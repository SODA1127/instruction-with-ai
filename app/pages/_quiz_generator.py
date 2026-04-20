from __future__ import annotations
import streamlit as st
import os
import io
import json
import re
import base64

try:
    import pypdf
    _PYPDF_OK = True
except ImportError:
    _PYPDF_OK = False

try:
    import fitz
    _FITZ_OK = True
except ImportError:
    _FITZ_OK = False

from src.config import P, get_max_pdf_pages, LOCAL_PDF_MAX_PAGES, CLOUD_PDF_MAX_PAGES, SUBJECT_LIST
from src.prompts.system_prompts import SYSTEM_PROMPTS, MATH_INSTRUCTION
from src.models import call_ai, stream_ai
from src.app_utils import encode_image_to_base64, make_pdf_bytes, parse_thinking_response, _pdf_extract_content, _parse_question_list, safe_filename, parse_quiz_markdown
from src.db_manager import db

def get_session_config() -> tuple[str, str, str]:
    return (
        st.session_state.get("provider", P.LMSTUDIO),
        st.session_state.get("model", ""),
        st.session_state.get("api_key", ""),
    )

# ────────────────────────────────────────────────────────────
# 기능 렌더링
# ────────────────────────────────────────────────────────────



def render_quiz_generator() -> None:
    """📝 기능 4: 평가문항 자동 생성기"""
    provider, model, api_key = get_session_config()
    st.header("📝 평가문항 자동 생성기")
    st.caption("학습 내용을 입력하면 다양한 유형의 평가 문항을 자동으로 생성합니다.")

    method = st.radio("입력 방식", ["✏️ 텍스트 입력", "📷 자료 이미지 업로드", "📄 PDF 문서 업로드"],
                      horizontal=True, key="quiz_input_method")
    content_text = ""
    ups = None

    if method == "✏️ 텍스트 입력":
        content_text = st.text_area("학습 내용",
            placeholder="예: 광합성은 식물이 빛 에너지를 이용하여...",
            height=180, key="quiz_text")
    elif method == "📷 자료 이미지 업로드":
        ups = st.file_uploader("교과서/자료 이미지 업로드 (다중 선택 가능)", type=["png", "jpg", "jpeg"],
                              key="quiz_img_upload", accept_multiple_files=True)
        if ups:
            for up in ups:
                st.image(up, use_container_width=True, caption=up.name)
    else:
        ups = st.file_uploader("관련 PDF 자료 업로드 (다중 선택 가능)", type=["pdf"], key="quiz_pdf_upload", accept_multiple_files=True)

    with st.expander("⚙️ 세부 설정", expanded=True):
        sc1, sc2 = st.columns(2)
        with sc1:
            quiz_subject = st.selectbox("과목 카테고리 (오답노트 분류용)", SUBJECT_LIST, key="quiz_subject_select")
        with sc2:
            difficulty = st.select_slider("난이도", ["하", "중하", "중", "중상", "상"],
                                          value="중", key="quiz_difficulty")

    c1, c2 = st.columns(2)
    with c1:
        q_types = st.multiselect("문항 유형",
            ["선택형(4지선다)", "단답형", "서술형", "참/거짓", "빈칸 채우기"],
            default=["선택형(4지선다)", "단답형"], key="quiz_types")
    with c2:
        num_q = st.slider("문항 수", 1, 50, 5, key="quiz_count_v2")

    if st.button("🎯 문항 생성", key="btn_quiz", use_container_width=True):
        img_list = []
        if method == "✏️ 텍스트 입력":
            if not content_text.strip():
                st.warning("⚠️ 학습 내용을 입력하세요.")
                return
        elif method == "📷 자료 이미지 업로드":
            if not ups:
                st.warning("⚠️ 이미지를 업로드하세요.")
                return
            for up in ups:
                img_list.append(encode_image_to_base64(up))
            content_text = "업로드된 이미지의 학습 내용을 바탕으로 문항을 출제해주세요."
        else:
            if not ups:
                st.warning("⚠️ PDF 자료를 업로드하세요.")
                return
            with st.spinner(f"📄 PDF {len(ups)}개 분석 중..."):
                for up in ups:
                    file_bytes = up.read()
                    page_count = 0
                    if _PYPDF_OK:
                        try:
                            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
                            page_count = len(reader.pages)
                        except Exception: pass
                    
                    text, images, extr_method = _pdf_extract_content(file_bytes, page_count, "")
                    if text.strip():
                        content_text += f"\n\n[파일: {up.name}]\n{text}"
                    if images:
                        img_list.extend(images)
                
            if not content_text.strip() and not img_list:
                st.warning("⚠️ 자료에서 내용을 추출할 수 없습니다.")
                return
            
            if not content_text.strip():
                content_text = "업로드된 PDF 문서의 내용을 바탕으로 문항을 출제해주세요."

        if not q_types:
            st.warning("⚠️ 문항 유형을 하나 이상 선택하세요.")
            return

        # 이미지 개수 제한
        if img_list:
            max_p = get_max_pdf_pages(provider)
            img_list = img_list[:max_p]

        system = (("<|think|>\n" if provider == P.LMSTUDIO else "") +
                  SYSTEM_PROMPTS["quiz_generator"])
        
        user_prompt = (f"다음 정보를 바탕으로 평가 문항을 생성해주세요.\n\n"
                       f"문항 유형: {', '.join(q_types)}\n"
                       f"문항 수: {num_q}\n"
                       f"난이도: {difficulty}\n"
                       f"학습자 상태: {st.session_state.get('user_mode', '학생')}\n")
        
        if content_text:
            user_prompt += f"\n[학습 내용]\n{content_text[:15000]}"

        audience_type = st.session_state.get("user_mode", "수강생용")
        full_prompt = (f"[{audience_type} 관점에서 문항 출제]\n\n{user_prompt}\n\n"
                       f"### 매우 중요한 지시사항 (반드시 준수) ###\n"
                       f"1. 모든 응답은 반드시 `[` 기호로 시작하여 `]` 기호로 끝나야 합니다. (JSON 배열 형식)\n"
                       f"2. 인사말('안녕하세요', '준비했습니다' 등)이나 서론, 결론을 절대 포함하지 마십시오.\n"
                       f"3. 마크다운 코드 블록(```json)을 사용하지 말고 곧바로 JSON 텍스트만 출력하십시오.\n"
                       f"4. 해설 내에서 1., 2. 같은 번호 매기기를 절대 하지 말고 '-' 기호만 사용하십시오.")
        
        try:
            with st.spinner("🤖 AI가 평가 문항을 출제하는 중..."):
                result = call_ai(system, full_prompt, provider, model, api_key,
                                 images_b64=img_list if img_list else None)
            
            st.session_state.quiz_current_subject = quiz_subject # 현재 과목 저장
            
            from src.app_utils import parse_quiz_json, questions_to_markdown
            
            # 원시 응답 저장
            st.session_state.quiz_raw_response = result
            thinking, final_raw = parse_thinking_response(result)
            
            # 1. JSON 파싱 시도
            quiz_list = parse_quiz_json(final_raw)
            st.session_state.quiz_list = quiz_list 
            st.session_state.quiz_gen_thinking = thinking
            
            # 2. 화면 표시용 마크다운 생성
            final_md = questions_to_markdown(quiz_list)
            st.session_state.quiz_gen_final = final_md
            
            # JSON 파싱 실패 시 경고 표시
            if not any(isinstance(q, dict) and q.get("options") for q in quiz_list):
                 st.warning("⚠️ AI가 구조화된 형식을 지키지 않아 일부 기능(라디오 버튼 등)이 제한될 수 있습니다.")
                 
        except Exception as e:
            st.error(f"❌ 생성 오류: {e}")
            with st.expander("🛠 디버그 정보"):
                st.code(st.session_state.get("quiz_raw_response", "응답 없음"))

    if st.session_state.get("quiz_gen_final"):
        thinking = st.session_state.get("quiz_gen_thinking", "")
        final = st.session_state.quiz_gen_final
        if thinking:
            with st.expander("🎯 출제 의도 및 AI 분석", expanded=False):
                st.markdown(
                    f'<div style="background:#1e1e2e;border-left:3px solid #059669;'
                    f'padding:16px;border-radius:8px;font-size:0.85rem;'
                    f'color:#6ee7b7;white-space:pre-wrap;">{thinking}</div>',
                    unsafe_allow_html=True)
        # ── 생성된 평가 문항 렌더링 (정답 섹션은 Expander로 보호) ──────────────────
        st.subheader("📝 생성된 평가 문항")
        
        # [ANSWER_START]와 [ANSWER_END] 사이를 Expander로 묶어서 렌더링
        content_parts = re.split(r'(\[ANSWER_START\].*?\[ANSWER_END\])', final, flags=re.DOTALL)
        for part in content_parts:
            if part.startswith("[ANSWER_START]"):
                # 태그 제거 후 Expander 적용
                ans_content = part.replace("[ANSWER_START]", "").replace("[ANSWER_END]", "").strip()
                with st.expander("💡 정답 및 해설 보기", expanded=False):
                    st.markdown(ans_content, unsafe_allow_html=True)
            else:
                if part.strip():
                    st.markdown(part, unsafe_allow_html=True)
        
        # 파일명 접두어 준비
        base_name = "quiz_questions"
        if st.session_state.get("quiz_pdf_upload"):
             first_up = st.session_state.quiz_pdf_upload[0] if isinstance(st.session_state.quiz_pdf_upload, list) else st.session_state.quiz_pdf_upload
             base_name = os.path.splitext(first_up.name)[0]
        elif st.session_state.get("quiz_img_upload"):
             first_up = st.session_state.quiz_img_upload[0] if isinstance(st.session_state.quiz_img_upload, list) else st.session_state.quiz_img_upload
             base_name = os.path.splitext(first_up.name)[0]
        base_name = safe_filename(base_name)
            
        dl_col1, dl_col2, dl_col3 = st.columns([1, 1, 1])
        with dl_col1:
            st.download_button("💾 문항 저장 (.md)", data=final.encode('utf-8-sig'),
                               file_name=f"{base_name}.md", mime="text/markdown",
                               key="dl_quiz", use_container_width=True)
        with dl_col2:
            pdf_bytes = make_pdf_bytes(st.session_state.quiz_gen_final)
            if pdf_bytes:
                st.download_button("💾 문항 저장 (.pdf)", data=pdf_bytes,
                                   file_name=f"{base_name}.pdf", mime="application/pdf",
                                   key="dl_quiz_pdf", use_container_width=True)
        with dl_col3:
            if st.button("📝 퀴즈 직접 풀어보기", key="btn_solve_interactive", use_container_width=True):
                if st.session_state.get("quiz_list"):
                    st.session_state.quiz_solving_mode = True
                    st.session_state.quiz_solved_data = st.session_state.quiz_list
                    st.session_state.quiz_user_answers = {}
                    st.session_state.quiz_results = {}
                    st.session_state.quiz_graded = False
                else:
                    st.warning("⚠️ 퀴즈 데이터가 없습니다.")
                st.rerun()

    # ── 퀴즈 직접 풀어보기 UI (대화형) ──────────────────────────────
    if st.session_state.get("quiz_solving_mode") and st.session_state.get("quiz_solved_data"):
        st.divider()
        st.subheader("✍️ 스마트 퀴즈 풀이")
        questions = st.session_state.quiz_solved_data
        
        for idx, q in enumerate(questions):
            st.markdown(f"#### **Q{q.get('number', idx+1)}. {q.get('content', '')}**")
            
            # multiple_choice이거나 options가 있는 경우 라디오 버튼 표시
            if q.get('type') == 'multiple_choice' or q.get('options'):
                options = q.get('options', [])
                if not options: # 비어있다면 긴급 fallback
                    options = ["답안 정보 없음"]
                    
                user_choice = st.radio(
                    f"정답을 선택하세요", 
                    options, 
                    key=f"solve_q_{idx}", 
                    index=None,
                    label_visibility="collapsed"
                )
                st.session_state.quiz_user_answers[idx] = user_choice
            else:
                # 주관식용 텍스트 입력
                user_text = st.text_input(
                    f"답안을 입력하세요", 
                    key=f"solve_q_{idx}",
                    placeholder="여기에 정답 입력..."
                )
                st.session_state.quiz_user_answers[idx] = user_text
            st.write("") # 간격 조절

        if st.button("🎯 채점하기", key="btn_quiz_grade", use_container_width=True):
            for idx, q in enumerate(questions):
                user_ans = str(st.session_state.quiz_user_answers.get(idx, "")).strip()
                real_ans = str(q['answer']).strip()
                # 채점 로직: 정답이 포함되어 있거나 일치하는지 확인
                is_correct = real_ans in user_ans or user_ans in real_ans if user_ans else False
                st.session_state.quiz_results[idx] = is_correct
            
            st.session_state.quiz_graded = True
            
            # --- [추가] 로그인 상태일 경우 DB에 결과 저장 ---
            if st.user.is_logged_in:
                user_id = st.user.get("sub")
                quiz_title = st.session_state.get("quiz_current_subject", "일반 퀴즈")
                score = sum(1 for v in st.session_state.quiz_results.values() if v)
                total = len(questions)
                # 틀린 문제 데이터만 추출하여 저장
                incorrect_data = [questions[idx] for idx, v in st.session_state.quiz_results.items() if not v]
                try:
                    db.save_quiz_result(user_id, quiz_title, score, total, incorrect_data)
                except Exception: pass
            
            st.rerun()

        if st.session_state.get("quiz_graded"):
            correct_count = sum(1 for v in st.session_state.quiz_results.values() if v)
            st.success(f"🎊 채점 완료! {len(questions)}문제 중 {correct_count}문제를 맞혔습니다.")
            
            for idx, q in enumerate(questions):
                is_correct = st.session_state.quiz_results.get(idx)
                color = "✅ 정답" if is_correct else "❌ 오답"
                
                with st.expander(f"{color} - 문항 {q['number']}", expanded=not is_correct):
                    st.markdown(f"**나의 답:** {st.session_state.quiz_user_answers.get(idx)}")
                    st.markdown(f"**실제 정답:** {q['answer']}")
                    if q['explanation']:
                        st.info(f"💡 해설: {q['explanation']}")
                    
                    if not is_correct:
                        if st.button(f"📌 오답노트에 담기 ({q['number']}번)", key=f"btn_mark_wrong_{idx}"):
                             w_notes = st.session_state.get("wrong_notes", [])
                             if q['content'] not in [wn['content'] for wn in w_notes]:
                                 # 과목 정보 추가하여 저장
                                 q_to_save = q.copy()
                                 
                                 # 자동 추론인 경우 AI가 분석한 과목 우선 사용
                                 selected_subj = st.session_state.get("quiz_current_subject", "자동 추론")
                                 if selected_subj == "자동 추론":
                                     q_to_save['subject'] = q.get('subject', '기타')
                                 else:
                                     q_to_save['subject'] = selected_subj
                                     
                                 w_notes.append(q_to_save)
                                 st.session_state.wrong_notes = w_notes
                                 st.toast(f"[{q_to_save['subject']}] {q['number']}번이 오답노트에 저장되었습니다!")

        if st.button("🔙 목록으로 돌아가기", key="btn_back_to_list"):
            st.session_state.quiz_solving_mode = False
            st.rerun()
