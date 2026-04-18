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

from src.config import P, get_max_pdf_pages, LOCAL_PDF_MAX_PAGES, CLOUD_PDF_MAX_PAGES
from src.prompts.system_prompts import SYSTEM_PROMPTS, MATH_INSTRUCTION
from src.models import call_ai, stream_ai
from src.utils import encode_image_to_base64, make_pdf_bytes, parse_thinking_response, _pdf_extract_content, _parse_question_list, safe_filename, parse_quiz_markdown

def get_session_config() -> tuple[str, str, str]:
    return (
        st.session_state.get("provider", P.LMSTUDIO),
        st.session_state.get("model", ""),
        st.session_state.get("api_key", ""),
    )

# ────────────────────────────────────────────────────────────
# 기능 렌더링
# ────────────────────────────────────────────────────────────

def render_image_analyzer() -> None:
    """📸 기능 1: 이미지 기반 문제 분석기"""
    provider, model, api_key = get_session_config()
    st.header("📸 이미지 기반 문제 분석기")
    st.caption("시험지, 학생 답안지, 교과서 사진을 업로드하면 AI가 분석합니다.")

    col1, col2 = st.columns([1, 1])
    with col1:
        uploaded = st.file_uploader("이미지 업로드", type=["png", "jpg", "jpeg"],
                                    key="img_analyzer_upload")
        analysis_type = st.radio("분석 유형",
            ["📄 문제 텍스트 추출", "✏️ 답안 채점 보조", "📊 난이도 분석"],
            key="img_analysis_type")
        extra_info = st.text_area("추가 지시사항 (선택)",
            placeholder="예: 중학교 2학년 수학 문제입니다.",
            key="img_extra_info", height=100)
        if uploaded:
            st.image(uploaded, caption="업로드된 이미지", use_container_width=True)

    with col2:
        if st.button("🔍 분석 시작", key="btn_image_analyze", use_container_width=True):
            if not uploaded:
                st.warning("⚠️ 이미지를 먼저 업로드하세요.")
                return
            user_mode = st.session_state.get("user_mode", "👨‍🎓 수강생용")
            full_prompt = f"[{user_mode} 관점에서 분석]\n\n{user_prompt}"
            try:
                with st.spinner("🤖 AI가 이미지를 분석하는 중..."):
                    b64 = encode_image_to_base64(uploaded)
                    result = call_ai(SYSTEM_PROMPTS["image_analyzer"],
                                     full_prompt, provider, model, api_key,
                                     images_b64=[b64])
                st.session_state.img_analyzer_result = result
            except Exception as e:
                st.error(f"❌ {e}")

            st.subheader("📋 분석 결과")
            # 생각 과정 제거 및 후처리 적용
            _, final_content = parse_thinking_response(st.session_state.img_analyzer_result)
            st.markdown(final_content)
            dl_col1, dl_col2 = st.columns([1, 1])
            # 파일명 접두어 준비
            base_name = "image_analysis"
            if uploaded:
                base_name = os.path.splitext(uploaded.name)[0]
            base_name = safe_filename(base_name)
            
            with dl_col1:
                st.download_button("💾 결과 저장 (.md)", data=st.session_state.img_analyzer_result.encode('utf-8-sig'),
                                   file_name=f"{base_name}.md", mime="text/markdown",
                                   key="download_img_result_md", use_container_width=True)
            with dl_col2:
                pdf_bytes = make_pdf_bytes(st.session_state.img_analyzer_result)
                if pdf_bytes:
                    st.download_button("💾 결과 저장 (.pdf)", data=pdf_bytes,
                                       file_name=f"{base_name}.pdf", mime="application/pdf",
                                       key="download_img_result_pdf", use_container_width=True)


def render_step_solver() -> None:
    """🧠 기능 2: 단계별 풀이 생성기 (Thinking 모드)"""
    provider, model, api_key = get_session_config()
    st.header("🧠 단계별 풀이 생성기")
    st.caption("수학·과학 문제를 입력하면 AI가 단계별로 풀이 과정을 보여줍니다.")

    method = st.radio("입력 방식", ["✏️ 텍스트 입력", "📷 문제 사진 업로드", "📄 PDF 문서 업로드"],
                      horizontal=True, key="solver_input_method")
    
    problem_text = ""
    up = None

    if method == "✏️ 텍스트 입력":
        problem_text = st.text_area("문제 입력",
            placeholder="예: 이차방정식 x² - 5x + 6 = 0을 풀어라.",
            height=150, key="solver_text")
    elif method == "📷 문제 사진 업로드":
        up = st.file_uploader("문제 사진 업로드", type=["png", "jpg", "jpeg"],
                              key="solver_img_upload")
        if up:
            st.image(up, use_container_width=True)
    else:
        up = st.file_uploader("PDF 문제 파일 업로드", type=["pdf"], key="solver_pdf_upload")

    subject = st.selectbox("과목", ["수학", "물리", "화학", "생물", "지구과학", "기타"],
                           key="solver_subject")

    if st.button("🧩 단계별 풀이 생성", key="btn_solve", use_container_width=True):
        img_list = None
        if method == "✏️ 텍스트 입력":
            if not problem_text.strip():
                st.warning("⚠️ 문제를 입력하세요.")
                return
        elif method == "📷 문제 사진 업로드":
            if not up:
                st.warning("⚠️ 이미지를 업로드하세요.")
                return
            img_b64 = encode_image_to_base64(up)
            img_list = [img_b64]
            problem_text = "업로드된 이미지의 문제를 단계별로 풀어주세요."
        else:
            if not up:
                st.warning("⚠️ PDF 문서를 업로드하세요.")
                return
            with st.spinner("📄 PDF 문서 분석 중..."):
                file_bytes = up.read()
                page_count = 0
                if _PYPDF_OK:
                    try:
                        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
                        page_count = len(reader.pages)
                    except Exception:
                        pass
                extracted_text, extracted_images, extr_method = _pdf_extract_content(file_bytes, page_count, "")
                if extr_method == "text" and extracted_text.strip():
                    problem_text = extracted_text
                else:
                    img_list = extracted_images if extracted_images else None
                    if img_list and len(img_list) > 1:
                        img_list = img_list[:1] # 한문제만 풀이하므로 첫장만
                    problem_text = "업로드된 PDF 문서 첫 페이지의 문제를 단계별로 풀어주세요."

        user_mode = st.session_state.get("user_mode", "👨‍🎓 수강생용")
        full_user_prompt = f"[{user_mode}을 위한 풀이]\n\n{user_prompt}"

        try:
            with st.spinner("🤔 AI가 문제를 풀고 있습니다..."):
                result = call_ai(system, full_user_prompt, provider, model, api_key,
                                 images_b64=img_list)
            thinking, final = parse_thinking_response(result)
            st.session_state.step_solver_thinking = thinking
            st.session_state.step_solver_final = final
        except Exception as e:
            st.error(f"❌ {e}")

    if st.session_state.get("step_solver_final"):
        thinking = st.session_state.get("step_solver_thinking", "")
        final = st.session_state.step_solver_final
        if thinking:
            with st.expander("🧠 AI의 사고 과정 보기", expanded=False):
                st.markdown(
                    f'<div style="background:#1e1e2e;border-left:3px solid #7c3aed;'
                    f'padding:16px;border-radius:8px;font-size:0.85rem;'
                    f'color:#c4b5fd;white-space:pre-wrap;">{thinking}</div>',
                    unsafe_allow_html=True)
        st.subheader("📐 단계별 풀이")
        st.markdown(final)
        
        # 파일명 접두어 준비
        base_name = "problem_solution"
        if st.session_state.get("solver_img_upload"):
            base_name = os.path.splitext(st.session_state.solver_img_upload.name)[0]
        elif st.session_state.get("solver_pdf_upload"):
            base_name = os.path.splitext(st.session_state.solver_pdf_upload.name)[0]
        base_name = safe_filename(base_name)

        dl_col1, dl_col2 = st.columns([1, 1])
        with dl_col1:
            st.download_button("💾 풀이 저장 (.md)", data=final.encode('utf-8-sig'),
                               file_name=f"{base_name}.md", mime="text/markdown",
                               key="download_step_solver_md", use_container_width=True)
        with dl_col2:
            pdf_bytes = make_pdf_bytes(result) # make_pdf_bytes performs internal parsing
            if pdf_bytes:
                st.download_button("💾 풀이 저장 (.pdf)", data=pdf_bytes,
                                   file_name=f"{base_name}.pdf", mime="application/pdf",
                                   key="download_step_solver_pdf", use_container_width=True)


