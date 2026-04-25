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
import src.app_utils as app_utils

def get_session_config() -> tuple[str, str, str]:
    return (
        st.session_state.get("provider", P.LMSTUDIO),
        st.session_state.get("model", ""),
        st.session_state.get("api_key", ""),
    )

# ────────────────────────────────────────────────────────────
# 기능 렌더링
# ────────────────────────────────────────────────────────────



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
            img_b64 = app_utils.encode_image_to_base64(up)
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
                extracted_text, extracted_images, extr_method = app_utils._pdf_extract_content(file_bytes, page_count, "")
                if extr_method == "text" and extracted_text.strip():
                    problem_text = extracted_text
                else:
                    img_list = extracted_images if extracted_images else None
                    if img_list and len(img_list) > 1:
                        img_list = img_list[:1] # 한문제만 풀이하므로 첫장만
                    problem_text = "업로드된 PDF 문서 첫 페이지의 문제를 단계별로 풀어주세요."

        user_mode = st.session_state.get("user_mode", "👨‍🎓 수강생용")
        full_user_prompt = f"[{user_mode}을 위한 풀이]\n\n{problem_text}"

        try:
            with st.spinner("🤔 AI가 문제를 풀고 있습니다..."):
                result = call_ai(SYSTEM_PROMPTS["step_solver"], full_user_prompt, provider, model, api_key,
                                 images_b64=img_list)
            thinking, final = app_utils.parse_thinking_response(result)
            st.session_state.step_solver_thinking = thinking
            st.session_state.step_solver_final = final
            st.session_state.step_solver_result = result
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
        st.markdown(final, unsafe_allow_html=True)
        
        # 파일명 접두어 준비
        base_name = "problem_solution"
        if st.session_state.get("solver_img_upload"):
            base_name = os.path.splitext(st.session_state.solver_img_upload.name)[0]
        elif st.session_state.get("solver_pdf_upload"):
            base_name = os.path.splitext(st.session_state.solver_pdf_upload.name)[0]
        base_name = app_utils.safe_filename(base_name)

        dl_col1, dl_col2 = st.columns([1, 1])
        with dl_col1:
            st.download_button("💾 풀이 저장 (.md)", data=final.encode('utf-8-sig'),
                               file_name=f"{base_name}.md", mime="text/markdown",
                               key="download_step_solver_md", use_container_width=True)
        with dl_col2:
            current_result = st.session_state.get("step_solver_result", "")
            pdf_bytes = app_utils.make_pdf_bytes(st.session_state.step_solver_result) # make_pdf_bytes performs internal parsing
            if pdf_bytes:
                st.download_button("💾 풀이 저장 (.pdf)", data=pdf_bytes,
                                   file_name=f"{base_name}.pdf", mime="application/pdf",
                                   key="download_step_solver_pdf", use_container_width=True)

