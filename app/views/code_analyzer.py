import streamlit as st
import os
from .common import get_session_config
from src.config import P
from src.prompts.system_prompts import get_system_prompt
from src.models import call_ai
from src.utils import make_pdf_bytes, parse_thinking_response, safe_filename

def render_code_analyzer() -> None:
    """💻 기능 6: 프로그래밍 코드 분석기"""
    provider, model, api_key, mode = get_session_config()
    st.header("💻 프로그래밍 코드 분석기")
    st.caption("프로그래밍 코드를 업로드하거나 입력하면 AI가 상세 분석 및 최적화를 도와줍니다.")

    col1, col2 = st.columns([1, 1])
    with col1:
        uploaded = st.file_uploader("코드 파일 업로드", type=["py", "java", "cpp", "js", "html", "css", "c", "h"],
                                    key="code_upload")
        manual_code = st.text_area("또는 코드 직접 입력", placeholder="여기에 코드를 복사해서 붙여넣으세요.",
                                   height=250, key="manual_code")
        extra_info = st.text_area("추가 지시사항 (선택)",
                                   placeholder="예: 이 코드의 시간 복잡도를 분석하고 최적화해줘.",
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
            
            system = get_system_prompt("code_analyzer", mode)
            if provider == P.LMSTUDIO:
                system = "<|think|>\n" + system
            try:
                with st.spinner("🤖 AI가 코드를 분석하고 최적화 방안을 찾는 중..."):
                    result = call_ai(system,
                                     user_prompt, provider, model, api_key)
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
                st.download_button("💾 결과 저장 (.md)", data=st.session_state.code_analyzer_result.encode('utf-8-sig'),
                                   file_name=f"{base_name}.md", mime="text/markdown",
                                   key="dl_code_md", use_container_width=True)
            with dl_col2:
                pdf_bytes = make_pdf_bytes(st.session_state.code_analyzer_result)
                if pdf_bytes:
                    st.download_button("💾 결과 저장 (.pdf)", data=pdf_bytes,
                                       file_name=f"{base_name}.pdf", mime="application/pdf",
                                       key="dl_code_pdf", use_container_width=True)
