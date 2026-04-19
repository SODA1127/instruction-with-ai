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

from src.config import P, get_max_pdf_pages, LOCAL_PDF_MAX_PAGES, CLOUD_PDF_MAX_PAGES
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



def render_chatbot() -> None:
    """💬 기능 5: 교육 상담 챗봇"""
    provider, model, api_key = get_session_config()
    st.header("💬 교육 상담 챗봇")
    st.caption("교수법, 학생 지도, 학급 경영 등 어떤 고민이든 편하게 이야기하세요.")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    for msg in st.session_state.chat_history:
        avatar = "🎓" if msg["role"] == "assistant" else "🙋"
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])

    user_input = st.chat_input("고민이나 질문을 입력하세요...")

    if st.sidebar.button("🗑️ 대화 초기화", key="clear_chat"):
        st.session_state.chat_history = []
        st.rerun()

    if user_input:
        with st.chat_message("user", avatar="🙋"):
            st.markdown(user_input)
        st.session_state.chat_history.append({"role": "user", "content": user_input})

        with st.chat_message("assistant", avatar="🎓"):
            full_response = ""
            try:
                history = st.session_state.chat_history[:-1]
                user_mode = st.session_state.get("user_mode", "수강생용")
                full_input = f"[{user_mode}과 대화 중]\n{user_input}"
                
                resp = call_ai(SYSTEM_PROMPTS["chatbot"], full_input,
                               provider, model, api_key,
                               history=history, stream=True)
                full_response = stream_ai(resp, provider)
            except Exception as e:
                st.error(f"❌ {e}")
                full_response = ""

        _, clean = parse_thinking_response(full_response)
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": clean or full_response,
        })


# ────────────────────────────────────────────────────────────
# PDF 유틸리티
# ────────────────────────────────────────────────────────────

# PDF 텍스트가 분석에 충분한 품질인지 판별하는 기준 (페이지당 평균 글자 수)
_PDF_TEXT_MIN_CHARS_PER_PAGE = 80


def extract_pdf_text(file_bytes: bytes) -> tuple[str, int]:
    """
    pypdf로 PDF에서 텍스트를 추출합니다.
    Returns: (추출된 전체 텍스트, 총 페이지 수)
    """
    if not _PYPDF_OK:
        return "", 0
    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        pages.append(f"[페이지 {i + 1}]\n{text.strip()}")
    return "\n\n".join(pages), len(reader.pages)


def pdf_pages_to_images(file_bytes: bytes, max_pages: int = 20, selected_pages: set[int] | None = None) -> list[str]:
    """
    pymupdf(fitz)로 PDF 페이지를 base64 JPEG 이미지 리스트로 변환합니다.
    max_pages를 초과하는 페이지는 건너뜁니다.
    Returns: base64 문자열 리스트
    """
    if not _FITZ_OK:
        return []
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    images = []
    for i in range(len(doc)):
        if selected_pages is not None and i not in selected_pages:
            continue
        if len(images) >= max_pages:
            break
        page = doc[i]
        # 150 DPI 상당 (2x 배율) — 속도와 품질의 균형
        mat = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("jpeg")
        images.append(base64.b64encode(img_bytes).decode("utf-8"))
    doc.close()
    return images


def is_pdf_text_sufficient(text: str, page_count: int) -> bool:
    """텍스트 품질이 분석에 충분한지 판별합니다."""
    if not text.strip() or page_count == 0:
        return False
    avg_chars = len(text.replace("\n", "").replace(" ", "")) / page_count
    return avg_chars >= _PDF_TEXT_MIN_CHARS_PER_PAGE


