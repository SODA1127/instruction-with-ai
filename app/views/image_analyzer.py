import streamlit as st
import os
from .common import get_session_config
from src.config import P
from src.prompts.system_prompts import get_system_prompt
from src.models import call_ai
from src.app_utils import encode_image_to_base64, make_pdf_bytes, safe_filename

def render_image_analyzer() -> None:
    """📸 기능 1: 이미지 기반 문제 분석기"""
    provider, model, api_key, mode = get_session_config()
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
            type_label = analysis_type.split(" ", 1)[1]
            user_prompt = f"다음 이미지에 대해 [{type_label}]을 수행해주세요."
            if extra_info.strip():
                user_prompt += f"\n\n추가 지시: {extra_info}"
            try:
                with st.spinner("🤖 AI가 이미지를 분석하는 중..."):
                    b64 = encode_image_to_base64(uploaded)
                    system = get_system_prompt("image_analyzer", mode)
                    if provider == P.LMSTUDIO:
                        system = "<|think|>\n" + system
                    result = call_ai(system,
                                     user_prompt, provider, model, api_key,
                                     images_b64=[b64])
                st.session_state.img_analyzer_result = result
            except Exception as e:
                st.error(f"❌ {e}")

        if st.session_state.get("img_analyzer_result"):
            st.subheader("📋 분석 결과")
            st.markdown(st.session_state.img_analyzer_result)
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
