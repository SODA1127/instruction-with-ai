import streamlit as st

st.download_button(
    "다운로드 테스트 (Korean)",
    data="안녕하세요",
    file_name="테스트.md",
    mime="text/markdown"
)

st.download_button(
    "다운로드 테스트 (English)",
    data="Hello",
    file_name="test.md",
    mime="text/markdown"
)

st.download_button(
    "다운로드 테스트 (Bytes, Korean)",
    data="안녕하세요".encode('utf-8'),
    file_name="테스트_bytes.md",
    mime="text/markdown"
)
