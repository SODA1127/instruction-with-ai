import streamlit as st
from .common import get_session_config
from src.config import P
from src.prompts.system_prompts import get_system_prompt
from src.models import call_ai, stream_ai
from src.app_utils import parse_thinking_response

def render_chatbot() -> None:
    """💬 기능 5: 교육 상담 챗봇"""
    provider, model, api_key, mode = get_session_config()
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
                system = get_system_prompt("chatbot", mode)
                if provider == P.LMSTUDIO:
                    system = "<|think|>\n" + system

                resp = call_ai(system, user_input,
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