def render_lesson_plan() -> None:
    """📄 기능 3: 교안/학습자료 생성기"""
    provider, model, api_key = get_session_config()
    st.header("📄 교안 / 학습자료 생성기")
    st.caption("과목과 단원 정보를 입력하면 AI가 완성된 교안을 생성합니다.")

    col1, col2 = st.columns([1, 1])
    with col1:
        subject = st.selectbox("과목",
            ["국어", "영어", "수학", "과학", "사회", "역사", "도덕",
             "음악", "미술", "체육", "기술·가정", "프로그래밍", "기타"], key="plan_subject")
        grade = st.selectbox("학년",
            ["초등 1학년", "초등 2학년", "초등 3학년", "초등 4학년", "초등 5학년", "초등 6학년",
             "중학 1학년", "중학 2학년", "중학 3학년",
             "고등 1학년", "고등 2학년", "고등 3학년",
             "대학교 1학년", "대학교 2학년", "대학교 3학년", "대학교 4학년"], key="plan_grade")
        unit_name = st.text_input("단원명", placeholder="예: 1단원. 문학의 빛깔",
                                  key="plan_unit")
        duration = st.number_input("수업 시간 (분)", min_value=10, max_value=120,
                                   value=45, step=5, key="plan_duration")
        ups = st.file_uploader("📄 참고 자료 PDF 업로드 (다중 선택 가능)", type=["pdf"], key="plan_pdf_upload", accept_multiple_files=True)
    with col2:
        plan_type = st.selectbox("교안 유형",
            ["📋 수업 지도안", "📝 학습 활동지", "📊 평가 계획서"], key="plan_type")
        goals = st.text_area("학습 목표 (성취기준)",
            placeholder="예: 시의 운율과 이미지를 분석하여 작가의 의도를 파악할 수 있다.",
            height=100, key="plan_goals")
        notes = st.text_area("특이사항 / 추가 요청",
            placeholder="예: 모둠 활동 중심, 디지털 기기 활용",
            height=80, key="plan_notes")

    if st.button("📋 교안 생성", key="btn_plan", use_container_width=True):
        if not unit_name.strip():
            st.warning("⚠️ 단원명을 입력해주세요.")
            return
            
        pdf_content = ""
        all_images = []
        if ups:
            with st.spinner(f"📄 PDF {len(ups)}개 분석 중..."):
                for up in ups:
                    file_bytes = up.read()
                    page_count = 0
                    if _PYPDF_OK:
                        try:
                            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
                            page_count = len(reader.pages)
                        except Exception: pass
                    
                    text, images, method = _pdf_extract_content(file_bytes, page_count, "")
                    if text.strip():
                        pdf_content += f"\n\n[파일: {up.name}]\n{text}"
                    if images:
                        all_images.extend(images)

        img_list = None
        if all_images:
            max_p = get_max_pdf_pages(provider)
            img_list = all_images[:max_p]

        type_label = plan_type.split(" ", 1)[1]
        user_prompt = (f"다음 정보를 바탕으로 [{type_label}]을 작성해주세요.\n\n"
                       f"과목: {subject}\n학년: {grade}\n단원명: {unit_name}\n"
                       f"수업 시간: {duration}분\n"
                       f"학습 목표: {goals or '교사가 설정 예정'}\n"
                       f"특이사항: {notes or '없음'}")
        
        if pdf_content:
            user_prompt += f"\n\n[참고 자료 내용]\n{pdf_content[:20000]}"
        elif img_list:
            user_prompt += f"\n\n[참고 자료]\n업로드된 참고 자료의 이미지 및 내용을 바탕으로 반영해주세요."

        user_mode = st.session_state.get("user_mode", "👩‍🏫 교육자용")
        full_prompt = f"[{user_mode}을 위한 교안/자료 작성]\n\n{user_prompt}"

        try:
            with st.spinner("📝 AI가 교안을 작성하는 중..."):
                result = call_ai(SYSTEM_PROMPTS["lesson_plan"], full_prompt,
                                 provider, model, api_key, images_b64=img_list)
            st.session_state.lesson_plan_result = result
        except Exception as e:
            st.error(f"❌ {e}")

    if st.session_state.get("lesson_plan_result"):
        st.subheader("📋 생성된 교안")
        # 생각 과정 제거 및 후처리 적용
        _, final_content = parse_thinking_response(st.session_state.lesson_plan_result)
        st.markdown(final_content)
        
        # 파일명 접두어 준비
        base_name = "lesson_plan"
        if st.session_state.get("plan_pdf_upload"):
             # 다중 업로드일 경우 첫 번째 파일명 활용
             first_up = st.session_state.plan_pdf_upload[0] if isinstance(st.session_state.plan_pdf_upload, list) else st.session_state.plan_pdf_upload
             base_name = os.path.splitext(first_up.name)[0]
        base_name = safe_filename(base_name)
        
        dl_col1, dl_col2 = st.columns([1, 1])
        with dl_col1:
            _, final_md = parse_thinking_response(st.session_state.lesson_plan_result)
            st.download_button("💾 Markdown 저장", data=final_md.encode('utf-8-sig'),
                               file_name=f"{base_name}.md", mime="text/markdown",
                               key="dl_plan_md", use_container_width=True)
        with dl_col2:
            pdf_bytes = make_pdf_bytes(st.session_state.lesson_plan_result)
            if pdf_bytes:
                st.download_button("💾 PDF 저장", data=pdf_bytes,
                                   file_name=f"{base_name}.pdf", mime="application/pdf",
                                   key="dl_plan_pdf", use_container_width=True)


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

    c1, c2, c3 = st.columns(3)
    with c1:
        q_types = st.multiselect("문항 유형",
            ["선택형(4지선다)", "단답형", "서술형", "참/거짓", "빈칸 채우기"],
            default=["선택형(4지선다)", "단답형"], key="quiz_types")
    with c2:
        num_q = st.slider("문항 수", 1, 20, 5, key="quiz_count")
    with c3:
        difficulty = st.select_slider("난이도", ["하", "중하", "중", "중상", "상"],
                                      value="중", key="quiz_difficulty")

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

        user_mode = st.session_state.get("user_mode", "👩‍🏫 교육자용")
        full_prompt = f"[{user_mode} 관점에서 문항 출제]\n\n{user_prompt}"
        
        try:
            with st.spinner("🤖 AI가 평가 문항을 출제하는 중..."):
                result = call_ai(system, full_prompt, provider, model, api_key,
                                 images_b64=img_list if img_list else None)
            thinking, final = parse_thinking_response(result)
            st.session_state.quiz_gen_thinking = thinking
            st.session_state.quiz_gen_final = final
        except Exception as e:
            st.error(f"❌ {e}")

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
        st.subheader("📝 생성된 평가 문항")
        # 이미 parse_thinking_response를 거친 final 변수 사용
        st.markdown(final)
        
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
                st.session_state.quiz_solving_mode = True
                st.session_state.quiz_solved_data = parse_quiz_markdown(final)
                st.session_state.quiz_user_answers = {}
                st.session_state.quiz_results = {}
                st.session_state.quiz_graded = False
                st.rerun()

    # ── 퀴즈 직접 풀어보기 UI ──────────────────────────────────────
    if st.session_state.get("quiz_solving_mode") and st.session_state.get("quiz_solved_data"):
        st.divider()
        st.subheader("✍️ 스마트 퀴즈 풀이")
        questions = st.session_state.quiz_solved_data
        
        for idx, q in enumerate(questions):
            st.markdown(f"**문항 {q['number']}. {q['content']}**")
            
            if q['options']:
                # 객관식용 라디오 버튼
                user_choice = st.radio(f"답안 선택 (Q{q['number']})", q['options'], 
                                       key=f"solve_q_{idx}", index=None)
                st.session_state.quiz_user_answers[idx] = user_choice
            else:
                # 주관식용 텍스트 입력
                user_text = st.text_input(f"답안 입력 (Q{q['number']})", 
                                          key=f"solve_q_{idx}")
                st.session_state.quiz_user_answers[idx] = user_text

        if st.button("🎯 채점하기", key="btn_quiz_grade", use_container_width=True):
            for idx, q in enumerate(questions):
                user_ans = str(st.session_state.quiz_user_answers.get(idx, "")).strip()
                real_ans = str(q['answer']).strip()
                # 채점 로직: 정답이 포함되어 있거나 일치하는지 확인
                is_correct = real_ans in user_ans or user_ans in real_ans if user_ans else False
                st.session_state.quiz_results[idx] = is_correct
            st.session_state.quiz_graded = True
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
                                 w_notes.append(q)
                                 st.session_state.wrong_notes = w_notes
                                 st.toast(f"{q['number']}번 문제가 오답노트에 저장되었습니다!")

        if st.button("🔙 목록으로 돌아가기", key="btn_back_to_list"):
            st.session_state.quiz_solving_mode = False
            st.rerun()

    # ── 오답노트 모아보기 ──────────────────────────────────────────
    if st.session_state.get("wrong_notes"):
        st.divider()
        with st.expander("📚 나의 오답노트 모아보기", expanded=True):
            for i, wn in enumerate(st.session_state.wrong_notes):
                st.markdown(f"**[{i+1}] {wn['content']}**")
                st.markdown(f"- 정답: {wn['answer']}")
                if wn['explanation']:
                    st.caption(f"💡 해설: {wn['explanation']}")
                if st.button(f"🗑️ 삭제", key=f"del_wn_{i}"):
                    st.session_state.wrong_notes.pop(i)
                    st.rerun()
            if st.button("🗑️ 전체 초기화", key="clear_all_wn"):
                st.session_state.wrong_notes = []
                st.rerun()


