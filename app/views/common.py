import streamlit as st
import io
from src.config import P, _PDF_MAX_IMAGE_PAGES_LOCAL, _PDF_MAX_IMAGE_PAGES_CLOUD

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

def get_max_pdf_pages(provider: str) -> int:
    """Provider에 따른 PDF 이미지 변환 최대 페이지 수 반환"""
    if provider in [P.LMSTUDIO, P.OLLAMA, P.WEBLLM]:
        return _PDF_MAX_IMAGE_PAGES_LOCAL
    return _PDF_MAX_IMAGE_PAGES_CLOUD

def get_session_config() -> tuple[str, str, str, str]:
    return (
        st.session_state.get("provider", P.LMSTUDIO),
        st.session_state.get("model", ""),
        st.session_state.get("api_key", ""),
        st.session_state.get("user_mode", "👨‍🎓 학생 모드"),
    )
