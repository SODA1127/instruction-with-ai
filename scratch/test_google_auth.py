import streamlit as st
from st_google_auth import st_google_auth

# Streamlit Cloud의 Secrets 혹은 로컬 .streamlit/secrets.toml이 설정되어 있어야 함
# [google_auth]
# client_id = "..."
# client_secret = "..."
# redirect_uri = "..." (Streamlit Cloud 주소 혹은 http://localhost:8501)

def test_auth():
    st.title("🔐 Google Auth Test (Local Only)")
    st.write("메인 앱 적용 전 인증 기능을 테스트합니다.")

    try:
        # st-google-auth는 기본적으로 st.secrets["google_auth"]를 찾음
        user_info = st_google_auth(
            client_id=st.secrets.get("google_auth", {}).get("client_id", ""),
            client_secret=st.secrets.get("google_auth", {}).get("client_secret", ""),
            redirect_uri=st.secrets.get("google_auth", {}).get("redirect_uri", "http://localhost:8501")
        )

        if user_info:
            st.success(f"✅ 로그인 성공: {user_info.get('name')}")
            st.json(user_info)
            if st.button("로그아웃"):
                st.session_state.clear()
                st.rerun()
        else:
            st.info("로그인 버튼을 눌러 인증을 진행해 주세요.")
            
    except Exception as e:
        st.error(f"❌ 인증 설정 오류: {e}")
        st.info("💡 `.streamlit/secrets.toml`에 [google_auth] 정보가 필요합니다.")

if __name__ == "__main__":
    test_auth()
