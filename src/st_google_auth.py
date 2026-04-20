import streamlit as st
import requests
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
import urllib.parse
import secrets

def _clear_query_params():
    """Streamlit 버전 호환 query_params 클리어."""
    try:
        st.query_params.clear()
    except Exception:
        for key in list(st.query_params.keys()):
            del st.query_params[key]


def st_google_auth(client_id, client_secret, redirect_uri):
    # 0. 이미 로그인되어 있으면 즉시 반환
    if st.session_state.get("google_user_info"):
        return st.session_state["google_user_info"]

    # 1. URL에서 인증 코드 가져오기
    params = st.query_params
    code = params.get("code")
    err = params.get("error")

    if err:
        st.error(f"❌ 구글 인증 오류: {err}")
        _clear_query_params()
        return None

    if isinstance(code, list):
        code = code[0]

    # [방어 로직] 세션 플래그 초기화
    st.session_state.setdefault("auth_processing_now", False)
    st.session_state.setdefault("processed_codes", set())

    if code:
        if code in st.session_state["processed_codes"]:
            # 이미 처리된 코드면 파라미터 제거 후 리런 (무한 루프 방지)
            _clear_query_params()
            st.rerun()
            return None

        if st.session_state["auth_processing_now"]:
            st.info("⏳ 이미 인증 처리가 진행 중입니다...")
            return None

        # 인증 시작
        st.session_state["auth_processing_now"] = True
        st.session_state["processed_codes"].add(code)

        st.toast("🔍 구글 인증 코드를 감지했습니다.")
        with st.spinner("🔐 구글 보안 토큰 교환 중..."):
            try:
                token_url = "https://oauth2.googleapis.com/token"
                payload = {
                    "code": str(code).strip(),
                    "client_id": str(client_id).strip(),
                    "client_secret": str(client_secret).strip(),
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                }

                response = requests.post(token_url, data=payload, timeout=10)
                token_data = response.json()

                if response.status_code == 200:
                    verified_info = id_token.verify_oauth2_token(
                        token_data.get("id_token"),
                        google_requests.Request(),
                        client_id
                    )
                    st.session_state["google_user_info"] = verified_info
                    st.session_state["auth_processing_now"] = False
                    st.toast("✅ 로그인 성공!")

                    _clear_query_params()
                    st.rerun()
                    return verified_info
                else:
                    error_msg = token_data.get('error_description', token_data.get('error', 'Unknown Error'))
                    st.error(f"❌ 구글 인증 실패: {error_msg}")
                    if "redirect_uri" in error_msg.lower():
                        st.info(
                            f"💡 현재 앱이 사용 중인 redirect_uri: `{redirect_uri}`\n\n"
                            "구글 클라우드 콘솔의 'Authorized redirect URIs' 에 이 주소가 "
                            "**정확히** 등록되어 있어야 합니다 (슬래시 유무/포트 번호 포함)."
                        )

                    st.session_state["auth_processing_now"] = False
                    _clear_query_params()
                    return None
            except Exception as e:
                st.error(f"🚨 시스템 오류: {type(e).__name__}: {e}")
                st.session_state["auth_processing_now"] = False
                _clear_query_params()
                return None

    # --- 2. 로그인 버튼 표시 섹션 (코드가 없을 때만 도달) ---
    if "oauth_state_val" not in st.session_state:
        st.session_state["oauth_state_val"] = secrets.token_urlsafe(16)
    
    auth_params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": st.session_state["oauth_state_val"],
        "prompt": "select_account"
    }
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(auth_params)}"
    
    st.sidebar.markdown(f'''
        <a href="{auth_url}" target="_self" style="
            display: block; width: 100%; padding: 0.8rem;
            background-color: #262730; color: #ffffff; text-align: center;
            text-decoration: none; border-radius: 10px;
            border: 1px solid rgba(250, 250, 250, 0.2);
            font-weight: 600; font-size: 1rem;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        ">
            🔑 Google 계정으로 로그인
        </a>
    ''', unsafe_allow_html=True)
    return None
