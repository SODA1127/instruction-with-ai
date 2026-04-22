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
            st.markdown(st.session_state.code_analyzer_result, unsafe_allow_html=True)
            
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
                pdf_bytes = app_utils.make_pdf_bytes(st.session_state.code_analyzer_result)
                if pdf_bytes:
                    st.download_button("💾 분석 결과 저장 (.pdf)", data=pdf_bytes,
                                       file_name=f"{base_name}_analysis.pdf", mime="application/pdf",
                                       key="dl_code_pdf", use_container_width=True)