def render_chatbot() -> None:
    """💬 기능 5: 교육 상담 챗봇"""
    provider, model, api_key = get_session_config()
    st.header("💬 교육 상담 챗봇")
    st.caption("교수법, 학생 지도, 학급 경영 등 어떤 고민이든 편하게 이야기하세요.")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    for msg in st.session_state.chat_history:
        avatar = "🎓" if msg["role"] == "assistant" else "🙋"
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])

    user_input = st.chat_input("고민이나 질문을 입력하세요...")

    if st.sidebar.button("🗑️ 대화 초기화", key="clear_chat"):
        st.session_state.chat_history = []
        st.rerun()

    if user_input:
        with st.chat_message("user", avatar="🙋"):
            st.markdown(user_input)
        st.session_state.chat_history.append({"role": "user", "content": user_input})

        with st.chat_message("assistant", avatar="🎓"):
            full_response = ""
            try:
                history = st.session_state.chat_history[:-1]
                user_mode = st.session_state.get("user_mode", "수강생용")
                full_input = f"[{user_mode}과 대화 중]\n{user_input}"
                
                resp = call_ai(SYSTEM_PROMPTS["chatbot"], full_input,
                               provider, model, api_key,
                               history=history, stream=True)
                full_response = stream_ai(resp, provider)
            except Exception as e:
                st.error(f"❌ {e}")
                full_response = ""

        _, clean = parse_thinking_response(full_response)
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": clean or full_response,
        })


# ────────────────────────────────────────────────────────────
# PDF 유틸리티
# ────────────────────────────────────────────────────────────

# PDF 텍스트가 분석에 충분한 품질인지 판별하는 기준 (페이지당 평균 글자 수)
_PDF_TEXT_MIN_CHARS_PER_PAGE = 80


