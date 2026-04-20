from __future__ import annotations
import streamlit as st
import os
from src.config import SUBJECT_LIST
from src.db_manager import db
from src.app_utils import make_pdf_bytes, safe_filename

def render_wrong_notes() -> None:
    """📚 기능: 나의 오답노트 모아보기 (과목별 관리)"""
    st.header("📚 나의 오답노트")
    st.caption("퀴즈에서 틀린 문제들을 과목별로 모아보고 복습할 수 있습니다.")

    # 1. 로컬 세션 오답 가져오기
    local_notes = st.session_state.get("wrong_notes", [])
    
    # 2. 로그인 상태일 경우 DB에서 과거 오답 가져오기
    remote_notes = []
    if st.user.is_logged_in:
        user_id = st.user.get("sub")
        try:
            with st.spinner("과거 기록 불러오는 중..."):
                results = db.get_quiz_results(user_id)
                for res in results:
                    # incorrect_answers 컬럼이 JSON 리스트임
                    inc_list = res.get("incorrect_answers", [])
                    if isinstance(inc_list, list):
                        # 각 문항에 퀴즈 제목(과목) 정보 주입
                        for item in inc_list:
                            if "subject" not in item:
                                item["subject"] = res.get("quiz_title", "기타")
                            remote_notes.append(item)
        except Exception as e:
            st.error(f"⚠️ 기록 조회 오류: {e}")

    # 3. 통합 (중복 제거는 문제 내용 기준)
    notes = local_notes.copy()
    existing_contents = {n.get("content") for n in local_notes}
    for rn in remote_notes:
        if rn.get("content") not in existing_contents:
            notes.append(rn)

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

    # --- [추가] 전체 내보내기 (Export) 섹션 ---
    if filtered_notes:
        dl_col1, dl_col2 = st.columns(2)
        
        # 통합 마크다운 생성
        all_md = f"# 📚 오답노트 ({selected_filter})\n\n"
        for i, n in enumerate(filtered_notes):
            all_md += f"## {i+1}. {n.get('content')}\n"
            if n.get("options"):
                for opt in n["options"]: 
                    all_md += f"- {opt}\n"
            all_md += f"\n**✅ 정답:** {n.get('answer')}\n"
            all_md += f"**💡 해설:** {n.get('explanation', '-')}\n\n---\n\n"

        with dl_col1:
            st.download_button(
                "💾 MD 내보내기",
                data=all_md.encode('utf-8-sig'),
                file_name=safe_filename(f"오답노트_{selected_filter}.md"),
                mime="text/markdown",
                use_container_width=True
            )
        with dl_col2:
            pdf_bytes = make_pdf_bytes(all_md)
            if pdf_bytes:
                st.download_button(
                    "💾 PDF 내보내기",
                    data=pdf_bytes,
                    file_name=safe_filename(f"오답노트_{selected_filter}.pdf"),
                    mime="application/pdf",
                    use_container_width=True
                )

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
