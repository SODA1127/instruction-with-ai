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
import src.app_utils as app_utils

def get_session_config() -> tuple[str, str, str]:
    return (
        st.session_state.get("provider", P.LMSTUDIO),
        st.session_state.get("model", ""),
        st.session_state.get("api_key", ""),
    )

# ────────────────────────────────────────────────────────────
# 기능 렌더링
# ────────────────────────────────────────────────────────────



def render_pdf_analyzer() -> None:
    """📑 기능 6: PDF 문서 분석기 (문제별 개별 풀이 지원)"""
    provider, model, api_key = get_session_config()
    st.header("📑 PDF 문서 분석기")
    st.caption("시험지·교재 PDF 업로드 → 문제 자동 감지 → 문제별 개별 풀이")

    if not _PYPDF_OK and not _FITZ_OK:
        st.error("❌ PDF 처리 라이브러리가 없습니다. `pip install pypdf pymupdf`를 실행하세요.")
        return

    # ── 이미 문제가 추출된 상태: 문제 카드 UI 우선 렌더링 ──────
    if st.session_state.get("pdf_questions"):
        with st.sidebar:
            with st.expander("📑 현재 PDF", expanded=False):
                st.caption(st.session_state.get("pdf_filename", ""))
                if st.button("📂 새 PDF 열기", key="open_new_pdf"):
                    for k in ("pdf_questions", "pdf_solutions", "pdf_content_text",
                              "pdf_images_b64", "pdf_filename", "pdf_extraction_method",
                              "pdf_solve_all"):
                        st.session_state.pop(k, None)
                    st.rerun()
        _render_question_solver_ui(provider, model, api_key, mode=st.session_state.get("user_mode", "교육자용"))
        return

    # ── 업로드 & 분석 설정 UI ────────────────────────────────────
    col1, col2 = st.columns([1, 1])

    with col1:
        uploaded = st.file_uploader(
            "PDF 파일 업로드 (최대 50MB)",
            type=["pdf"],
            key="pdf_upload",
        )

        analysis_type = st.selectbox(
            "분석 유형",
            [
                "🔢 문제별 개별 풀이  ← 권장 (컨텍스트 제한 우회)",
                "📋 전체 내용 요약",
                "🔑 핵심 개념 및 키워드 추출",
                "📝 학습 자료 / 노트 생성",
                "🔍 특정 내용 질의응답",
            ],
            key="pdf_analysis_type",
        )

        custom_question = ""
        if analysis_type.startswith("🔍"):
            custom_question = st.text_area(
                "질문 입력",
                placeholder="예: 이 문서에서 광합성 단계를 설명하는 부분을 요약해줘.",
                height=100,
                key="pdf_question",
            )

        st.info(f"📍 현재 모드: **{st.session_state.get('user_mode', '교육자용')}**")

        page_range = st.text_input(
            "분석할 페이지 범위 (선택, 비워두면 전체)",
            placeholder="예: 1-10  또는  3,7,12",
            key="pdf_page_range",
        )

    with col2:
        if uploaded:
            file_bytes = uploaded.read()
            file_size_mb = len(file_bytes) / 1_048_576

            page_count = 0
            if _PYPDF_OK:
                try:
                    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
                    page_count = len(reader.pages)
                except Exception:
                    pass

            is_question_mode = analysis_type.startswith("🔢")

            st.markdown(
                f"""
                <div style='background:#1e293b;border:1px solid #334155;
                border-radius:10px;padding:16px;margin-bottom:12px;'>
                <b>📄 {uploaded.name}</b><br>
                <small style='color:#94a3b8;'>크기: {file_size_mb:.1f} MB
                {'| 총 ' + str(page_count) + ' 페이지' if page_count else ''}
                {'| 🔢 문제별 풀이 모드' if is_question_mode else ''}</small>
                </div>
                """,
                unsafe_allow_html=True,
            )

            btn_label = "🔢 문제 추출 & 풀이 시작" if is_question_mode else "🔍 PDF 분석 시작"
            if st.button(btn_label, key="btn_pdf_analyze", use_container_width=True):
                _run_pdf_analysis(
                    file_bytes, uploaded.name, page_count,
                    analysis_type, custom_question, page_range,
                    provider, model, api_key,
                    user_mode=st.session_state.get("user_mode", "교육자용")
                )
        else:
            st.markdown(
                """
                <div style='background:#0f172a;border:2px dashed #334155;
                border-radius:12px;padding:40px;text-align:center;color:#64748b;'>
                <div style='font-size:3rem;margin-bottom:12px;'>📑</div>
                <b>PDF 파일을 왼쪽에 업로드하세요</b><br>
                <small>시험지·교재·학습자료 등 지원</small>
                </div>
                """,
                unsafe_allow_html=True,
            )
            with st.expander("ℹ️ PDF 분석 안내", expanded=True):
                max_p = get_max_pdf_pages(provider)
                st.markdown(f"""
**🔢 문제별 개별 풀이 (권장)**
- PDF에서 문제를 자동 감지해 목록 생성 → 개별 풀이
- 컨텍스트 제한 우회로 정확도 대폭 향상

**📄 일반 분석 모드**
- 요약 / 핵심 개념 / 노트 생성 등 수행
- 비전 분석 시 최대 **{max_p}페이지** 지원 (로컬 {LOCAL_PDF_MAX_PAGES} / 클라우드 {CLOUD_PDF_MAX_PAGES})
""")

    # ── 일반 분석 결과 출력 ──────────────────────────────────────────
    _render_pdf_general_result()

