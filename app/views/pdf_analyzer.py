import streamlit as st
import os
import io
from .common import get_session_config, get_max_pdf_pages, _PYPDF_OK, _FITZ_OK
from src.config import P
from src.prompts.system_prompts import get_system_prompt
from src.models import call_ai
from src.app_utils import encode_image_to_base64, generate_pdf_bytes, parse_thinking_response, _pdf_extract_content, _parse_question_list, safe_filename

if _PYPDF_OK:
    import pypdf

def _render_question_solver_ui(
    provider: str, model: str, api_key: str, mode: str,
) -> None:
    questions: list[dict] = st.session_state.get("pdf_questions", [])
    solutions: dict = st.session_state.setdefault("pdf_solutions", {})
    content_text: str = st.session_state.get("pdf_content_text", "")
    images_b64 = st.session_state.get("pdf_images_b64", None)
    method = st.session_state.get("pdf_extraction_method", "text")
    filename = st.session_state.get("pdf_filename", "문서")

    if not questions:
        return

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

    if st.session_state.get("pdf_solve_all"):
        unsolved = [i for i in range(len(questions)) if i not in solutions]
        if unsolved:
            prog = st.progress(0, text="전체 풀이 진행 중...")
            for step, idx in enumerate(unsolved):
                q = questions[idx]
                prog.progress((step + 1) / len(unsolved),
                               text=f"문제 {q['번호']} 풀이 중... ({step+1}/{len(unsolved)})")
                sol = _solve_single_question(
                    q, content_text, images_b64, provider, model, api_key, filename, mode
                )
                solutions[idx] = sol
            prog.empty()
        st.session_state.pdf_solve_all = False
        st.rerun()

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
                        q, content_text, images_b64, provider, model, api_key, filename, mode
                    )
                solutions[i] = sol
                st.rerun()

        if solved:
            with st.expander(f"📐 문제 {q['번호']} 풀이 보기", expanded=True):
                st.markdown(solutions[i])
                orig_name = st.session_state.get("pdf_filename", "pdf")
                base_name = os.path.splitext(orig_name)[0]
                q_filename = safe_filename(f"{i+1}_{base_name}_Q{i+1}")

                dl_col1, dl_col2 = st.columns([1, 1])
                with dl_col1:
                    _, final_sol = parse_thinking_response(solutions[i])
                    st.download_button("💾 MD 저장", data=final_sol.encode('utf-8-sig'),
                                       file_name=f"{q_filename}.md", mime="text/markdown",
                                       key=f"dl_sol_{i}", use_container_width=True)
                with dl_col2:
                    pdf_bytes = generate_pdf_bytes(solutions[i])
                    if pdf_bytes:
                        st.download_button("💾 PDF 저장", data=pdf_bytes,
                                           file_name=f"{q_filename}.pdf", mime="application/pdf",
                                           key=f"dl_sol_pdf_{i}", use_container_width=True)

        st.markdown("</div>", unsafe_allow_html=True)

    if solutions:
        all_sols = "\n\n---\n\n".join(
            f"## 문제 {questions[i]['번호']}\n{questions[i]['내용']}\n\n### 풀이\n{sol}"
            for i, sol in sorted(solutions.items())
        )
        orig_name = st.session_state.get("pdf_filename", "pdf")
        base_name = os.path.splitext(orig_name)[0]
        all_filename = safe_filename(f"{base_name}_전체풀이")

        col1, col2 = st.columns(2)
        with col1:
            _, final_all = parse_thinking_response(all_sols)
            st.download_button("💾 전체 풀이 저장 (.md)", data=final_all.encode('utf-8-sig'),
                               file_name=f"{all_filename}.md", mime="text/markdown",
                               key="dl_all_solutions", use_container_width=True)
        with col2:
            pdf_bytes = generate_pdf_bytes(all_sols)
            if pdf_bytes:
                st.download_button("💾 전체 풀이 저장 (.pdf)", data=pdf_bytes,
                                   file_name=f"{all_filename}.pdf", mime="application/pdf",
                                   key="dl_all_solutions_pdf", use_container_width=True)

def _solve_single_question(
    q: dict, content_text: str, images_b64: list[str] | None,
    provider: str, model: str, api_key: str, filename: str, mode: str,
) -> str:
    context = ""
    if content_text:
        needle = q["내용"][:50]
        idx = content_text.find(needle)
        if idx >= 0:
            start = max(0, idx - 500)
            end = min(len(content_text), idx + 2000)
            context = content_text[start:end]
        else:
            context = content_text[:3000]

    system = get_system_prompt("step_solver", mode)
    if provider == P.LMSTUDIO:
        system = "<|think|>\n" + system

    user_prompt = f"[문서: {filename}]\n\n**문제 {q['번호']}번**\n{q['내용']}\n\n"
    if context:
        user_prompt += f"[문서 내 관련 컨텍스트]\n{context}\n\n"
    user_prompt += "이 문제를 단계별로 자세히 풀어주세요."

    return call_ai(system, user_prompt, provider, model, api_key,
                   images_b64=images_b64 if not context else None)

