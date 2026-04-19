from __future__ import annotations
import streamlit as st
import os
from src.config import SUBJECT_LIST

def render_wrong_notes() -> None:
    """📚 기능: 나의 오답노트 모아보기 (과목별 관리)"""
    st.header("📚 나의 오답노트")
    st.caption("퀴즈에서 틀린 문제들을 과목별로 모아보고 복습할 수 있습니다.")

    notes = st.session_state.get("wrong_notes", [])

    if not notes:
        st.info("아직 저장된 오답이 없습니다. 퀴즈를 풀고 틀린 문제를 오답노트에 추가해 보세요!")
        return

    # 과목별 필터링 UI
    subjects_in_notes = sorted(list(set([n.get('subject', '기타') for n in notes])))
    filter_options = ["전체 보기"] + subjects_in_notes
    
    col_f1, col_f2 = st.columns([2, 1])
    with col_f1:
        selected_filter = st.selectbox("과목 필터", filter_options, key="filter_wrong_notes")
    with col_f2:
        if st.button("🗑️ 전체 초기화", key="clear_all_wn_page", use_container_width=True):
            st.session_state.wrong_notes = []
            st.rerun()

    filtered_notes = notes if selected_filter == "전체 보기" else [n for n in notes if n.get('subject') == selected_filter]

    st.write(f"현재 **{selected_filter}** 기준 총 **{len(filtered_notes)}개**의 문항이 있습니다.")
    st.divider()

    # 오답 리스트 렌더링
    for i, wn in enumerate(filtered_notes):
        with st.container():
            # 헤더: 과목 뱃지 + 문제 내용
            badge_color = "#3b82f6" # 기본 파란색
            subject_name = wn.get('subject', '기타')
            
            st.markdown(
                f'<span style="background:{badge_color}22;border:1px solid {badge_color};'
                f'border-radius:6px;padding:2px 8px;font-size:0.75rem;color:{badge_color};'
                f'margin-right:10px;">{subject_name}</span>',
                unsafe_allow_html=True
            )
            
            c1, c2 = st.columns([9, 1])
            with c1:
                st.markdown(f"#### **{wn.get('content', '내용 없음')}**")
            with c2:
                if st.button("🗑️", key=f"del_filt_wn_{i}"):
                    # 원본 리스트에서 해당 객체 찾아서 삭제
                    st.session_state.wrong_notes = [n for n in notes if n != wn]
                    st.rerun()

            # 선택지 표시
            if wn.get("options"):
                for opt in wn["options"]:
                    st.markdown(f"- {opt}")

            # 정답 및 해설
            with st.expander("📖 정답 및 해설 보기", expanded=False):
                st.markdown(f"**✅ 정답:** {wn.get('answer', '정보 없음')}")
                if wn.get("explanation"):
                    st.info(f"💡 {wn['explanation']}")
            
            st.write("") # 간격
            st.divider()