def extract_pdf_text(file_bytes: bytes) -> tuple[str, int]:
    """
    pypdf로 PDF에서 텍스트를 추출합니다.
    Returns: (추출된 전체 텍스트, 총 페이지 수)
    """
    if not _PYPDF_OK:
        return "", 0
    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        pages.append(f"[페이지 {i + 1}]\n{text.strip()}")
    return "\n\n".join(pages), len(reader.pages)


def pdf_pages_to_images(file_bytes: bytes, max_pages: int = 20, selected_pages: set[int] | None = None) -> list[str]:
    """
    pymupdf(fitz)로 PDF 페이지를 base64 JPEG 이미지 리스트로 변환합니다.
    max_pages를 초과하는 페이지는 건너뜁니다.
    Returns: base64 문자열 리스트
    """
    if not _FITZ_OK:
        return []
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    images = []
    for i in range(len(doc)):
        if selected_pages is not None and i not in selected_pages:
            continue
        if len(images) >= max_pages:
            break
        page = doc[i]
        # 150 DPI 상당 (2x 배율) — 속도와 품질의 균형
        mat = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("jpeg")
        images.append(base64.b64encode(img_bytes).decode("utf-8"))
    doc.close()
    return images


def is_pdf_text_sufficient(text: str, page_count: int) -> bool:
    """텍스트 품질이 분석에 충분한지 판별합니다."""
    if not text.strip() or page_count == 0:
        return False
    avg_chars = len(text.replace("\n", "").replace(" ", "")) / page_count
    return avg_chars >= _PDF_TEXT_MIN_CHARS_PER_PAGE


def _pdf_extract_content(
    file_bytes: bytes,
    page_count: int,
    page_range: str,
) -> tuple[str, list[str] | None, str]:
    """
    PDF에서 텍스트 또는 이미지를 추출합니다 (공통 로직).
    Returns: (content_text, images_b64_or_None, extraction_method)
    """
    # 페이지 범위 파싱
    selected_pages: set[int] | None = None
    if page_range.strip():
        try:
            selected_pages = set()
            for part in page_range.replace(" ", "").split(","):
                if "-" in part:
                    a, b = part.split("-")
                    selected_pages.update(range(int(a) - 1, int(b)))
                else:
                    selected_pages.add(int(part) - 1)
        except ValueError:
            selected_pages = None

    extracted_text, n_pages = extract_pdf_text(file_bytes)

    # 페이지 범위 필터링
    if selected_pages and extracted_text:
        filtered, current_page_idx = [], 0
        for line in extracted_text.split("\n"):
            m = re.match(r"\[페이지 (\d+)\]", line)
            if m:
                current_page_idx = int(m.group(1)) - 1
            if m is None or current_page_idx in selected_pages:
                filtered.append(line)
        extracted_text = "\n".join(filtered)

    text_ok = is_pdf_text_sufficient(extracted_text, n_pages or max(1, page_count))

    if text_ok:
        return extracted_text, None, "text"
    elif _FITZ_OK:
        max_pg = 999  # Extract all needed images safely, limits will be handled in chunks or by selected_pages
        images = pdf_pages_to_images(file_bytes, max_pg, selected_pages)
        if images:
            return "", images, "vision"

    # 폴백: 텍스트가 부족해도 그대로 사용
    return extracted_text, None, "text (sparse)"


def _parse_question_list(raw: str) -> list[dict]:
    """
    AI 응답에서 문제 목록 JSON을 파싱합니다.
    [{"번호":"1","내용":"..."},...] 형식 또는 텍스트 폴백.
    """
    # JSON 블록 추출 시도
    json_match = re.search(r"\[[\s\S]*\]", raw)
    if json_match:
        try:
            data = json.loads(json_match.group())
            # 최소 필드 확인
            return [
                {"번호": str(q.get("번호", i + 1)), "내용": q.get("내용", "").strip()}
                for i, q in enumerate(data)
                if q.get("내용", "").strip()
            ]
        except json.JSONDecodeError:
            pass

    # 폴백 1: JSON이 깨졌거나 역슬래시 에러 시 정규식으로 직접 키/값 추출
    questions = []
    # "번호":"...", "내용":"..." 패턴 탐색
    matches = re.findall(r'"번호"\s*:\s*"([^"]+)"\s*,\s*"내용"\s*:\s*"(.*?)"\s*\}', raw, re.DOTALL)
    if matches:
        for num, content in matches:
            questions.append({"번호": num, "내용": content.strip().replace('\\"', '"').replace('\\\\', '\\')})
        if questions:
            return questions

    # 폴백 2: "1." / "1)" / "문제 1" 텍스트 패턴으로 분할
    pattern = re.split(r"(?m)^(?:문제\s*)?(\d+)[.)]\s+", raw)
    if len(pattern) > 2:
        for i in range(1, len(pattern) - 1, 2):
            num = pattern[i]
            content = pattern[i + 1].strip()
            if content:
                questions.append({"번호": num, "내용": content[:500]})
    return questions