def _run_pdf_analysis(
    file_bytes: bytes, filename: str, page_count: int,
    analysis_type: str, custom_question: str, page_range: str,
    provider: str, model: str, api_key: str, mode: str,
) -> None:
    is_question_mode = analysis_type.startswith("🔢")

    with st.status("📄 PDF 내용 추출 중...", expanded=True) as status:
        st.write("📝 텍스트 추출 시도 중...")
        max_pg = get_max_pdf_pages(provider)
        extracted_text, images_b64, method = _pdf_extract_content(
            file_bytes, page_count, page_range, max_pages=max_pg
        )
        if method == "text":
            st.write(f"✅ 텍스트 추출 완료 ({len(extracted_text):,}자)")
        elif method == "vision":
            st.write(f"🖼️ 이미지 변환 완료 ({len(images_b64)}페이지)")
        
        st.session_state.pdf_content_text = extracted_text
        st.session_state.pdf_images_b64 = images_b64
        st.session_state.pdf_extraction_method = method
        st.session_state.pdf_filename = filename

        if is_question_mode:
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
            if extracted_text:
                q_prompt += f"[문서 내용]\n{extracted_text[:100000]}"
            else:
                q_prompt += "[참고]: 문서 텍스트가 부족하여 첨부된 이미지를 대신 분석해야 합니다."

            questions = []
            images_list = images_b64 if images_b64 else []
            if images_list:
                chunk_size = get_max_pdf_pages(provider)
                for i in range(0, len(images_list), chunk_size):
                    chunk = images_list[i:i+chunk_size]
                    st.write(f"🔍 이미지에서 문제 목록 추출 중... ({i+1}~{min(i+chunk_size, len(images_list))}장)")
                    raw_qs = call_ai(q_system, q_prompt, provider, model, api_key, images_b64=chunk)
                    _, clean_qs = parse_thinking_response(raw_qs)
                    questions.extend(_parse_question_list(clean_qs or raw_qs))
            else:
                raw_qs = call_ai(q_system, q_prompt, provider, model, api_key)
                _, clean_qs = parse_thinking_response(raw_qs)
                questions.extend(_parse_question_list(clean_qs or raw_qs))
            
            st.session_state.pdf_questions = questions
            st.session_state.pdf_solutions = {}
            st.write(f"✅ {len(questions)}개 문제 감지 완료!")
            status.update(label=f"✅ {len(questions)}개 문제 감지!", state="complete", expanded=False)
            st.rerun()
        else:
            type_label = analysis_type.split(" ", 1)[1]
            st.write(f"🤖 AI 분석 중 ({method})...")
            content_for_prompt = extracted_text or f"{filename}의 이미지를 분석해주세요."
            if analysis_type.startswith("🔍") and custom_question.strip():
                user_prompt = f"다음 문서에 대해 질문에 답해주세요.\n\n[질문]: {custom_question}\n\n[문서 내용]:\n{content_for_prompt}"
            else:
                user_prompt = f"다음 PDF 문서({filename})에 대해 [{type_label}]을 수행해주세요.\n\n[문서 내용]:\n{content_for_prompt}"

            system = get_system_prompt("pdf_analyzer", mode)
            try:
                analysis_images = images_b64[:max_pg] if images_b64 else None
                result = call_ai(system, user_prompt, provider, model, api_key, images_b64=analysis_images)
                st.session_state.pdf_general_result = result
                st.session_state.pdf_general_method = method
                st.session_state.pdf_general_type = type_label
                status.update(label="✅ 분석 완료!", state="complete", expanded=False)
                st.rerun()
            except Exception as e:
                st.error(f"❌ 분석 실패: {e}")
                status.update(label="분석 실패", state="error")

