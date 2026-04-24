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
            # user_prompt 정의 추가
            user_prompt = f"분석 유형: {analysis_type}\n추가 정보: {extra_info}"
            full_prompt = f"[{user_mode} 관점에서 분석]\n\n{user_prompt}"
            try:
                with st.spinner("🤖 AI가 이미지를 분석하는 중..."):
                    # app_utils. 필요
                    b64 = app_utils.encode_image_to_base64(uploaded)
                    result = call_ai(SYSTEM_PROMPTS["image_analyzer"],
                                     full_prompt, provider, model, api_key,
                                     images_b64=[b64])
                    st.session_state.img_analyzer_result = result
            except Exception as e:
                st.error(f"❌ {e}")

        if st.session_state.get("img_analyzer_result"):
            st.subheader("📋 분석 결과")
            # 생각 과정 제거 및 후처리 적용
            _, final_content = app_utils.parse_thinking_response(st.session_state.img_analyzer_result)
            st.markdown(final_content, unsafe_allow_html=True)
            dl_col1, dl_col2 = st.columns([1, 1])
            # 파일명 접두어 준비
            base_name = os.path.splitext(uploaded.name)[0] if uploaded else "image_analysis"
            # app_utils. 필요
            clean_base_name = app_utils.safe_filename(base_name)
            
            with dl_col1:
                st.download_button("💾 결과 저장 (.md)", data=st.session_state.img_analyzer_result.encode('utf-8-sig'),
                                   file_name=f"{clean_base_name}.md", mime="text/markdown",
                                   key="download_img_result_md", use_container_width=True)
            with dl_col2:
                pdf_bytes = app_utils.make_pdf_bytes(st.session_state.img_analyzer_result)
                if pdf_bytes:
                    st.download_button("💾 결과 저장 (.pdf)", data=pdf_bytes,
                                       file_name=f"{clean_base_name}.pdf", mime="application/pdf",
                                       key="download_img_result_pdf", use_container_width=True)