def _render_question_solver_ui(
    provider: str, model: str, api_key: str, mode: str,
) -> None:
    """추출된 문제들을 카드 형태로 보여주고 개별/전체 풀이를 처리하는 UI"""
    questions: list[dict] = st.session_state.get("pdf_questions", [])
    solutions: dict = st.session_state.setdefault("pdf_solutions", {})
    content_text: str = st.session_state.get("pdf_content_text", "")
    images_b64 = st.session_state.get("pdf_images_b64", None)
    method = st.session_state.get("pdf_extraction_method", "text")
    filename = st.session_state.get("pdf_filename", "문서")

    if not questions:
        st.info("감지된 문제가 없습니다.")
        return

    badge_color = "#10b981" if method == "text" else "#f59e0b"
    badge_label = "📝 텍스트 추출 기반" if method == "text" else "🖼️ 비전 AI 분석 기반"
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
            for k in ("pdf_questions", "pdf_solutions", "pdf_solve_all", "pdf_bytes_cache", "pdf_all_cache_key"):
                st.session_state.pop(k, None)
            st.rerun()

    st.divider()

    # 전체 풀이 진행
    if st.session_state.get("pdf_solve_all"):
        unsolved = [i for i in range(len(questions)) if i not in solutions]
        if unsolved:
            prog = st.progress(0, text="전체 풀이 진행 중 (병렬 처리)...")
            
            import concurrent.futures
            
            def _solve_task(idx):
                q = questions[idx]
                sol = _solve_single_question(
                    q, content_text, images_b64, provider, model, api_key, filename, mode
                )
                pdf_b = app_utils.make_pdf_bytes(sol)
                return idx, sol, pdf_b

            completed = 0
            if "pdf_bytes_cache" not in st.session_state:
                st.session_state.pdf_bytes_cache = {}
                
            # 멀티스레딩 병렬 처리 적용 (API Rate Limit 방지를 위해 5개로 제한)
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = {executor.submit(_solve_task, idx): idx for idx in unsolved}
                
                for future in concurrent.futures.as_completed(futures):
                    idx, sol, pdf_b = future.result()
                    solutions[idx] = sol
                    st.session_state.pdf_bytes_cache[idx] = pdf_b
                    
                    completed += 1
                    prog.progress(completed / len(unsolved),
                                  text=f"풀이 및 PDF 변환 진행 중... ({completed}/{len(unsolved)} 완료)")

            prog.empty()
        st.session_state.pdf_solve_all = False
        st.rerun()

    # 개별 문제 카드
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
            q_text = q["content"][:200] + ("..." if len(q["content"]) > 200 else "")
            st.markdown(
                f'<span style="background:#4f46e5;color:white;border-radius:6px;'
                f'padding:2px 10px;font-weight:700;font-size:0.85rem;margin-right:10px;">'
                f'{q["number"]}번</span> {q_text}',
                unsafe_allow_html=True,
            )
        with btn_col:
            btn_label = "✅ 재풀이" if solved else "📖 풀이"
            if st.button(btn_label, key=f"solve_q_{i}", use_container_width=True):
                with st.spinner(f"문제 {q['number']} 풀이 및 PDF 생성 중..."):
                    sol = _solve_single_question(
                        q, content_text, images_b64, provider, model, api_key, filename, mode
                    )
                    pdf_b = app_utils.make_pdf_bytes(sol)
                solutions[i] = sol
                if "pdf_bytes_cache" not in st.session_state:
                    st.session_state.pdf_bytes_cache = {}
                st.session_state.pdf_bytes_cache[i] = pdf_b
                st.rerun()

        if solved:
            with st.expander(f"📐 문제 {q['number']} 풀이 보기", expanded=True):
                sol_text = solutions[i]
                
                # 그래프 코드 파싱 및 실행
                parts = re.split(r'```python\s*graph\n(.*?)```', sol_text, flags=re.DOTALL | re.IGNORECASE)
                
                for idx_p, part in enumerate(parts):
                    if idx_p % 2 == 0:
                        if part.strip():
                            st.markdown(part)
                    else:
                        code = part.strip()
                        with st.expander("💻 그래프 생성 코드", expanded=False):
                            st.code(code, language='python')
                        try:
                            import matplotlib.pyplot as plt
                            plt.close('all') # 이전 플롯 초기화
                            plt.rc('font', family='sans-serif') 
                            plt.rcParams['axes.unicode_minus'] = False
                            
                            local_vars = {'plt': plt, 'np': __import__('numpy')}
                            exec(code, globals(), local_vars)
                            
                            # AI 코드가 그린 현재 활성화된 figure 가져오기
                            fig = plt.gcf()
                            st.pyplot(fig)
                            plt.close('all')
                        except Exception as e:
                            st.error(f"⚠️ 그래프 렌더링 오류: {e}")
                
                orig_name = st.session_state.get("pdf_filename", "pdf")
                base_name = os.path.splitext(orig_name)[0]
                q_filename = app_utils.safe_filename(f"{i+1}_{base_name}_Q{i+1}")

                dl_col1, dl_col2 = st.columns([1, 1])
                with dl_col1:
                    _, final_sol = app_utils.parse_thinking_response(solutions[i])
                    st.download_button("💾 MD 저장", data=final_sol.encode('utf-8-sig'),
                                       file_name=f"{q_filename}.md", mime="text/markdown",
                                       key=f"dl_sol_{i}", use_container_width=True)
                with dl_col2:
                    if "pdf_bytes_cache" not in st.session_state:
                        st.session_state.pdf_bytes_cache = {}
                    
                    pdf_bytes = st.session_state.pdf_bytes_cache.get(i)
                    if pdf_bytes is None:
                        # Fallback for old sessions
                        pdf_bytes = app_utils.make_pdf_bytes(solutions[i])
                        st.session_state.pdf_bytes_cache[i] = pdf_bytes
                        
                    if pdf_bytes:
                        st.download_button("💾 PDF 저장", data=pdf_bytes,
                                           file_name=f"{q_filename}.pdf", mime="application/pdf",
                                           key=f"dl_sol_pdf_{i}", use_container_width=True)

        st.markdown("</div>", unsafe_allow_html=True)

    # 전체 합본 저장
    if solutions:
        all_sols = "\n\n---\n\n".join(
            f"## 문제 {questions[i]['number']}\n{questions[i]['content']}\n\n### 풀이\n{sol}"
            for i, sol in sorted(solutions.items())
        )
        orig_name = st.session_state.get("pdf_filename", "pdf")
        base_name = os.path.splitext(orig_name)[0]
        all_filename = app_utils.safe_filename(f"{base_name}_전체풀이")

        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            _, final_all = app_utils.parse_thinking_response(all_sols)
            st.download_button("💾 전체 풀이 저장 (.md)", data=final_all.encode('utf-8-sig'),
                               file_name=f"{all_filename}.md", mime="text/markdown",
                               key="dl_all_solutions", use_container_width=True)
        with col2:
            cache_key = hash(all_sols)
            if "pdf_bytes_cache" not in st.session_state:
                st.session_state.pdf_bytes_cache = {}
                
            if st.session_state.get("pdf_all_cache_key") != cache_key:
                with st.spinner("전체 풀이 PDF 변환 중..."):
                    st.session_state.pdf_bytes_cache["all"] = app_utils.make_pdf_bytes(all_sols)
                    st.session_state.pdf_all_cache_key = cache_key
                    
            pdf_bytes = st.session_state.pdf_bytes_cache.get("all")
            if pdf_bytes:
                st.download_button("💾 전체 풀이 저장 (.pdf)", data=pdf_bytes,
                                   file_name=f"{all_filename}.pdf", mime="application/pdf",
                                   key="dl_all_solutions_pdf", use_container_width=True)

        # 🔗 [NEW] 공유 링크 생성 섹션
        st.divider()
        sc1, sc2 = st.columns([2, 1])
        with sc1:
            st.info("💡 **이 풀이 노트를 다른 사람에게 공유하고 싶나요?** 링크를 생성하여 함께 볼 수 있습니다.")
        with sc2:
            if st.button("🔗 공유 링크 생성", key="btn_share_pdf", use_container_width=True, type="primary"):
                quiz_data = {
                    "type": "pdf_analysis",
                    "subject": st.session_state.get("pdf_filename", "PDF 문서"),
                    "questions": [
                        {
                            "number": q["number"],
                            "content": q["content"],
                            "solution": solutions.get(i, "아직 풀이가 생성되지 않았습니다.")
                        }
                        for i, q in enumerate(questions) if i in solutions
                    ]
                }
                
                if not quiz_data["questions"]:
                    st.error("❌ 공유할 풀이 데이터가 없습니다.")
                else:
                    with st.spinner("🚀 공유 링크 생성 중..."):
                        from src.db_manager import db
                        try:
                            redirect_uri = st.secrets.get("auth", {}).get("redirect_uri", "")
                            if redirect_uri and "localhost" not in redirect_uri:
                                base_url = redirect_uri.replace("oauth2callback", "")
                            else:
                                base_url = "http://localhost:8501/"
                        except:
                            base_url = "http://localhost:8501/"
                            
                        quiz_id = db.save_shared_quiz(quiz_data)
                        if quiz_id:
                            st.session_state.last_pdf_share_url = f"{base_url}?quiz_id={quiz_id}"
                            st.success("✅ 공유 링크가 생성되었습니다!")
                        else:
                            st.error("❌ 공유 링크 생성 실패 (DB 연동 오류)")

        if st.session_state.get("last_pdf_share_url"):
            st.code(st.session_state.last_pdf_share_url, language="text")
            st.warning("⚠️ 위 링크를 복사하여 공유하세요!")