def _render_pdf_general_result() -> None:
    if "pdf_general_result" not in st.session_state:
        return
    result = st.session_state.pdf_general_result
    method = st.session_state.pdf_general_method
    type_label = st.session_state.pdf_general_type
    content_text = st.session_state.get("pdf_content_text", "")

    badge_color = "#10b981" if method == "text" else "#f59e0b"
    badge_label = "📝 텍스트 추출" if method == "text" else "🖼️ 비전 AI"
    st.markdown(f'<span style="background:{badge_color}22;border:1px solid {badge_color};border-radius:6px;padding:3px 10px;font-size:0.8rem;color:{badge_color};">{badge_label}</span>', unsafe_allow_html=True)
    st.subheader(f"📋 {type_label} 결과")
    st.markdown(result)

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        _, final_md = parse_thinking_response(result)
        st.download_button("💾 결과 저장 (.md)", data=final_md.encode('utf-8-sig'), file_name="pdf_analysis_result.md", mime="text/markdown", key="dl_pdf_md_gen", use_container_width=True)
    with col_b:
        pdf_bytes = generate_pdf_bytes(result)
        if pdf_bytes:
            st.download_button("💾 결과 저장 (.pdf)", data=pdf_bytes, file_name="pdf_analysis_result.pdf", mime="application/pdf", key="dl_pdf_pdf_gen", use_container_width=True)
    with col_c:
        if method == "text" and content_text:
            st.download_button("💾 추출 텍스트 저장 (.txt)", data=content_text.encode('utf-8-sig'), file_name="extracted_text.txt", mime="text/plain", key="dl_pdf_txt_gen", use_container_width=True)
    
    if st.button("🗑️ 결과 지우기", key="clear_pdf_general", use_container_width=True):
        st.session_state.pop("pdf_general_result", None)
        st.rerun()

def render_pdf_analyzer() -> None:
    provider, model, api_key, mode = get_session_config()
    st.header("📑 PDF 문서 분석기")
    st.caption("시험지·교재 PDF 업로드 → 문제 자동 감지 → 문제별 개별 풀이")

    if not _PYPDF_OK and not _FITZ_OK:
        st.error("❌ PDF 처리 라이브러리가 없습니다. `pip install pypdf pymupdf`를 실행하세요.")
        return

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
        _render_question_solver_ui(provider, model, api_key, mode)
        return

    col1, col2 = st.columns([1, 1])
    with col1:
        uploaded = st.file_uploader("PDF 파일 업로드 (최대 50MB)", type=["pdf"], key="pdf_upload")
        analysis_type = st.selectbox("분석 유형", [
            "🔢 문제별 개별 풀이  ← 권장 (컨텍스트 제한 우회)", "📋 전체 내용 요약",
            "🔑 핵심 개념 및 키워드 추출", "📝 학습 자료 / 노트 생성", "🔍 특정 내용 질의응답"
        ], key="pdf_analysis_type")
        custom_question = ""
        if analysis_type.startswith("🔍"):
            custom_question = st.text_area("질문 입력", placeholder="요약해줘.", height=100, key="pdf_question")
        page_range = st.text_input("분석할 페이지 범위 (선택, 비워두면 전체)", placeholder="예: 1-10", key="pdf_page_range")

    with col2:
        if uploaded:
            file_bytes = uploaded.read()
            file_size_mb = len(file_bytes) / 1_048_576
            page_count = 0
            if _PYPDF_OK:
                try:
                    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
                    page_count = len(reader.pages)
                except Exception: pass
            is_question_mode = analysis_type.startswith("🔢")
            st.markdown(f"""
                <div style='background:#1e293b;border:1px solid #334155;border-radius:10px;padding:16px;margin-bottom:12px;'>
                <b>📄 {uploaded.name}</b><br>
                <small style='color:#94a3b8;'>크기: {file_size_mb:.1f} MB {'| 총 ' + str(page_count) + ' 페이지' if page_count else ''}</small>
                </div>
            """, unsafe_allow_html=True)

            btn_label = "🔢 문제 추출 & 풀이 시작" if is_question_mode else "🔍 PDF 분석 시작"
            if st.button(btn_label, key="btn_pdf_analyze", use_container_width=True):
                _run_pdf_analysis(file_bytes, uploaded.name, page_count, analysis_type, custom_question, page_range, provider, model, api_key, mode)
        else:
            st.markdown(f"""
                <div style='background:#0f172a;border:2px dashed #334155;border-radius:12px;padding:40px;text-align:center;color:#64748b;'>
                <div style='font-size:3rem;margin-bottom:12px;'>📑</div><b>PDF 파일을 왼쪽에 업로드하세요</b></div>
            """, unsafe_allow_html=True)
            with st.expander("ℹ️ 문제별 풀이 모드 안내", expanded=True):
                st.markdown(f"""
**🔢 문제별 개별 풀이 (권장)**
- PDF에서 문제를 자동 감지해 목록 생성
- 문제 하나씩 AI에 요청 → **컨텍스트 제한 우회**
- 전체 풀이 한 번에 가능

**📄 일반 분석 모드**
- 비전 처리 시 최대 **{get_max_pdf_pages(provider)}페이지** 분석
""")

    _render_pdf_general_result()
