import streamlit as st
import os
import io
from .common import get_session_config, get_max_pdf_pages, _PYPDF_OK
from src.config import P
from src.prompts.system_prompts import get_system_prompt
from src.models import call_ai
from src.app_utils import encode_image_to_base64, make_pdf_bytes, parse_thinking_response, _pdf_extract_content, safe_filename

if _PYPDF_OK:
    import pypdf

def render_quiz_generator() -> None:
    """📝 기능 4: 평가문항 자동 생성기"""
    provider, model, api_key, mode = get_session_config()
    st.header("📝 평가문항 자동 생성기")
    st.caption("학습 내용을 입력하면 다양한 유형의 평가 문항을 자동으로 생성합니다.")

    method = st.radio("입력 방식", ["✏️ 텍스트 입력", "📷 자료 이미지 업로드", "📄 PDF 문서 업로드"],
                      horizontal=True, key="quiz_input_method")
    content_text = ""
    up = None

    if method == "✏️ 텍스트 입력":
        content_text = st.text_area("학습 내용",
            placeholder="예: 광합성은 식물이 빛 에너지를 이용하여...",
            height=180, key="quiz_text")
    elif method == "📷 자료 이미지 업로드":
        up = st.file_uploader("교과서/자료 이미지 업로드", type=["png", "jpg", "jpeg"],
                               key="quiz_img_upload")
        if up:
            st.image(up, use_container_width=True)
    else:
        up = st.file_uploader("관련 PDF 자료 업로드", type=["pdf"], key="quiz_pdf_upload")

    c1, c2, c3 = st.columns(3)
    with c1:
        q_types = st.multiselect("문항 유형",
            ["선택형(4지선다)", "단답형", "서술형", "참/거짓", "빈칸 채우기"],
            default=["선택형(4지선다)", "단답형"], key="quiz_types")
    with c2:
        num_q = st.slider("문항 수", 1, 20, 5, key="quiz_count")
    with c3:
        difficulty = st.select_slider("난이도", ["하", "중하", "중", "중상", "상"],
                                      value="중", key="quiz_difficulty")

    if st.button("🎯 문항 생성", key="btn_quiz", use_container_width=True):
        img_list = None
        if method == "✏️ 텍스트 입력":
            if not content_text.strip():
                st.warning("⚠️ 학습 내용을 입력하세요.")
                return
        elif method == "📷 자료 이미지 업로드":
            if not up:
                st.warning("⚠️ 이미지를 업로드하세요.")
                return
            img_b64 = encode_image_to_base64(up)
            img_list = [img_b64]
            content_text = "업로드된 이미지의 학습 내용을 바탕으로 문항을 출제해주세요."
        else:
            if not up:
                st.warning("⚠️ PDF 자료를 업로드하세요.")
                return
            with st.spinner("📄 PDF 분석 중..."):
                file_bytes = up.read()
                page_count = 0
                if _PYPDF_OK:
                    try:
                        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
                        page_count = len(reader.pages)
                    except Exception:
                        pass
                max_pg = get_max_pdf_pages(provider)
                extracted_text, extracted_images, extr_method = _pdf_extract_content(file_bytes, page_count, "", max_pages=max_pg)
                if extr_method == "text" and extracted_text.strip():
                    content_text = extracted_text
                else:
                    img_list = extracted_images if extracted_images else None
                    if img_list and len(img_list) > max_pg:
                        img_list = img_list[:max_pg]
                    content_text = "업로드된 PDF 문서의 내용을 바탕으로 문항을 출제해주세요."

        if not q_types:
            st.warning("⚠️ 문항 유형을 하나 이상 선택하세요.")
            return

        system = (("<|think|>\n" if provider == P.LMSTUDIO else "") +
                  get_system_prompt("quiz_generator", mode))
        
        user_prompt = (f"문항 유형: {', '.join(q_types)}\n문항 수: {num_q}문항\n"
                       f"난이도: {difficulty}\n\n학습 내용:\n{content_text[:30000]}\n\n"
                       f"각 문항에 정답과 해설, 평가 요소를 포함해주세요.")
        
        try:
            with st.spinner("🤖 AI가 평가 문항을 출제하는 중..."):
                result = call_ai(system, user_prompt, provider, model, api_key,
                                 images_b64=img_list)
            thinking, final = parse_thinking_response(result)
            st.session_state.quiz_gen_thinking = thinking
            st.session_state.quiz_gen_final = final
        except Exception as e:
            st.error(f"❌ {e}")

    if st.session_state.get("quiz_gen_final"):
        thinking = st.session_state.get("quiz_gen_thinking", "")
        final = st.session_state.quiz_gen_final
        if thinking:
            with st.expander("🎯 출제 의도 및 AI 분석", expanded=False):
                st.markdown(
                    f'<div style="background:#1e1e2e;border-left:3px solid #059669;'
                    f'padding:16px;border-radius:8px;font-size:0.85rem;'
                    f'color:#6ee7b7;white-space:pre-wrap;">{thinking}</div>',
                    unsafe_allow_html=True)
        st.subheader("📝 생성된 평가 문항")
        st.markdown(final)
        
        # 파일명 접두어 준비
        base_name = "quiz_questions"
        if st.session_state.get("quiz_img_upload"):
            base_name = os.path.splitext(st.session_state.quiz_img_upload.name)[0]
        elif st.session_state.get("quiz_pdf_upload"):
            base_name = os.path.splitext(st.session_state.quiz_pdf_upload.name)[0]
        base_name = safe_filename(base_name)
            
        dl_col1, dl_col2 = st.columns([1, 1])
        with dl_col1:
            st.download_button("💾 문항 저장 (.md)", data=final.encode('utf-8-sig'),
                               file_name=f"{base_name}.md", mime="text/markdown",
                               key="dl_quiz", use_container_width=True)
        with dl_col2:
            pdf_bytes = make_pdf_bytes(st.session_state.quiz_gen_final)
            if pdf_bytes:
                st.download_button("💾 문항 저장 (.pdf)", data=pdf_bytes,
                                   file_name=f"{base_name}.pdf", mime="application/pdf",
                                   key="dl_quiz_pdf", use_container_width=True)
