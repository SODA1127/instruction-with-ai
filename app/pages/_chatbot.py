from __future__ import annotations
import streamlit as st
import os
import io
import json
import re
import base64

from src.config import P
from src.prompts.system_prompts import SYSTEM_PROMPTS
from src.models import call_ai, stream_ai
import src.app_utils as app_utils
from src.db_manager import db

def get_session_config() -> tuple[str, str, str]:
    return (
        st.session_state.get("provider", P.LMSTUDIO),
        st.session_state.get("model", ""),
        st.session_state.get("api_key", ""),
    )

# ────────────────────────────────────────────────────────────
# 기능 렌더링
# ────────────────────────────────────────────────────────────

def render_chatbot() -> None:
    """💬 기능 5: 교육 상담 챗봇"""
    provider, model, api_key = get_session_config()
    st.header("💬 교육 상담 챗봇")
    st.caption("교수법, 학생 지도, 학급 경영 등 어떤 고민이든 편하게 이야기하세요.")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    for msg in st.session_state.chat_history:
        avatar = "🎓" if msg["role"] == "assistant" else "🙋"
        with st.chat_message(msg["role"], avatar=avatar):
            # 출력 시에도 혹시 모를 전처리를 수행하여 가독성 확보
            _, clean_msg = app_utils.parse_thinking_response("<|channel>thought\n<channel|>" + msg["content"])
            st.markdown(clean_msg)

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
                user_mode = st.session_state.get("user_mode", "수강생용")
                full_input = f"[{user_mode}과 대화 중]\n{user_input}"
                
                resp = call_ai(SYSTEM_PROMPTS["chatbot"], full_input,
                               provider, model, api_key,
                               history=history, stream=True)
                full_response = stream_ai(resp, provider)
            except Exception as e:
                st.error(f"❌ {e}")
                full_response = ""

        # AI 응답에서 사고 과정 분리 및 클린징
        _, clean = app_utils.parse_thinking_response(full_response)
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": clean or full_response,
        })

        # --- [추가] 로그인 상태일 경우 DB에 대화 저장 ---
        if st.session_state.get("user"):
            user_id = st.session_state.user.get("sub")
            # 첫 질문을 제목으로 사용
            title = st.session_state.chat_history[0]["content"][:30] if st.session_state.chat_history else "상담 대화"
            try:
                db.save_conversation(user_id, title, st.session_state.chat_history)
            except Exception: pass
