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
from src.app_utils import encode_image_to_base64, make_pdf_bytes, parse_thinking_response, _pdf_extract_content, _parse_question_list, safe_filename, parse_quiz_markdown

def get_session_config() -> tuple[str, str, str]:
    return (
        st.session_state.get("provider", P.LMSTUDIO),
        st.session_state.get("model", ""),
        st.session_state.get("api_key", ""),
    )

# ────────────────────────────────────────────────────────────
# 기능 렌더링
# ────────────────────────────────────────────────────────────



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
