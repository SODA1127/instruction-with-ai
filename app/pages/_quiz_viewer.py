import streamlit as st
import src.app_utils as app_utils
import src.db_manager as db

def render_quiz_viewer(quiz_id: str) -> None:
    """🔗 공유된 퀴즈를 풀 수 있는 전용 뷰어 페이지"""
    
    # 1. 퀴즈 데이터 로드
    quiz_data = db.get_shared_quiz(quiz_id)
    
    if not quiz_data:
        st.error("❌ 존재하지 않거나 만료된 퀴즈 링크입니다.")
        if st.button("홈으로 이동", use_container_width=True):
            st.query_params.clear()
            st.rerun()
        return

    passage = quiz_data.get("passage", "")
    questions = quiz_data.get("questions", [])

    st.title("🎯 공유된 AI 퀴즈 풀기")
    st.info("AI가 생성한 평가 문항입니다. 지문을 읽고 정답을 맞춰보세요!")
    
    # 2. 지문 렌더링
    if passage:
        st.subheader("📖 지문")
        st.markdown(
            f'<div style="background:#f8fafc; border:1px solid #e2e8f0; padding:25px; '
            f'border-radius:15px; font-family:\'Noto Sans KR\', sans-serif; color:#334155; '
            f'line-height:1.8; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); margin-bottom:30px;">'
            f'{passage}</div>',
            unsafe_allow_html=True
        )

    # 3. 문제 풀이 세션 상태 초기화
    if f"user_answers_{quiz_id}" not in st.session_state:
        st.session_state[f"user_answers_{quiz_id}"] = {}
    if f"quiz_submitted_{quiz_id}" not in st.session_state:
        st.session_state[f"quiz_submitted_{quiz_id}"] = False

    # 4. 개별 문항 렌더링
    st.subheader("📝 평가 문항")
    for i, q in enumerate(questions):
        idx = str(i + 1)
        q_text = q.get("content", "내용 없음")
        options = q.get("options", [])
        q_type = q.get("type", "multiple_choice")
        
        with st.container():
            st.markdown(f"#### **Q{idx}. {q_text}**")
            
            if options:
                # 객관식
                st.session_state[f"user_answers_{quiz_id}"][idx] = st.radio(
                    f"답안 선택 (Q{idx})", options, 
                    key=f"radio_{quiz_id}_{idx}", 
                    index=None,
                    label_visibility="collapsed"
                )
            else:
                # 주관식
                st.session_state[f"user_answers_{quiz_id}"][idx] = st.text_input(
                    f"답안 입력 (Q{idx})", 
                    key=f"input_{quiz_id}_{idx}",
                    placeholder="정답을 입력하세요...",
                    label_visibility="collapsed"
                )
        st.divider()

    # 5. 제출 및 채점
    if not st.session_state[f"quiz_submitted_{quiz_id}"]:
        if st.button("✅ 모든 답안 제출하기", use_container_width=True, type="primary"):
            st.session_state[f"quiz_submitted_{quiz_id}"] = True
            st.rerun()
    else:
        # 채점 결과 공개
        st.success("🎉 답안 제출이 완료되었습니다! 결과를 확인하세요.")
        total_correct = 0
        
        for i, q in enumerate(questions):
            idx = str(i + 1)
            correct_ans = str(q.get("answer", "")).strip()
            user_ans = str(st.session_state[f"user_answers_{quiz_id}"].get(idx, "")).strip()
            explanation = q.get("explanation", "설명이 없습니다.")

            # 유연한 정답 매칭 (번호 추출 등)
            is_correct = False
            if correct_ans in user_ans or user_ans in correct_ans:
                is_correct = True
            
            with st.expander(f"Q{idx} 결과: {'✅ 정답' if is_correct else '❌ 오답'}", expanded=True):
                if is_correct:
                    total_correct += 1
                else:
                    st.error(f"내 답안: {user_ans}")
                    st.info(f"정답: {correct_ans}")
                
                st.markdown(f"**해설:**\n{explanation}")

        # 최종 점수 표시
        st.metric("최종 점수", f"{total_correct} / {len(questions)}", delta=f"{int(total_correct/len(questions)*100)}점")
        
        if st.button("🏠 메인 페이지로 돌아가기", use_container_width=True):
            st.query_params.clear()
            st.rerun()