def _solve_single_question(
    q: dict, content_text: str, images_b64: list[str] | None,
    provider: str, model: str, api_key: str, filename: str, mode: str,
) -> str:
    """문제 하나에 대해 AI에 풀이 요청"""
    context = ""
    if content_text:
        # 가급적 문제 주변 텍스트 2500자 정도를 컨텍스트로 제공
        needle = q["content"][:50]
        idx = content_text.find(needle)
        if idx >= 0:
            start = max(0, idx - 500)
            end = min(len(content_text), idx + 2000)
            context = content_text[start:end]
        else:
            context = content_text[:3000]

    system = SYSTEM_PROMPTS.get("step_solver", MATH_INSTRUCTION)
    if provider == P.LMSTUDIO:
        system = "<|think|>\n" + system

    user_prompt = f"[문서: {filename}]\n\n**문제 {q['number']}번**\n{q['content']}\n\n"
    if context:
        user_prompt += f"[문서 내 관련 컨텍스트]\n{context}\n\n"
    user_prompt += f"이 문제를 [{mode}]의 요구사항에 맞춰 단계별로 자세히 풀어주세요."

    return call_ai(system, user_prompt, provider, model, api_key,
                   images_b64=images_b64 if not context else None)


def _run_pdf_analysis(
    file_bytes: bytes,
    filename: str,
    page_count: int,
    analysis_type: str,
    custom_question: str,
    page_range: str,
    provider: str,
    model: str,
    api_key: str,
    user_mode: str = "교육자용",
) -> None:
    """PDF 분석 실행: 문제별 모드와 일반 모드로 분기."""
    st.session_state.pdf_user_mode_final = user_mode

    # ── 공통: 텍스트/이미지 추출 ────────────────────────────────
    with st.status("📄 PDF 내용 추출 중...", expanded=True) as status:
        st.write("📝 텍스트 추출 시도 중...")
        content_text, images_b64, method = app_utils._pdf_extract_content(
            file_bytes, page_count, page_range
        )
        if method == "text":
            st.write(f"✅ 텍스트 추출 완료 ({len(content_text):,}자)")
        elif method == "vision":
            st.write(f"🖼️ 이미지 변환 완료 ({len(images_b64)}페이지)")
        else:
            st.write("⚠️ 텍스트 품질 낮음, 가능한 범위에서 진행")

        # ── 문제별 풀이 모드 ─────────────────────────────────────
        if analysis_type.startswith("🔢"):
            st.write("🔍 AI가 문제 목록 추출 중...")

            q_system = (
                "당신은 시험지 분석 전문가입니다.\n"
                "제공된 문서에서 모든 시험/연습 문제를 찾아 정확히 반환하세요.\n"
                "반드시 아래 JSON 배열 형식만 출력하세요. 다른 텍스트는 금지입니다:\n"
                '[{"번호":"1","내용":"문제 전체 텍스트"},{"번호":"2","내용":"..."}]\n'
                f"{MATH_INSTRUCTION}"
            )
            q_prompt = (
                "첨부된 문서(파일 또는 이미지)에서 기재된 모든 시험 문항이나 연습 문제를 찾아 "
                "JSON 배열 형식으로만 반환하세요. JSON 외의 부가적인 인사말이나 마크다운 설명은 일절 생략하세요.\n"
                "문제가 없다면 빈 배열 []을 반환하세요.\n\n"
            )
            if content_text:
                q_prompt += f"[문서 내용]\n{content_text[:100000]}"
            else:
                q_prompt += "[참고]: 문서 텍스트가 부족하여 첨부된 이미지를 대신 분석해야 합니다."

            debug_raw_responses = []
            try:
                questions = []
                images_list = images_b64 if images_b64 else []
                if images_list:
                    chunk_size = get_max_pdf_pages(provider)
                    for i in range(0, len(images_list), chunk_size):
                        chunk = images_list[i:i+chunk_size]
                        st.write(f"🔍 이미지에서 문제 목록 추출 중... ({i+1}~{min(i+chunk_size, len(images_list))}장)")
                        raw_qs = call_ai(q_system, q_prompt, provider, model, api_key, images_b64=chunk)
                        debug_raw_responses.append(raw_qs)
                        _, clean_qs = app_utils.parse_thinking_response(raw_qs)
                        questions.extend(app_utils._parse_question_list(clean_qs or raw_qs))
                else:
                    raw_qs = call_ai(q_system, q_prompt, provider, model, api_key, images_b64=None)
                    debug_raw_responses.append(raw_qs)
                    _, clean_qs = app_utils.parse_thinking_response(raw_qs)
                    questions = app_utils._parse_question_list(clean_qs or raw_qs)
            except Exception as e:
                st.error(f"❌ 문제 추출 실패: {e}")
                status.update(label="실패", state="error")
                return

            if not questions:
                with st.expander("🛠 디버그: AI 원본 응답 확인", expanded=True):
                    for idx, r in enumerate(debug_raw_responses):
                        st.text(f"--- Chunk {idx+1} Raw Output ---\n{r}")
                st.warning("⚠️ 문제를 감지하지 못했습니다. AI가 반환한 위 디버그 텍스트를 확인해주세요.")
                status.update(label="문제 미감지", state="error")
                return

            # 세션에 저장
            st.session_state.pdf_questions = questions
            st.session_state.pdf_solutions = {}
            st.session_state.pdf_content_text = content_text
            st.session_state.pdf_images_b64 = images_b64
            st.session_state.pdf_extraction_method = method
            st.session_state.pdf_filename = filename
            st.session_state.pop("pdf_solve_all", None)

            st.write(f"✅ {len(questions)}개 문제 감지 완료!")
            status.update(label=f"✅ {len(questions)}개 문제 감지!", state="complete", expanded=False)
            st.rerun()
            return

        # ── 일반 분석 모드 ────────────────────────────────────────
        type_label = analysis_type.split(" ", 1)[1]
        st.write(f"🤖 AI 분석 중 ({method})...")

        content_for_prompt = content_text or f"{filename}의 이미지를 분석해주세요."

        if analysis_type.startswith("🔍") and custom_question.strip():
            user_prompt = (
                f"다음 문서에 대해 [{user_mode}] 관점에서 질문에 답해주세요.\n\n"
                f"[질문]: {custom_question}\n\n[문서 내용]:\n{content_for_prompt}"
            )
        else:
            user_prompt = (
                f"다음 PDF 문서({filename})에 대해 [{user_mode}]을 위한 [{type_label}]을 수행해주세요.\n\n"
                f"[문서 내용]:\n{content_for_prompt}"
            )

        system = SYSTEM_PROMPTS["pdf_analyzer"]

        try:
            max_p = get_max_pdf_pages(provider)
            analysis_images = images_b64
            if images_b64 and len(images_b64) > max_p:
                st.warning(f"⚠️ 일반 분석 모드에서는 컨텍스트 제한으로 앞의 {max_p}장 이미지만 분석됩니다. 모든 페이지 문제를 추출하려면 '문제별 풀이' 모드를 활용하세요.")
                analysis_images = images_b64[:max_p]

            result = call_ai(system, user_prompt, provider, model, api_key,
                             images_b64=analysis_images)
            status.update(label="✅ 분석 완료!", state="complete", expanded=False)
            
            # 일반 결과 세션에 저장
            st.session_state.pdf_general_result = result
            st.session_state.pdf_general_method = method
            st.session_state.pdf_general_type = type_label
            st.session_state.pdf_filename = filename
            st.session_state.pdf_content_text = content_text
        except Exception as e:
            st.error(f"❌ AI 분석 오류: {e}")
            status.update(label="분석 실패", state="error")
            return