def _pdf_extract_content(
    file_bytes: bytes,
    page_count: int,
    page_range: str,
) -> tuple[str, list[str] | None, str]:
    """
    PDF에서 텍스트 또는 이미지를 추출합니다 (공통 로직).
    Returns: (content_text, images_b64_or_None, extraction_method)
    """
    # 페이지 범위 파싱
    selected_pages: set[int] | None = None
    if page_range.strip():
        try:
            selected_pages = set()
            for part in page_range.replace(" ", "").split(","):
                if "-" in part:
                    a, b = part.split("-")
                    selected_pages.update(range(int(a) - 1, int(b)))
                else:
                    selected_pages.add(int(part) - 1)
        except ValueError:
            selected_pages = None

    extracted_text, n_pages = extract_pdf_text(file_bytes)

    # 페이지 범위 필터링
    if selected_pages and extracted_text:
        filtered, current_page_idx = [], 0
        for line in extracted_text.split("\n"):
            m = re.match(r"\[페이지 (\d+)\]", line)
            if m:
                current_page_idx = int(m.group(1)) - 1
            if m is None or current_page_idx in selected_pages:
                filtered.append(line)
        extracted_text = "\n".join(filtered)

    text_ok = is_pdf_text_sufficient(extracted_text, n_pages or max(1, page_count))

    if text_ok:
        return extracted_text, None, "text"
    elif _FITZ_OK:
        max_pg = 999  # Extract all needed images safely, limits will be handled in chunks or by selected_pages
        images = pdf_pages_to_images(file_bytes, max_pg, selected_pages)
        if images:
            return "", images, "vision"

    # 폴백: 텍스트가 부족해도 그대로 사용
    return extracted_text, None, "text (sparse)"


def _parse_question_list(raw: str) -> list[dict]:
    """
    AI 응답에서 문제 목록 JSON을 파싱합니다.
    [{"번호":"1","내용":"..."},...] 형식 또는 텍스트 폴백.
    """
    # JSON 블록 추출 시도
    json_match = re.search(r"\[[\s\S]*\]", raw)
    if json_match:
        try:
            data = json.loads(json_match.group())
            # 최소 필드 확인
            return [
                {"번호": str(q.get("번호", i + 1)), "내용": q.get("내용", "").strip()}
                for i, q in enumerate(data)
                if q.get("내용", "").strip()
            ]
        except json.JSONDecodeError:
            pass

    # 폴백 1: JSON이 깨졌거나 역슬래시 에러 시 정규식으로 직접 키/값 추출
    questions = []
    # "번호":"...", "내용":"..." 패턴 탐색
    matches = re.findall(r'"번호"\s*:\s*"([^"]+)"\s*,\s*"내용"\s*:\s*"(.*?)"\s*\}', raw, re.DOTALL)
    if matches:
        for num, content in matches:
            questions.append({"번호": num, "내용": content.strip().replace('\\"', '"').replace('\\\\', '\\')})
        if questions:
            return questions

    # 폴백 2: "1." / "1)" / "문제 1" 텍스트 패턴으로 분할
    pattern = re.split(r"(?m)^(?:문제\s*)?(\d+)[.)]\s+", raw)
    if len(pattern) > 2:
        for i in range(1, len(pattern) - 1, 2):
            num = pattern[i]
            content = pattern[i + 1].strip()
            if content:
                questions.append({"번호": num, "내용": content[:500]})
    return questions


