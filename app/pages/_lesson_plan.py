from __future__ import annotations
import streamlit as st
import os
import io
import json
import re
import base64

try:
    import pypdf
    _PYPDF_OK = True
except ImportError:
    _PYPDF_OK = False

try:
    import fitz
    _FITZ_OK = True
except ImportError:
    _FITZ_OK = False

from src.config import P, get_max_pdf_pages, LOCAL_PDF_MAX_PAGES, CLOUD_PDF_MAX_PAGES, SUBJECT_LIST
from src.prompts.system_prompts import SYSTEM_PROMPTS, MATH_INSTRUCTION
from src.models import call_ai, stream_ai
from src.app_utils import encode_image_to_base64, make_pdf_bytes, parse_thinking_response, _pdf_extract_content, _parse_question_list, safe_filename, parse_quiz_markdown

def get_session_config() -> tuple[str, str, str]:
    return (
        st.session_state.get("provider", P.LMSTUDIO),
        st.session_state.get("model", ""),
        st.session_state.get("api_key", ""),
    )

# ────────────────────────────────────────────────────────────
# 기능 렌더링
# ────────────────────────────────────────────────────────────



def render_lesson_plan() -> None:
    """📄 기능 3: 교안/학습자료 생성기"""
    provider, model, api_key = get_session_config()
    st.header("📄 교안 / 학습자료 생성기")
    st.caption("과목과 단원 정보를 입력하면 AI가 완성된 교안을 생성합니다.")

    col1, col2 = st.columns([1, 1])
    with col1:
        subject = st.selectbox("과목", SUBJECT_LIST, key="plan_subject")
        grade = st.selectbox("학년",
            ["초등 1학년", "초등 2학년", "초등 3학년", "초등 4학년", "초등 5학년", "초등 6학년",
             "중학 1학년", "중학 2학년", "중학 3학년",
             "고등 1학년", "고등 2학년", "고등 3학년",
             "대학교 1학년", "대학교 2학년", "대학교 3학년", "대학교 4학년"], key="plan_grade")
        unit_name = st.text_input("단원명", placeholder="예: 1단원. 문학의 빛깔",
                                  key="plan_unit")
        duration = st.number_input("수업 시간 (분)", min_value=10, max_value=120,
                                   value=45, step=5, key="plan_duration")
        ups = st.file_uploader("📄 참고 자료 PDF 업로드 (다중 선택 가능)", type=["pdf"], key="plan_pdf_upload", accept_multiple_files=True)
    with col2:
        plan_type = st.selectbox("교안 유형",
            ["📋 수업 지도안", "📝 학습 활동지", "📊 평가 계획서"], key="plan_type")
        goals = st.text_area("학습 목표 (성취기준)",
            placeholder="예: 시의 운율과 이미지를 분석하여 작가의 의도를 파악할 수 있다.",
            height=100, key="plan_goals")
        notes = st.text_area("특이사항 / 추가 요청",
            placeholder="예: 모둠 활동 중심, 디지털 기기 활용",
            height=80, key="plan_notes")

    if st.button("📋 교안 생성", key="btn_plan", use_container_width=True):
        if not unit_name.strip():
            st.warning("⚠️ 단원명을 입력해주세요.")
            return
            
        pdf_content = ""
        all_images = []
        if ups:
            with st.spinner(f"📄 PDF {len(ups)}개 분석 중..."):
                for up in ups:
                    file_bytes = up.read()
                    page_count = 0
                    if _PYPDF_OK:
                        try:
                            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
                            page_count = len(reader.pages)
                        except Exception: pass
                    
                    text, images, method = _pdf_extract_content(file_bytes, page_count, "")
                    if text.strip():
                        pdf_content += f"\n\n[파일: {up.name}]\n{text}"
                    if images:
                        all_images.extend(images)

        img_list = None
        if all_images:
            max_p = get_max_pdf_pages(provider)
            img_list = all_images[:max_p]

        type_label = plan_type.split(" ", 1)[1]
        user_prompt = (f"다음 정보를 바탕으로 [{type_label}]을 작성해주세요.\n\n"
                       f"과목: {subject}\n학년: {grade}\n단원명: {unit_name}\n"
                       f"수업 시간: {duration}분\n"
                       f"학습 목표: {goals or '교사가 설정 예정'}\n"
                       f"특이사항: {notes or '없음'}")
        
        if pdf_content:
            user_prompt += f"\n\n[참고 자료 내용]\n{pdf_content[:20000]}"
        elif img_list:
            user_prompt += f"\n\n[참고 자료]\n업로드된 참고 자료의 이미지 및 내용을 바탕으로 반영해주세요."

        user_mode = st.session_state.get("user_mode", "👩‍🏫 교육자용")
        full_prompt = f"[{user_mode}을 위한 교안/자료 작성]\n\n{user_prompt}"

        try:
            with st.spinner("📝 AI가 교안을 작성하는 중..."):
                result = call_ai(SYSTEM_PROMPTS["lesson_plan"], full_prompt,
                                 provider, model, api_key, images_b64=img_list)
            st.session_state.lesson_plan_result = result
        except Exception as e:
            st.error(f"❌ {e}")

    if st.session_state.get("lesson_plan_result"):
        st.subheader("📋 생성된 교안")
        # 생각 과정 제거 및 후처리 적용
        _, final_content = parse_thinking_response(st.session_state.lesson_plan_result)
        st.markdown(final_content, unsafe_allow_html=True)
        
        # 파일명 접두어 준비
        base_name = "lesson_plan"
        if st.session_state.get("plan_pdf_upload"):
             # 다중 업로드일 경우 첫 번째 파일명 활용
             first_up = st.session_state.plan_pdf_upload[0] if isinstance(st.session_state.plan_pdf_upload, list) else st.session_state.plan_pdf_upload
             base_name = os.path.splitext(first_up.name)[0]
        base_name = safe_filename(base_name)
        
        dl_col1, dl_col2 = st.columns([1, 1])
        with dl_col1:
            _, final_md = parse_thinking_response(st.session_state.lesson_plan_result)
            st.download_button("💾 Markdown 저장", data=final_md.encode('utf-8-sig'),
                               file_name=f"{base_name}.md", mime="text/markdown",
                               key="dl_plan_md", use_container_width=True)
        with dl_col2:
            pdf_bytes = make_pdf_bytes(st.session_state.lesson_plan_result)
            if pdf_bytes:
                st.download_button("💾 PDF 저장", data=pdf_bytes,
                                   file_name=f"{base_name}.pdf", mime="application/pdf",
                                   key="dl_plan_pdf", use_container_width=True)