def _render_pdf_general_result() -> None:
    """PDF 일반 분석 결과를 UI에 표시하고 다운로드 버튼 지원"""
    if "pdf_general_result" not in st.session_state:
        return
        
    result = st.session_state.pdf_general_result
    method = st.session_state.pdf_general_method
    type_label = st.session_state.pdf_general_type
    filename = st.session_state.pdf_filename
    content_text = st.session_state.get("pdf_content_text", "")

    # 결과 출력
    badge_color = "#10b981" if method == "text" else "#f59e0b"
    badge_label = "📝 텍스트 추출" if method == "text" else "🖼️ 비전 AI"
    st.markdown(
        f'<span style="background:{badge_color}22;border:1px solid {badge_color};'
        f'border-radius:6px;padding:3px 10px;font-size:0.8rem;color:{badge_color};">'
        f'{badge_label}</span>',
        unsafe_allow_html=True,
    )
    mode = st.session_state.get("user_mode", "교육자용")
    st.subheader(f"📋 {type_label} 결과 ({mode})")
    
    # 생각 과정 제거 후 본문만 렌더링
    _, final_content = app_utils.parse_thinking_response(result)
    st.markdown(final_content, unsafe_allow_html=True)

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        thinking, final_md = app_utils.parse_thinking_response(result)
        suffix = "educator" if "교육자" in mode else "student"
        st.download_button("💾 결과 저장 (.md)", data=final_md.encode('utf-8-sig'),
                           file_name=f"analysis_{suffix}.md", mime="text/markdown",
                           key="dl_pdf_md_gen", use_container_width=True)
    with col_b:
        pdf_bytes = app_utils.make_pdf_bytes(result)
        if pdf_bytes:
            st.download_button("💾 결과 저장 (.pdf)", data=pdf_bytes,
                               file_name=f"analysis_{suffix}.pdf", mime="application/pdf",
                               key="dl_pdf_pdf_gen", use_container_width=True)
    with col_c:
        if method == "text" and content_text:
            st.download_button("💾 추출 텍스트 저장 (.txt)", data=content_text.encode('utf-8-sig'),
                               file_name="extracted_text.txt", mime="text/plain",
                               key="dl_pdf_txt_gen", use_container_width=True)