def _render_question_solver_ui(
    provider: str, model: str, api_key: str,
) -> None:
    """
    세션에 저장된 문제 목록을 카드로 렌더링하고
    문제별 '풀이하기' 버튼 → 개별 AI 풀이를 제공합니다.
    """
    questions: list[dict] = st.session_state.get("pdf_questions", [])
    solutions: dict = st.session_state.setdefault("pdf_solutions", {})
    content_text: str = st.session_state.get("pdf_content_text", "")
    images_b64 = st.session_state.get("pdf_images_b64", None)
    method = st.session_state.get("pdf_extraction_method", "text")
    filename = st.session_state.get("pdf_filename", "문서")

    if not questions:
        return

    # 헤더
    badge_color = "#10b981" if method == "text" else "#f59e0b"
    badge_label = "📝 텍스트" if method == "text" else "🖼️ 비전 AI"
    st.markdown(
        f'<span style="background:{badge_color}22;border:1px solid {badge_color};'
        f'border-radius:6px;padding:3px 10px;font-size:0.8rem;color:{badge_color};">'
        f'{badge_label}</span>'
        f'&nbsp;&nbsp;<b style="color:#94a3b8;font-size:0.9rem;">{filename}</b>',
        unsafe_allow_html=True,
    )

    solved_count = len(solutions)
    st.markdown(
        f"### 🔢 감지된 문제 — {len(questions)}개 "
        f"<span style='color:#10b981;font-size:0.85rem;'>({solved_count}개 풀이 완료)</span>",
        unsafe_allow_html=True,
    )

    # 전체 풀이 / 초기화 버튼
    ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([2, 2, 2])
    with ctrl_col1:
        if st.button("⚡ 전체 문제 풀이", key="solve_all_btn", use_container_width=True):
            st.session_state.pdf_solve_all = True
    with ctrl_col2:
        if st.button("🗑️ 풀이 초기화", key="clear_solutions_btn", use_container_width=True):
            st.session_state.pdf_solutions = {}
            st.rerun()
    with ctrl_col3:
        if st.button("🔄 문제 재추출", key="reextract_btn", use_container_width=True):
            for k in ("pdf_questions", "pdf_solutions", "pdf_solve_all"):
                st.session_state.pop(k, None)
            st.rerun()

    st.divider()

    # 전체 풀이 모드 처리
    if st.session_state.get("pdf_solve_all"):
        unsolved = [i for i in range(len(questions)) if i not in solutions]
        if unsolved:
            prog = st.progress(0, text="전체 풀이 진행 중...")
            for step, idx in enumerate(unsolved):
                q = questions[idx]
                prog.progress((step + 1) / len(unsolved),
                              text=f"문제 {q['번호']} 풀이 중... ({step+1}/{len(unsolved)})")
                sol = _solve_single_question(
                    q, content_text, images_b64, provider, model, api_key, filename
                )
                solutions[idx] = sol
            prog.empty()
        st.session_state.pdf_solve_all = False
        st.rerun()

    # 문제 카드
    for i, q in enumerate(questions):
        solved = i in solutions

        card_border = "#10b981" if solved else "#334155"
        card_bg = "#0d1f1a" if solved else "#0f172a"
        st.markdown(
            f'<div style="border:1px solid {card_border};border-radius:12px;'
            f'background:{card_bg};padding:16px 20px;margin-bottom:10px;">',
            unsafe_allow_html=True,
        )

        q_col, btn_col = st.columns([5, 1])
        with q_col:
            # 문제 번호 배지 + 내용 (길면 expander)
            st.markdown(
                f'<div style="display:flex;align-items:flex-start;gap:12px;">'
                f'<span style="background:#4f46e5;color:white;border-radius:6px;'
                f'padding:2px 10px;font-weight:700;font-size:0.85rem;white-space:nowrap;">'
                f'{q["번호"]}번</span>'
                f'<span style="color:#e2e8f0;font-size:0.95rem;">{q["내용"][:200]}'
                f'{"..." if len(q["내용"]) > 200 else ""}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
        with btn_col:
            btn_label = "✅ 재풀이" if solved else "📖 풀이"
            if st.button(btn_label, key=f"solve_q_{i}", use_container_width=True):
                with st.spinner(f"문제 {q['번호']} 풀이 생성 중..."):
                    sol = _solve_single_question(
                        q, content_text, images_b64, provider, model, api_key, filename
                    )
                solutions[i] = sol
                st.rerun()

        if solved:
            with st.expander(f"📐 문제 {q['번호']} 풀이 보기", expanded=True):
                # 생각 과정 제거 및 후처리($, ** 보정) 적용
                _, final_sol = parse_thinking_response(solutions[i])
                st.markdown(final_sol)
                # 파일명 접두어 준비
                orig_name = st.session_state.get("pdf_filename", "pdf")
                base_name = os.path.splitext(orig_name)[0]
                q_filename = safe_filename(f"{i+1}_{base_name}_Q{i+1}")

                dl_col1, dl_col2 = st.columns([1, 1])
                with dl_col1:
                    _, final_sol = parse_thinking_response(solutions[i])
                    st.download_button(
                        "💾 MD 저장",
                        data=final_sol.encode('utf-8-sig'),
                        file_name=f"{q_filename}.md",
                        mime="text/markdown",
                        key=f"dl_sol_{i}",
                        use_container_width=True,
                    )
                with dl_col2:
                    pdf_bytes = make_pdf_bytes(solutions[i])
                    if pdf_bytes:
                        st.download_button(
                            "💾 PDF 저장",
                            data=pdf_bytes,
                            file_name=f"{q_filename}.pdf",
                            mime="application/pdf",
                            key=f"dl_sol_pdf_{i}",
                            use_container_width=True,
                        )

        st.markdown("</div>", unsafe_allow_html=True)

    # 풀이 전체 저장
    if solutions:
        all_sols = "\n\n---\n\n".join(
            f"## 문제 {questions[i]['번호']}\n{questions[i]['내용']}\n\n### 풀이\n{sol}"
            for i, sol in sorted(solutions.items())
        )
        # 파일명 접두어 준비 (전체)
        orig_name = st.session_state.get("pdf_filename", "pdf")
        base_name = os.path.splitext(orig_name)[0]
        all_filename = safe_filename(f"{base_name}_전체풀이")

        col1, col2 = st.columns(2)
        with col1:
            _, final_all = parse_thinking_response(all_sols)
            st.download_button(
                "💾 전체 풀이 저장 (.md)",
                data=final_all.encode('utf-8-sig'),
                file_name=f"{all_filename}.md",
                mime="text/markdown",
                key="dl_all_solutions",
                use_container_width=True,
            )
        with col2:
            pdf_bytes = make_pdf_bytes(all_sols)
            if pdf_bytes:
                st.download_button(
                    "💾 전체 풀이 저장 (.pdf)",
                    data=pdf_bytes,
                    file_name=f"{all_filename}.pdf",
                    mime="application/pdf",
                    key="dl_all_solutions_pdf",
                    use_container_width=True,
                )


def _solve_single_question(
    q: dict,
    content_text: str,
    images_b64: list[str] | None,
    provider: str, model: str, api_key: str,
    filename: str,
) -> str:
    """단일 문제에 대한 상세 풀이를 AI에 요청합니다."""
    # 컨텍스트: 문제 주변 내용만 잘라서 전송 (토큰 절약)
    # 문제 내용이 텍스트에 있으면 앞뒤 2000자만 추출
    context = ""
    if content_text:
        needle = q["내용"][:50]  # 문제 앞부분으로 검색
        idx = content_text.find(needle)
        if idx >= 0:
            start = max(0, idx - 500)
            end = min(len(content_text), idx + 2000)
            context = content_text[start:end]
        else:
            # 못 찾으면 전체 텍스트 앞 3000자만
            context = content_text[:3000]

    user_mode = st.session_state.get("user_mode", "👩‍🏫 교육자용")
    is_educator = "교육자" in user_mode

    system = (
        f"당신은 [{user_mode}]을 위한 한국의 교육 전문가 AI입니다.\n"
        "학생이 제출한 시험 문제를 받아 명확하고 단계적인 풀이를 제공합니다.\n\n"
        "[콘텐츠 유형별 출력 형식]\n"
        "1. 일반 교과(수학, 과학 등): :::problem, :::concept, :::solving, :::explanation 컨테이너를 사용하여 알록달록하게 구성하세요.\n"
        "2. 프로그래밍/코딩: 컨테이너 박스 없이 표준 마크다운(헤더 #, ##, 코드 블록 ```) 포맷을 사용하여 기술 문서처럼 깔끔하게 구성하세요.\n\n"
        f"{MATH_INSTRUCTION}\n"
        "항상 한국어로 답변하세요. 프로그래밍 문제라면 반드시 가독성 좋은 코드 스니펫을 포함하세요.\n"
        + ("교수법 팁이나 보충 설명도 포함하면 좋습니다." if is_educator else "이해하기 쉬운 비유와 학습 권장 사항을 포함하세요.")
    )

    user_prompt = (
        f"[문서: {filename}]\n"
        f"[대상: {user_mode}]\n\n"
        f"**문제 {q['번호']}번**\n{q['내용']}\n\n"
    )
    if context:
        user_prompt += f"[문서 내 관련 컨텍스트]\n{context}\n\n"
    
    user_prompt += "이 문제를 위 대상의 눈높이에 맞춰 단계별로 자세히 분석 및 풀이해주세요."

    return call_ai(system, user_prompt, provider, model, api_key,
                   images_b64=images_b64 if not context else None)

