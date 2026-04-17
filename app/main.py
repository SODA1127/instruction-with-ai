from __future__ import annotations
import sys
import os

# 프로젝트 루트를 sys.path의 최우선 순위로 설정하여 다른 프로젝트(src)와의 충돌 방지
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import streamlit as st
import src
from src.config import (
    P, PROVIDER_KEY_HINTS, PROVIDER_MODELS, LMSTUDIO_PREFERRED,
    get_max_pdf_pages, LOCAL_PDF_MAX_PAGES, CLOUD_PDF_MAX_PAGES
)
from src.models import check_lmstudio_connection, check_ollama_connection
from app.pages import (
    render_image_analyzer, render_step_solver, render_lesson_plan,
    render_quiz_generator, render_chatbot, render_pdf_analyzer,
    render_code_analyzer
)

CUSTOM_MODEL_OPTION = "✍️ 직접 입력..."

def render_sidebar() -> str:
    """사이드바 렌더링 및 프로바이더 설정."""
    with st.sidebar:
        st.markdown('<div class="app-title">🎓 AI 통합 학습 도우미</div>', unsafe_allow_html=True)
        st.markdown('<div class="app-subtitle">교육자와 학생을 위한 멀티 AI 학습 플랫폼</div>', unsafe_allow_html=True)
        st.divider()

        feature = st.radio("🔧 기능 선택", [
            "📸 이미지 문제 분석기", "📑 PDF 문서 분석기", "🧠 단계별 풀이 생성기",
            "📄 교안 생성기", "📝 평가문항 생성기", "💻 프로그래밍 코드 분석기", "💬 교육 상담 챗봇",
        ], key="selected_feature")

        st.divider()
        st.markdown("**🎓 수강 대상 모드**")
        st.radio("수강 대상", 
                 ["👩‍🏫 교육자용 (상세 해설, 교수법 포함)", "👨‍🎓 수강생용 (쉬운 개념 풀이, 학습 팁 포함)"], 
                 key="user_mode", label_visibility="collapsed")

        st.divider()
        st.markdown("**🌐 AI 프로바이더 선택**")
        st.radio("AI 프로바이더", P.ALL, key="provider", label_visibility="collapsed")
        provider = st.session_state.provider

        st.divider()

        if provider == P.LMSTUDIO:
            _render_local_service_config(provider, "LM Studio", 1234, check_lmstudio_connection)
        elif provider == P.OLLAMA:
            _render_local_service_config(provider, "Ollama", 11434, check_ollama_connection)
        elif provider == P.WEBLLM:
            _render_webllm_config()
        else:
            _render_cloud_config(provider)

        st.divider()

        # ── 제작 동기 ────────────────────────────────────────
        st.markdown(
            """
            <div style="background: rgba(129,140,248,.1); padding: 12px; border-radius: 10px; border: 1px solid rgba(129,140,248,.2); margin-bottom: 15px;">
                <div style="font-weight: 700; color: #818cf8; font-size: 0.85rem; margin-bottom: 5px;">🎯 제작 동기</div>
                <div style="font-size: 0.78rem; color: #cbd5e1; line-height: 1.5; font-style: italic;">
                    "대학교 1학년으로서 전공 지식을 깊이 있게 공부하는 과정에서, 학생의 눈높이에서 복잡한 수식과 개념을 친절하게 설명해 주는 AI 비서가 우리 모두에게 필요하다는 생각으로 시작하게 되었습니다."
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
        st.markdown(
            f"""
            <div style="font-size: 0.82rem; color: #94a3b8; line-height: 1.6;">
                <div style="font-weight: 700; color: #f8fafc; margin-bottom: 4px;">👨‍💻 Developer</div>
                <div><b>SODA1127</b> (아주대 융합시스템공학과 202620426 이기정)</div>
                <div style="margin-top: 8px;">
                    <a href="mailto:dlrlwjd1127@gmail.com" style="text-decoration:none;">📧 Email</a> | 
                    <a href="https://github.com/soda1127" target="_blank" style="text-decoration:none;">🐙 GitHub</a>
                </div>
                <div style="margin-top: 12px; margin-bottom: 12px;">
                    <a href="https://www.buymeacoffee.com/dlrlwjd112u" target="_blank">
                        <img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" style="height: 34px !important;width: 125px !important;" >
                    </a>
                </div>
                <div style="font-size: 0.72rem; border-top: 1px solid #334155; padding-top: 8px;">
                    © 2026 Kijung Lee. All rights reserved.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    return feature


def _render_local_service_config(provider: str, name: str, port: int, check_func) -> None:
    """LM Studio / Ollama 공통 설정 패널."""
    st.markdown(f"**⚙️ {name} 연결**")

    state_key = f"{provider}_state"
    if (state_key not in st.session_state or st.sidebar.button("🔄 새로고침", key=f"refresh_{provider}")):
        with st.spinner(f"{name} 연결 확인 중..."):
            ok, default_model, all_models = check_func()
        st.session_state[state_key] = {"ok": ok, "default": default_model, "models": all_models}

    info = st.session_state[state_key]
    if info["ok"]:
        st.markdown(f'<div class="status-badge status-ok">🟢 {name} 연결됨 (Port {port})</div>', unsafe_allow_html=True)
        options = info["models"] + [CUSTOM_MODEL_OPTION]
        
        sel = st.selectbox("모델 선택", options, key=f"sel_{provider}")
        if sel == CUSTOM_MODEL_OPTION:
            model = st.text_input("모델명 직접 입력", placeholder="예: gemma:latest", key=f"custom_{provider}")
            st.session_state.model = model
        else:
            st.session_state.model = sel
    else:
        st.markdown(f'<div class="status-badge status-err">🔴 {name} 연결 안됨</div>', unsafe_allow_html=True)
        st.warning(f"{name}를 실행하고 모델을 로드한 후 '새로고침'을 눌러주세요.")
        model = st.text_input("수동 모델 지정", placeholder="gemma", key=f"manual_{provider}")
        st.session_state.model = model
    st.session_state.api_key = ""


def _render_webllm_config() -> None:
    """WebLLM 설정 패널."""
    st.markdown("**🌐 WebLLM 설정**")
    st.info("WebLLM은 브라우저 리소스를 사용합니다. 첫 로딩 시 시간이 소요될 수 있습니다.")
    models = PROVIDER_MODELS[P.WEBLLM] + [CUSTOM_MODEL_OPTION]
    sel = st.selectbox("모델 선택", models, key="sel_webllm")
    
    if sel == CUSTOM_MODEL_OPTION:
        st.session_state.model = st.text_input("모델명 입력", key="custom_webllm")
    else:
        st.session_state.model = sel
    st.session_state.api_key = ""


def _render_cloud_config(provider: str) -> None:
    """OpenAI / Gemini / Claude 공통 설정 패널."""
    hint_url, hint_prefix = PROVIDER_KEY_HINTS[provider]
    provider_full_name = provider.split(" ", 1)[1]

    st.markdown(f"**🔑 {provider_full_name} API 키**")
    session_key = f"api_key_{provider}"
    saved_key = st.session_state.get(session_key, "")

    api_key = st.text_input("API 키 입력", value=saved_key, type="password", key=f"api_key_input_{provider}", label_visibility="collapsed")
    st.markdown(f"<small>🔗 <a href='{hint_url}' target='_blank'>발급받기</a></small>", unsafe_allow_html=True)

    if api_key:
        st.session_state[session_key] = api_key
        st.session_state.api_key = api_key
    else:
        st.session_state.api_key = ""

    st.markdown("**🤖 모델 선택**")
    models = PROVIDER_MODELS[provider] + [CUSTOM_MODEL_OPTION]
    sel = st.selectbox("모델", models, key=f"sel_cloud_{provider}", label_visibility="collapsed")
    
    if sel == CUSTOM_MODEL_OPTION:
        model = st.text_input("모델명 직접 입력", key=f"custom_cloud_{provider}")
        st.session_state.model = model
    else:
        st.session_state.model = sel

    if api_key:
        st.markdown('<div class="status-badge status-ok">🟢 설정 완료</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="status-badge status-err">🔴 API 키 필요</div>', unsafe_allow_html=True)


# ────────────────────────────────────────────────────────────
# 메인
# ────────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(
        page_title="AI 통합 학습 도우미",
        page_icon="🎓",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap');
    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif; }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0f172a 0%, #1e1b4b 100%);
    }
    [data-testid="stSidebar"] * { color: #e2e8f0 !important; }
    [data-testid="stSidebar"] a { color: #818cf8 !important; }

    .app-title {
        font-size: 1.6rem; font-weight: 700;
        background: linear-gradient(135deg, #818cf8, #c084fc, #f472b6);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        text-align: center; margin-bottom: 0.2rem;
    }
    .app-subtitle {
        font-size: 0.78rem; color: #94a3b8; text-align: center; margin-bottom: 0.8rem;
    }

    .status-badge {
        display: inline-flex; align-items: center; gap: 6px;
        padding: 5px 12px; border-radius: 999px;
        font-size: 0.78rem; font-weight: 600; margin-top: 6px;
    }
    .status-ok  { background: rgba(16,185,129,.15); border: 1px solid #10b981; color: #6ee7b7; }
    .status-err { background: rgba(239,68,68,.15);  border: 1px solid #ef4444; color: #fca5a5; }

    .stButton > button {
        background: linear-gradient(135deg, #4f46e5, #7c3aed);
        color: white; border: none; border-radius: 10px;
        padding: .6rem 1.2rem; font-weight: 600; font-size: .95rem;
        transition: all .2s ease;
    }
    .stButton > button:hover {
        background: linear-gradient(135deg, #4338ca, #6d28d9);
        transform: translateY(-1px); box-shadow: 0 4px 20px rgba(79,70,229,.4);
    }

    /* 프로바이더 라디오 강조 */
    [data-testid="stSidebar"] .stRadio > div { gap: 4px; }
    [data-testid="stSidebar"] .stRadio label {
        font-size: .9rem; padding: 4px 0; cursor: pointer;
    }
    </style>
    """, unsafe_allow_html=True)

    feature = render_sidebar()

    # 클라우드 프로바이더인데 API 키가 없을 경우 경고
    provider = st.session_state.get("provider", P.LMSTUDIO)
    api_key  = st.session_state.get("api_key", "")

    if provider != P.LMSTUDIO and not api_key:
        st.warning(
            f"⚠️ {provider} 사용을 위해 사이드바에서 API 키를 입력해주세요.\n\n"
            "API 키는 세션 동안만 메모리에 저장되며 어디에도 기록되지 않습니다.",
            icon="🔑"
        )

    # LM Studio인데 연결 안 됨
    if provider == P.LMSTUDIO and not st.session_state.get("lm_connected", True):
        st.error("⚠️ LM Studio에 연결할 수 없습니다. LM Studio를 실행하고 모델을 로드해주세요.")

    # 기능 라우팅
    if feature == "📸 이미지 문제 분석기":
        render_image_analyzer()
    elif feature == "📑 PDF 문서 분석기":
        render_pdf_analyzer()
    elif feature == "🧠 단계별 풀이 생성기":
        render_step_solver()
    elif feature == "📄 교안 생성기":
        render_lesson_plan()
    elif feature == "📝 평가문항 생성기":
        render_quiz_generator()
    elif feature == "💻 프로그래밍 코드 분석기":
        render_code_analyzer()
    elif feature == "💬 교육 상담 챗봇":
        render_chatbot()


if __name__ == "__main__":
    main()
