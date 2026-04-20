import streamlit as st
from supabase import create_client, Client
import datetime

class DBManager:
    def __init__(self):
        """환경 변수(혹은 st.secrets)에서 Supabase 정보를 가져와 클라이언트를 초기화합니다."""
        try:
            self.url = st.secrets["SUPABASE_URL"]
            self.key = st.secrets["SUPABASE_KEY"]
            self.supabase: Client = create_client(self.url, self.key)
        except Exception as e:
            st.error(f"❌ Supabase 연결 실패: {e}")
            self.supabase = None

    # --- 프로필 관리 ---
    def upsert_profile(self, user_id, email, full_name, avatar_url):
        """사용자 프로필을 업데이트하거나 없으면 생성합니다."""
        if not self.supabase: return
        data = {
            "id": user_id,
            "email": email,
            "full_name": full_name,
            "avatar_url": avatar_url,
            "updated_at": datetime.datetime.utcnow().isoformat()
        }
        return self.supabase.table("profiles").upsert(data).execute()

    # --- 대화 이력 관리 ---
    def save_conversation(self, user_id, title, messages):
        """채팅 이력을 DB에 저장합니다."""
        if not self.supabase: return
        data = {
            "user_id": user_id,
            "title": title,
            "messages": messages
        }
        return self.supabase.table("conversations").insert(data).execute()

    def get_user_conversations(self, user_id):
        """특정 사용자의 전체 대화 목록을 가져옵니다."""
        if not self.supabase: return []
        response = self.supabase.table("conversations").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
        return response.data

    # --- 퀴즈 결과 및 오답노트 관리 ---
    def save_quiz_result(self, user_id, quiz_title, score, total, incorrect_data):
        """퀴즈 결과와 오답 데이터를 저장합니다."""
        if not self.supabase: return
        data = {
            "user_id": user_id,
            "quiz_title": quiz_title,
            "score": score,
            "total_questions": total,
            "incorrect_answers": incorrect_data
        }
        return self.supabase.table("quiz_results").insert(data).execute()

    def get_wrong_answers(self, user_id):
        """오답노트 조회를 위해 틀린 문제 데이터가 포함된 이력을 가져옵니다."""
        if not self.supabase: return []
        response = self.supabase.table("quiz_results").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
        return response.data

# 싱글톤 인스턴스 생성
db = DBManager()
