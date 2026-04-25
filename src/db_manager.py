import streamlit as st
from supabase import create_client, Client
import logging
from typing import List, Dict, Any, Optional

# --- 로깅 설정 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@st.cache_resource(show_spinner="데이터베이스 연결 중...")
def get_supabase_client() -> Client:
    """
    st.secrets에서 인증 정보를 읽어 Supabase 클라이언트를 초기화하고 캐싱합니다.
    """
    try:
        url: str = st.secrets["SUPABASE_URL"]
        key: str = st.secrets["SUPABASE_KEY"]
        
        supabase: Client = create_client(url, key)
        logger.info("Supabase 클라이언트 초기화 성공")
        return supabase
    except KeyError as e:
        logger.error(f"비밀 정보(st.secrets) 누락: {e}")
        raise ConnectionError("데이터베이스 설정 정보가 부족합니다.")
    except Exception as e:
        logger.error(f"Supabase 초기화 중 예상치 못한 오류: {e}")
        raise ConnectionError("데이터베이스 연결에 실패했습니다.")

def upsert_profile(user_id: str, email: str, full_name: str, avatar_url: Optional[str]) -> bool:
    """사용자 프로필을 업데이트하거나 없으면 생성합니다."""
    try:
        supabase = get_supabase_client()
        data = {
            "id": user_id,
            "email": email,
            "full_name": full_name,
            "avatar_url": avatar_url
        }
        supabase.table('profiles').upsert(data).execute()
        logger.info(f"프로필 업데이트 성공: {user_id}")
        return True
    except Exception as e:
        logger.error(f"프로필 업데이트 오류 ({user_id}): {e}")
        return False

def save_conversation(user_id: str, title: str, messages: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """새로운 대화 이력을 저장합니다."""
    try:
        supabase = get_supabase_client()
        data = {
            "user_id": user_id,
            "title": title,
            "messages": messages 
        }
        response = supabase.table('conversations').insert(data).execute()
        logger.info(f"대화 저장 성공: {title}")
        return response.data[0] if response and response.data else None
    except Exception as e:
        logger.error(f"대화 저장 오류 ({user_id}): {e}")
        return None

def get_user_conversations(user_id: str) -> List[Dict[str, Any]]:
    """특정 사용자의 전체 대화 목록을 가져옵니다."""
    try:
        supabase = get_supabase_client()
        response = supabase.table('conversations').select('*').eq('user_id', user_id).order('created_at', desc=True).execute()
        return response.data if response and response.data else []
    except Exception as e:
        logger.error(f"대화 목록 조회 오류 ({user_id}): {e}")
        return []

def save_quiz_result(user_id: str, quiz_title: str, score: int, total_questions: int, incorrect_answers: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """퀴즈 결과와 오답 데이터를 저장합니다."""
    try:
        supabase = get_supabase_client()
        data = {
            "user_id": user_id,
            "quiz_title": quiz_title,
            "score": score,
            "total_questions": total_questions,
            "incorrect_answers": incorrect_answers 
        }
        response = supabase.table('quiz_results').insert(data).execute()
        logger.info(f"퀴즈 결과 저장 성공: {quiz_title}")
        return response.data[0] if response and response.data else None
    except Exception as e:
        logger.error(f"퀴즈 결과 저장 오류 ({user_id}): {e}")
        return None

def get_quiz_results(user_id: str) -> List[Dict[str, Any]]:
    """특정 사용자의 전체 퀴즈 결과 목록을 가져옵니다."""
    try:
        supabase = get_supabase_client()
        response = supabase.table('quiz_results').select('*').eq('user_id', user_id).order('created_at', desc=True).execute()
        return response.data if response and response.data else []
    except Exception as e:
        logger.error(f"퀴즈 결과 조회 오류 ({user_id}): {e}")
        return []

def save_shared_quiz(quiz_data: Dict[str, Any]) -> Optional[str]:
    """공유용 퀴즈 데이터를 저장하고 UUID를 반환합니다."""
    try:
        supabase = get_supabase_client()
        response = supabase.table('shared_quizzes').insert({"quiz_data": quiz_data}).execute()
        if response and response.data:
            return response.data[0]["id"]
        return None
    except Exception as e:
        logger.error(f"공유 퀴즈 저장 오류: {e}")
        return None

def get_shared_quiz(quiz_id: str) -> Optional[Dict[str, Any]]:
    """ID 기반으로 공유된 퀴즈 데이터를 가져옵니다."""
    try:
        supabase = get_supabase_client()
        response = supabase.table('shared_quizzes').select('quiz_data').eq('id', quiz_id).execute()
        if response and response.data:
            return response.data[0]["quiz_data"]
        return None
    except Exception as e:
        logger.error(f"공유 퀴즈 조회 오류 ({quiz_id}): {e}")
        return None

# 기존 'db.method()' 호환성을 위한 클래스 래퍼 (선택 사항)
class _LegacyDBGate:
    def upsert_profile(self, *args, **kwargs): return upsert_profile(*args, **kwargs)
    def save_conversation(self, *args, **kwargs): return save_conversation(*args, **kwargs)
    def get_user_conversations(self, *args, **kwargs): return get_user_conversations(*args, **kwargs)
    def save_quiz_result(self, *args, **kwargs): return save_quiz_result(*args, **kwargs)
    def get_quiz_results(self, *args, **kwargs): return get_quiz_results(*args, **kwargs)
    def get_wrong_answers(self, user_id): return get_quiz_results(user_id) # 이전 이름 호환
    def save_shared_quiz(self, quiz_data): return save_shared_quiz(quiz_data)
    def get_shared_quiz(self, quiz_id): return get_shared_quiz(quiz_id)

db = _LegacyDBGate()