def _render_question_solver_ui(
    provider: str, model: str, api_key: str,
) -> None:
    """
    세션에 저장된 문제 목록을 카드로 렌더링하고
    문제별 '풀이하기' 버튼 → 개별 AI 풀이를 제공합니다.
    """
    questions: list[dict] = st.session_state.get("pdf_questions", [])
    solutions: dict = st.session_state.setdefault("pdf_solutions", {})
    content_text: str = st.session_state.get("pdf_content_text", "")
    images_b64 = st.session_state.get("pdf_images_b64", None)
    method = st.session_state.get("pdf_extraction_method", "text")
    filename = st.session_state.get("pdf_filename", "문서")

    if not questions:
        return

    # 헤더
    badge_color = "#10b981" if method == "text" else "#f59e0b"
    badge_label = "📝 텍스트" if method == "text" else "🖼️ 비전 AI"
    st.markdown(
        f'<span style="background:{badge_color}22;border:1px solid {badge_color};'
        f'border-radius:6px;padding:3px 10px;font-size:0.8rem;color:{badge_color};">'
        f'{badge_label}</span>'
        f'&nbsp;&nbsp;<b style="color:#94a3b8;font-size:0.9rem;">{filename}</b>',
        unsafe_allow_html=True,
    )

    solved_count = len(solutions)
    st.markdown(
        f"### 🔢 감지된 문제 — {len(questions)}개 "
        f"<span style='color:#10b981;font-size:0.85rem;'>({solved_count}개 풀이 완료)</span>",
        unsafe_allow_html=True,
    )

    # 전체 풀이 / 초기화 버튼
    ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([2, 2, 2])
    with ctrl_col1:
        if st.button("⚡ 전체 문제 풀이", key="solve_all_btn", use_container_width=True):
            st.session_state.pdf_solve_all = True
    with ctrl_col2:
        if st.button("🗑️ 풀이 초기화", key="clear_solutions_btn", use_container_width=True):
            st.session_state.pdf_solutions = {}
            st.rerun()
    with ctrl_col3:
        if st.button("🔄 문제 재추출", key="reextract_btn", use_container_width=True):
            for k in ("pdf_questions", "pdf_solutions", "pdf_solve_all"):
                st.session_state.pop(k, None)
            st.rerun()

    st.divider()

    # 전체 풀이 모드 처리
    if st.session_state.get("pdf_solve_all"):
        unsolved = [i for i in range(len(questions)) if i not in solutions]
        if unsolved:
            prog = st.progress(0, text="전체 풀이 진행 중...")
            for step, idx in enumerate(unsolved):
                q = questions[idx]
                prog.progress((step + 1) / len(unsolved),
                              text=f"문제 {q['번호']} 풀이 중... ({step+1}/{len(unsolved)})")
                sol = _solve_single_question(
                    q, content_text, images_b64, provider, model, api_key, filename
                )
                solutions[idx] = sol
            prog.empty()
        st.session_state.pdf_solve_all = False
        st.rerun()

    # 문제 카드
    for i, q in enumerate(questions):
        solved = i in solutions

        card_border = "#10b981" if solved else "#334155"
        card_bg = "#0d1f1a" if solved else "#0f172a"
        st.markdown(
            f'<div style="border:1px solid {card_border};border-radius:12px;'
            f'background:{card_bg};padding:16px 20px;margin-bottom:10px;">',
            unsafe_allow_html=True,
        )

        q_col, btn_col = st.columns([5, 1])
        with q_col:
            # 문제 번호 배지 + 내용 (길면 expander)
            st.markdown(
                f'<div style="display:flex;align-items:flex-start;gap:12px;">'
                f'<span style="background:#4f46e5;color:white;border-radius:6px;'
                f'padding:2px 10px;font-weight:700;font-size:0.85rem;white-space:nowrap;">'
                f'{q["번호"]}번</span>'
                f'<span style="color:#e2e8f0;font-size:0.95rem;">{q["내용"][:200]}'
                f'{"..." if len(q["내용"]) > 200 else ""}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
        with btn_col:
            btn_label = "✅ 재풀이" if solved else "📖 풀이"
            if st.button(btn_label, key=f"solve_q_{i}", use_container_width=True):
                with st.spinner(f"문제 {q['번호']} 풀이 생성 중..."):
                    sol = _solve_single_question(
                        q, content_text, images_b64, provider, model, api_key, filename
                    )
                solutions[i] = sol
                st.rerun()

        if solved:
            with st.expander(f"📐 문제 {q['번호']} 풀이 보기", expanded=True):
                # 생각 과정 제거 및 후처리($, ** 보정) 적용
                _, final_sol = parse_thinking_response(solutions[i])
                st.markdown(final_sol)
                # 파일명 접두어 준비
                orig_name = st.session_state.get("pdf_filename", "pdf")
                base_name = os.path.splitext(orig_name)[0]
                q_filename = safe_filename(f"{i+1}_{base_name}_Q{i+1}")

                dl_col1, dl_col2 = st.columns([1, 1])
                with dl_col1:
                    _, final_sol = parse_thinking_response(solutions[i])
                    st.download_button(
                        "💾 MD 저장",
                        data=final_sol.encode('utf-8-sig'),
                        file_name=f"{q_filename}.md",
                        mime="text/markdown",
                        key=f"dl_sol_{i}",
                        use_container_width=True,
                    )
                with dl_col2:
                    pdf_bytes = make_pdf_bytes(solutions[i])
                    if pdf_bytes:
                        st.download_button(
                            "💾 PDF 저장",
                            data=pdf_bytes,
                            file_name=f"{q_filename}.pdf",
                            mime="application/pdf",
                            key=f"dl_sol_pdf_{i}",
                            use_container_width=True,
                        )

        st.markdown("</div>", unsafe_allow_html=True)

    # 풀이 전체 저장
    if solutions:
        all_sols = "\n\n---\n\n".join(
            f"## 문제 {questions[i]['번호']}\n{questions[i]['내용']}\n\n### 풀이\n{sol}"
            for i, sol in sorted(solutions.items())
        )
        # 파일명 접두어 준비 (전체)
        orig_name = st.session_state.get("pdf_filename", "pdf")
        base_name = os.path.splitext(orig_name)[0]
        all_filename = safe_filename(f"{base_name}_전체풀이")

        col1, col2 = st.columns(2)
        with col1:
            _, final_all = parse_thinking_response(all_sols)
            st.download_button(
                "💾 전체 풀이 저장 (.md)",
                data=final_all.encode('utf-8-sig'),
                file_name=f"{all_filename}.md",
                mime="text/markdown",
                key="dl_all_solutions",
                use_container_width=True,
            )
        with col2:
            pdf_bytes = make_pdf_bytes(all_sols)
            if pdf_bytes:
                st.download_button(
                    "💾 전체 풀이 저장 (.pdf)",
                    data=pdf_bytes,
                    file_name=f"{all_filename}.pdf",
                    mime="application/pdf",
                    key="dl_all_solutions_pdf",
                    use_container_width=True,
                )


def _solve_single_question(
    q: dict,
    content_text: str,
    images_b64: list[str] | None,
    provider: str, model: str, api_key: str,
    filename: str,
) -> str:
    """단일 문제에 대한 상세 풀이를 AI에 요청합니다."""
    # 컨텍스트: 문제 주변 내용만 잘라서 전송 (토큰 절약)
    # 문제 내용이 텍스트에 있으면 앞뒤 2000자만 추출
    context = ""
    if content_text:
        needle = q["내용"][:50]  # 문제 앞부분으로 검색
        idx = content_text.find(needle)
        if idx >= 0:
            start = max(0, idx - 500)
            end = min(len(content_text), idx + 2000)
            context = content_text[start:end]
        else:
            # 못 찾으면 전체 텍스트 앞 3000자만
            context = content_text[:3000]

    user_mode = st.session_state.get("user_mode", "👩‍🏫 교육자용")
    is_educator = "교육자" in user_mode

    system = (
        f"당신은 [{user_mode}]을 위한 한국의 교육 전문가 AI입니다.\n"
        "학생이 제출한 시험 문제를 받아 명확하고 단계적인 풀이를 제공합니다.\n\n"
        "[콘텐츠 유형별 출력 형식]\n"
        "1. 일반 교과(수학, 과학 등): :::problem, :::concept, :::solving, :::explanation 컨테이너를 사용하여 알록달록하게 구성하세요.\n"
        "2. 프로그래밍/코딩: 컨테이너 박스 없이 표준 마크다운(헤더 #, ##, 코드 블록 ```) 포맷을 사용하여 기술 문서처럼 깔끔하게 구성하세요.\n\n"
        f"{MATH_INSTRUCTION}\n"
        "항상 한국어로 답변하세요. 프로그래밍 문제라면 반드시 가독성 좋은 코드 스니펫을 포함하세요.\n"
        + ("교수법 팁이나 보충 설명도 포함하면 좋습니다." if is_educator else "이해하기 쉬운 비유와 학습 권장 사항을 포함하세요.")
    )

    user_prompt = (
        f"[문서: {filename}]\n"
        f"[대상: {user_mode}]\n\n"
        f"**문제 {q['번호']}번**\n{q['내용']}\n\n"
    )
    if context:
        user_prompt += f"[문서 내 관련 컨텍스트]\n{context}\n\n"
    
    user_prompt += "이 문제를 위 대상의 눈높이에 맞춰 단계별로 자세히 분석 및 풀이해주세요."

    return call_ai(system, user_prompt, provider, model, api_key,
                   images_b64=images_b64 if not context else None)


def render_pdf_analyzer() -> None:
    """📑 기능 6: PDF 문서 분석기 (문제별 개별 풀이 지원)"""
    provider, model, api_key = get_session_config()
    st.header("📑 PDF 문서 분석기")
    st.caption("시험지·교재 PDF 업로드 → 문제 자동 감지 → 문제별 개별 풀이")

    if not _PYPDF_OK and not _FITZ_OK:
        st.error("❌ PDF 처리 라이브러리가 없습니다. `pip install pypdf pymupdf`를 실행하세요.")
        return

    # ── 이미 문제가 추출된 상태: 문제 카드 UI 우선 렌더링 ──────
    if st.session_state.get("pdf_questions"):
        with st.sidebar:
            with st.expander("📑 현재 PDF", expanded=False):
                st.caption(st.session_state.get("pdf_filename", ""))
                if st.button("📂 새 PDF 열기", key="open_new_pdf"):
                    for k in ("pdf_questions", "pdf_solutions", "pdf_content_text",
                              "pdf_images_b64", "pdf_filename", "pdf_extraction_method",
                              "pdf_solve_all"):
                        st.session_state.pop(k, None)
                    st.rerun()
        _render_question_solver_ui(provider, model, api_key)
        return

    # ── 업로드 & 분석 설정 UI ────────────────────────────────────
    col1, col2 = st.columns([1, 1])

    with col1:
        uploaded = st.file_uploader(
            "PDF 파일 업로드 (최대 50MB)",
            type=["pdf"],
            key="pdf_upload",
        )

        analysis_type = st.selectbox(
            "분석 유형",
            [
                "🔢 문제별 개별 풀이  ← 권장 (컨텍스트 제한 우회)",
                "📋 전체 내용 요약",
                "🔑 핵심 개념 및 키워드 추출",
                "📝 학습 자료 / 노트 생성",
                "🔍 특정 내용 질의응답",
            ],
            key="pdf_analysis_type",
        )

        custom_question = ""
        if analysis_type.startswith("🔍"):
            custom_question = st.text_area(
                "질문 입력",
                placeholder="예: 이 문서에서 광합성 단계를 설명하는 부분을 요약해줘.",
                height=100,
                key="pdf_question",
            )

        st.info(f"📍 현재 모드: **{st.session_state.get('user_mode', '교육자용')}**")

        page_range = st.text_input(
            "분석할 페이지 범위 (선택, 비워두면 전체)",
            placeholder="예: 1-10  또는  3,7,12",
            key="pdf_page_range",
        )

    with col2:
        if uploaded:
            file_bytes = uploaded.read()
            file_size_mb = len(file_bytes) / 1_048_576

            page_count = 0
            if _PYPDF_OK:
                try:
                    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
                    page_count = len(reader.pages)
                except Exception:
                    pass

            is_question_mode = analysis_type.startswith("🔢")

            st.markdown(
                f"""
                <div style='background:#1e293b;border:1px solid #334155;
                border-radius:10px;padding:16px;margin-bottom:12px;'>
                <b>📄 {uploaded.name}</b><br>
                <small style='color:#94a3b8;'>크기: {file_size_mb:.1f} MB
                {'| 총 ' + str(page_count) + ' 페이지' if page_count else ''}
                {'| 🔢 문제별 풀이 모드' if is_question_mode else ''}</small>
                </div>
                """,
                unsafe_allow_html=True,
            )

            btn_label = "🔢 문제 추출 & 풀이 시작" if is_question_mode else "🔍 PDF 분석 시작"
            if st.button(btn_label, key="btn_pdf_analyze", use_container_width=True):
                _run_pdf_analysis(
                    file_bytes, uploaded.name, page_count,
                    analysis_type, custom_question, page_range,
                    provider, model, api_key,
                    user_mode=st.session_state.get("user_mode", "교육자용")
                )
        else:
            st.markdown(
                """
                <div style='background:#0f172a;border:2px dashed #334155;
                border-radius:12px;padding:40px;text-align:center;color:#64748b;'>
                <div style='font-size:3rem;margin-bottom:12px;'>📑</div>
                <b>PDF 파일을 왼쪽에 업로드하세요</b><br>
                <small>시험지·교재·학습자료 등 지원</small>
                </div>
                """,
                unsafe_allow_html=True,
            )
            with st.expander("ℹ️ PDF 분석 안내", expanded=True):
                max_p = get_max_pdf_pages(provider)
                st.markdown(f"""
**🔢 문제별 개별 풀이 (권장)**
- PDF에서 문제를 자동 감지해 목록 생성 → 개별 풀이
- 컨텍스트 제한 우회로 정확도 대폭 향상

**📄 일반 분석 모드**
- 요약 / 핵심 개념 / 노트 생성 등 수행
- 비전 분석 시 최대 **{max_p}페이지** 지원 (로컬 {LOCAL_PDF_MAX_PAGES} / 클라우드 {CLOUD_PDF_MAX_PAGES})
""")

    # ── 일반 분석 결과 출력 ──────────────────────────────────────────
    _render_pdf_general_result()


def _run_pdf_analysis(
    file_bytes: bytes,
    filename: str,
    page_count: int,
    analysis_type: str,
    custom_question: str,
    page_range: str,
    provider: str,
    model: str,
    api_key: str,
    user_mode: str = "교육자용",
) -> None:
    """PDF 분석 실행: 문제별 모드와 일반 모드로 분기."""
    st.session_state.pdf_user_mode_final = user_mode

    # ── 공통: 텍스트/이미지 추출 ────────────────────────────────
    with st.status("📄 PDF 내용 추출 중...", expanded=True) as status:
        st.write("📝 텍스트 추출 시도 중...")
        content_text, images_b64, method = _pdf_extract_content(
            file_bytes, page_count, page_range
        )
        if method == "text":
            st.write(f"✅ 텍스트 추출 완료 ({len(content_text):,}자)")
        elif method == "vision":
            st.write(f"🖼️ 이미지 변환 완료 ({len(images_b64)}페이지)")
        else:
            st.write("⚠️ 텍스트 품질 낮음, 가능한 범위에서 진행")

        # ── 문제별 풀이 모드 ─────────────────────────────────────
        if analysis_type.startswith("🔢"):
            st.write("🔍 AI가 문제 목록 추출 중...")

            q_system = (
                "당신은 시험지 분석 전문가입니다.\n"
                "제공된 문서에서 모든 시험/연습 문제를 찾아 정확히 반환하세요.\n"
                "반드시 아래 JSON 배열 형식만 출력하세요. 다른 텍스트는 금지입니다:\n"
                '[{"번호":"1","내용":"문제 전체 텍스트"},{"번호":"2","내용":"..."}]'
            )
            q_prompt = (
                "첨부된 문서(파일 또는 이미지)에서 기재된 모든 시험 문항이나 연습 문제를 찾아 "
                "JSON 배열 형식으로만 반환하세요. JSON 외의 부가적인 인사말이나 마크다운 설명은 일절 생략하세요.\n"
                "문제가 없다면 빈 배열 []을 반환하세요.\n\n"
            )
            if content_text:
                q_prompt += f"[문서 내용]\n{content_text[:100000]}"
            else:
                q_prompt += "[참고]: 문서 텍스트가 부족하여 첨부된 이미지를 대신 분석해야 합니다."

            debug_raw_responses = []
            try:
                questions = []
                images_list = images_b64 if images_b64 else []
                if images_list:
                    chunk_size = get_max_pdf_pages(provider)
                    for i in range(0, len(images_list), chunk_size):
                        chunk = images_list[i:i+chunk_size]
                        st.write(f"🔍 이미지에서 문제 목록 추출 중... ({i+1}~{min(i+chunk_size, len(images_list))}장)")
                        raw_qs = call_ai(q_system, q_prompt, provider, model, api_key, images_b64=chunk)
                        debug_raw_responses.append(raw_qs)
                        _, clean_qs = parse_thinking_response(raw_qs)
                        questions.extend(_parse_question_list(clean_qs or raw_qs))
                else:
                    raw_qs = call_ai(q_system, q_prompt, provider, model, api_key, images_b64=None)
                    debug_raw_responses.append(raw_qs)
                    _, clean_qs = parse_thinking_response(raw_qs)
                    questions = _parse_question_list(clean_qs or raw_qs)
            except Exception as e:
                st.error(f"❌ 문제 추출 실패: {e}")
                status.update(label="실패", state="error")
                return

            if not questions:
                with st.expander("🛠 디버그: AI 원본 응답 확인", expanded=True):
                    for idx, r in enumerate(debug_raw_responses):
                        st.text(f"--- Chunk {idx+1} Raw Output ---\n{r}")
                st.warning("⚠️ 문제를 감지하지 못했습니다. AI가 반환한 위 디버그 텍스트를 확인해주세요.")
                status.update(label="문제 미감지", state="error")
                return

            # 세션에 저장
            st.session_state.pdf_questions = questions
            st.session_state.pdf_solutions = {}
            st.session_state.pdf_content_text = content_text
            st.session_state.pdf_images_b64 = images_b64
            st.session_state.pdf_extraction_method = method
            st.session_state.pdf_filename = filename
            st.session_state.pop("pdf_solve_all", None)

            st.write(f"✅ {len(questions)}개 문제 감지 완료!")
            status.update(label=f"✅ {len(questions)}개 문제 감지!", state="complete", expanded=False)
            st.rerun()
            return

        # ── 일반 분석 모드 ────────────────────────────────────────
        type_label = analysis_type.split(" ", 1)[1]
        st.write(f"🤖 AI 분석 중 ({method})...")

        content_for_prompt = content_text or f"{filename}의 이미지를 분석해주세요."

        if analysis_type.startswith("🔍") and custom_question.strip():
            user_prompt = (
                f"다음 문서에 대해 [{user_mode}] 관점에서 질문에 답해주세요.\n\n"
                f"[질문]: {custom_question}\n\n[문서 내용]:\n{content_for_prompt}"
            )
        else:
            user_prompt = (
                f"다음 PDF 문서({filename})에 대해 [{user_mode}]을 위한 [{type_label}]을 수행해주세요.\n\n"
                f"[문서 내용]:\n{content_for_prompt}"
            )

        system = SYSTEM_PROMPTS["pdf_analyzer"]

        try:
            max_p = get_max_pdf_pages(provider)
            analysis_images = images_b64
            if images_b64 and len(images_b64) > max_p:
                st.warning(f"⚠️ 일반 분석 모드에서는 컨텍스트 제한으로 앞의 {max_p}장 이미지만 분석됩니다. 모든 페이지 문제를 추출하려면 '문제별 풀이' 모드를 활용하세요.")
                analysis_images = images_b64[:max_p]

            result = call_ai(system, user_prompt, provider, model, api_key,
                             images_b64=analysis_images)
            status.update(label="✅ 분석 완료!", state="complete", expanded=False)
            
            # 일반 결과 세션에 저장
            st.session_state.pdf_general_result = result
            st.session_state.pdf_general_method = method
            st.session_state.pdf_general_type = type_label
            st.session_state.pdf_filename = filename
            st.session_state.pdf_content_text = content_text
        except Exception as e:
            st.error(f"❌ AI 분석 오류: {e}")
            status.update(label="분석 실패", state="error")
            return

def _render_pdf_general_result() -> None:
    """PDF 일반 분석 결과를 UI에 표시하고 다운로드 버튼 지원"""
    if "pdf_general_result" not in st.session_state:
        return
        
    result = st.session_state.pdf_general_result
    method = st.session_state.pdf_general_method
    type_label = st.session_state.pdf_general_type
    filename = st.session_state.pdf_filename
    content_text = st.session_state.get("pdf_content_text", "")

    # 결과 출력
    badge_color = "#10b981" if method == "text" else "#f59e0b"
    badge_label = "📝 텍스트 추출" if method == "text" else "🖼️ 비전 AI"
    st.markdown(
        f'<span style="background:{badge_color}22;border:1px solid {badge_color};'
        f'border-radius:6px;padding:3px 10px;font-size:0.8rem;color:{badge_color};">'
        f'{badge_label}</span>',
        unsafe_allow_html=True,
    )
    mode = st.session_state.get("user_mode", "교육자용")
    st.subheader(f"📋 {type_label} 결과 ({mode})")
    
    # 생각 과정 제거 후 본문만 렌더링
    _, final_content = parse_thinking_response(result)
    st.markdown(final_content)

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        _, final_md = parse_thinking_response(result)
        suffix = "educator" if "교육자" in mode else "student"
        st.download_button("💾 결과 저장 (.md)", data=final_md.encode('utf-8-sig'),
                           file_name=f"analysis_{suffix}.md", mime="text/markdown",
                           key="dl_pdf_md_gen", use_container_width=True)
    with col_b:
        pdf_bytes = make_pdf_bytes(result)
        if pdf_bytes:
            st.download_button("💾 결과 저장 (.pdf)", data=pdf_bytes,
                               file_name=f"analysis_{suffix}.pdf", mime="application/pdf",
                               key="dl_pdf_pdf_gen", use_container_width=True)
    with col_c:
        if method == "text" and content_text:
            st.download_button("💾 추출 텍스트 저장 (.txt)", data=content_text.encode('utf-8-sig'),
                               file_name="extracted_text.txt", mime="text/plain",
                               key="dl_pdf_txt_gen", use_container_width=True)







def render_code_analyzer() -> None:
    """💻 기능 6: 프로그래밍 코드 분석기"""
    provider, model, api_key = get_session_config()
    st.header("💻 프로그래밍 코드 분석기")
    st.caption("프로그래밍 코드를 업로드하거나 입력하면 AI가 상세 분석 및 최적화를 도와줍니다.")

    col1, col2 = st.columns([1, 1])
    with col1:
        uploaded = st.file_uploader("코드 파일 업로드", type=["py", "java", "cpp", "c", "js", "html", "css", "ts"],
                                    key="code_analyzer_upload")
        manual_code = st.text_area("또는 직접 코드 입력", height=250, placeholder="여기에 코드를 복사해 넣으세요.",
                                   key="code_manual_input")
        extra_info = st.text_area("추가 지시사항 (선택)",
                                   placeholder="예: 이 코드의 시간 복잡도를 계산해줘.",
                                   key="code_extra_info", height=100)
    
    with col2:
        if st.button("🔍 코드 분석 시작", key="btn_code_analyze", use_container_width=True):
            code_to_analyze = ""
            if uploaded:
                code_to_analyze = uploaded.getvalue().decode("utf-8")
            elif manual_code.strip():
                code_to_analyze = manual_code
            
            if not code_to_analyze.strip():
                st.warning("⚠️ 분석할 코드를 입력하거나 파일을 업로드하세요.")
                return
            
            user_prompt = f"다음 프로그래밍 코드를 분석해주세요:\n\n```\n{code_to_analyze}\n```"
            if extra_info.strip():
                user_prompt += f"\n\n추가 지시사항: {extra_info}"
            
            user_mode = st.session_state.get("user_mode", "👨‍🎓 수강생용")
            full_prompt = f"[{user_mode}을 위한 코드 분석]\n\n{user_prompt}"

            try:
                with st.spinner("🤖 AI가 코드를 분석하고 최적화 방안을 찾는 중..."):
                    result = call_ai(SYSTEM_PROMPTS["code_analyzer"],
                                     full_prompt, provider, model, api_key)
                st.session_state.code_analyzer_result = result
            except Exception as e:
                st.error(f"❌ {e}")

        if st.session_state.get("code_analyzer_result"):
            st.subheader("📋 분석 결과")
            st.markdown(st.session_state.code_analyzer_result)
            
            dl_col1, dl_col2 = st.columns([1, 1])
            base_name = "code_analysis"
            if uploaded:
                base_name = os.path.splitext(uploaded.name)[0]
            base_name = safe_filename(base_name)
            
            with dl_col1:
                st.download_button("💾 분석 결과 저장 (.md)", data=st.session_state.code_analyzer_result.encode('utf-8-sig'),
                                   file_name=f"{base_name}_analysis.md", mime="text/markdown",
                                   key="dl_code_md", use_container_width=True)
            with dl_col2:
                pdf_bytes = make_pdf_bytes(st.session_state.code_analyzer_result)
                if pdf_bytes:
                    st.download_button("💾 분석 결과 저장 (.pdf)", data=pdf_bytes,
                                       file_name=f"{base_name}_analysis.pdf", mime="application/pdf",
                                       key="dl_code_pdf", use_container_width=True)
def render_feedback_form() -> None:
    """📬 기능 7: 피드백 보내기"""
    st.header("📬 피드백 보내기")
    st.markdown("""
    앱 사용 중 불편한 점이나 기능 제안, 버그 제보 등 소중한 의견을 남겨주세요. 
    보내주신 의견은 서비스 개선에 적극 반영하겠습니다. 💎
    """)

    with st.container(border=True):
        st.markdown("### ✍️ 피드백 작성")
        fb_type = st.selectbox("피드백 유형", ["🐞 버그 제보", "💡 기능 제안", "📝 개선 의견", "❓ 기타"], key="fb_type")
        fb_content = st.text_area("내용", placeholder="이곳에 내용을 입력해주세요...", height=200, key="fb_content")
        
        email_to = "dlrlwjd1127@gmail.com"
        subject = f"[AI 통합 학습 도우미 피드백] {fb_type}"
        body = f"피드백 유형: {fb_type}\n\n내용:\n{fb_content}"
        
        # URL 인코딩
        import urllib.parse
        mailto_url = f"mailto:{email_to}?subject={urllib.parse.quote(subject)}&body={urllib.parse.quote(body)}"

        if st.button("🚀 피드백 발송 (이메일 앱 열기)", key="btn_feedback", use_container_width=True):
            if not fb_content.strip():
                st.warning("⚠️ 내용을 입력해주세요.")
            else:
                st.markdown(f'<a href="{mailto_url}" target="_blank" id="send_feedback_link" style="display:none;">Send</a>', unsafe_allow_html=True)
                # 자바스크립트를 이용해 클릭 효과
                st.components.v1.html(f"""
                    <script>
                        window.location.href = "{mailto_url}";
                    </script>
                """, height=0)
                st.success("✅ 메일 프로그램이 실행됩니다. 전송 버튼을 눌러 피드백을 완료해주세요!")

    st.info(f"📧 직접 메일을 보내시려면 **{email_to}**로 보내주셔도 좋습니다.")
