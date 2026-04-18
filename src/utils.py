from __future__ import annotations
import re
import io
import base64
import os
try:
    from weasyprint import HTML
    try:
        from weasyprint.fonts import FontConfiguration
    except ImportError:
        try:
            from weasyprint.text.fonts import FontConfiguration
        except ImportError:
            FontConfiguration = None
except ImportError:
    HTML = None
    FontConfiguration = None

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

def encode_image_to_base64(image_file):
    return base64.b64encode(image_file.read()).decode("utf-8")

def safe_filename(filename: str) -> str:
    """파일명에서 안전하지 않은 문자를 제거하거나 변경합니다."""
    # 공백은 언더바로, 한글/알파벳/숫자/언더바/하이픈/점 제외 모두 제거
    clean = re.sub(r'[^\w\s\-\.]', '', filename)
    clean = clean.replace(' ', '_')
    # ASCII 범위 밖의 문자가 있어도 OS는 보통 지원하지만, 극단적인 클린업을 위해:
    # (필요시 한글 유지)
    return clean if clean.strip() else "downloaded_file"

def make_pdf_bytes(markdown_text: str) -> bytes:
    """마크다운을 PDF 바이트로 변환합니다 (WeasyPrint 사용)."""
    try:
        # ── 1. 마크다운을 간단한 HTML로 변환 (기본 태그만 대응) ────────────────
        import markdown
        # latex2mathml 등의 수급이 불안정할 수 있으므로 간단한 변환기 사용
        # (실제 환경에 따라 확장 가능)
        html_body = markdown.markdown(markdown_text, extensions=['tables', 'fenced_code'])
        
        # ── 2. 이모지 및 특수문자 깨짐 방지를 위한 폰트 설정 ──────────────────
        # Linux/Streamlit Cloud 환경에서는 'Noto Color Emoji' 등이 필요함
        full_html = f"""
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ 
                    font-family: 'Noto Sans KR', 'Spoqa Han Sans', sans-serif, 'Apple Color Emoji', 'Segoe UI Emoji', 'Noto Color Emoji';
                    line-height: 1.6; color: #333; padding: 40px; 
                }}
                h1, h2, h3 {{ color: #1a202c; border-bottom: 2px solid #edf2f7; padding-bottom: 8px; }}
                code {{ background: #f7fafc; padding: 2px 4px; border-radius: 4px; font-family: monospace; }}
                pre {{ background: #f7fafc; padding: 16px; border-radius: 8px; border: 1px solid #e2e8f0; overflow-x: auto; }}
                blockquote {{ border-left: 4px solid #e2e8f0; padding-left: 16px; color: #718096; italic; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 16px; }}
                th, td {{ border: 1px solid #e2e8f0; padding: 12px; text-align: left; }}
                th {{ background: #edf2f7; font-weight: bold; }}
            </style>
        </head>
        <body>
            {html_body}
        </body>
        </html>
        """
        
        # ── 5. PDF 생성 ───────────────────────────────────────────
        if HTML is None:
            return b""
            
        font_config = FontConfiguration() if FontConfiguration else None
        pdf_bytes = HTML(string=full_html).write_pdf(font_config=font_config)
        return pdf_bytes
        
    except Exception as e:
        import streamlit as st
        try:
            st.error(f"❌ 고품질 PDF 생성 실패: {e}")
        except:
            pass
        return b""

def parse_thinking_response(text: str) -> tuple[str, str]:
    def clean_output(content: str) -> str:
        # 1. ```...``` 형태의 코드 블록 내부 $ 제거
        def repl_block(match):
            return match.group(0).replace("$", "")
        content = re.sub(r"```[\s\S]*?```", repl_block, content)
        
        # 2. 인라인 $...$ 보정 로직 정밀화
        def repl_inline(match):
            inner = match.group(1).strip()
            # (A) 명백한 LaTeX 명령어(\로 시작)나 위첨자(^), 중괄호({})가 있으면 진짜 수식
            is_real_latex = re.search(r'[\^\\\{\}]', inner)
            if is_real_latex:
                return match.group(0)
            # (B) 대괄호([]), 따옴표(', "), 언더바(_), 마침표(.) 등이 있으면 코드(변수/리스트 등)로 판단
            is_code_marker = re.search(r'[\[\]\'\"_\.]', inner)
            # (C) 단순 알파벳, 숫자, 콤마, 등호(=), 연산자(+, -, *) 등으로만 구성된 경우
            if is_code_marker or re.search(r'^[a-zA-Z0-9\s,=\+\-\*]+$', inner) or inner in [",", "[ ]", "[]"]:
                return f"`{inner}`"
            return match.group(0)
            
        content = re.sub(r"\$([^\$\n]+)\$", repl_inline, content)
        # 3. <br> 태그 보정
        content = re.sub(r"<br\s*/?>", "\n", content, flags=re.IGNORECASE)
        # 4. 이스케이프된 마크다운 별표(\*\*) 복원
        content = content.replace("\\*\\*", "**").replace("\\*", "*")
        return content

    m = re.search(r'<\|channel>thought\n(.*?)<channel\|>', text, re.DOTALL)
    if m:
        thinking = m.group(1).strip()
        final = text[m.end():].strip()
        return thinking, clean_output(final)

    m = re.search(r'<think>(.*?)</think>', text, re.DOTALL)
    if m:
        thinking = m.group(1).strip()
        final = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
        return thinking, clean_output(final)

    return "", clean_output(text)

def parse_quiz_markdown(text: str) -> list[dict]:
    """줄 단위 상태 머신 방식으로 퀴즈 문항을 정교하게 추출합니다."""
    # 사고 과정 제거 후의 순수 텍스트만 처리
    lines = text.split('\n')
    questions = []
    current_q = None
    
    # 문항 시작 기호 패턴 (문항 1., 1., 1번. 등)
    q_start_re = re.compile(r'^\s*(?:문항\s*)?(\d+)[번\.]\s*(.*)', re.IGNORECASE)
    # 보기 시작 기호 패턴 (①-⑩, (1)-(5), 1)-5), 1. 등)
    # 텍스트 중간의 숫자를 보기로 오인하지 않도록 줄 시작(^)에서만 매칭
    opt_start_re = re.compile(r'^\s*(?:[①-⑩\(\)]|[1-5][\)\.]|(?:\([1-5]\)))\s*(.*)')
    # 정답/해설 패턴
    ans_re = re.compile(r'^\s*(?:정답|답)\s*[:：]?\s*(.*)', re.IGNORECASE)
    exp_re = re.compile(r'^\s*(?:해설)\s*[:：]?\s*(.*)', re.IGNORECASE)

    quiz_started = False
    
    for line in lines:
        raw_line = line
        line = line.strip()
        if not line: continue
        
        # 1. 새로운 문항 시작 확인
        q_match = q_start_re.match(line)
        if q_match:
            quiz_started = True # 첫 문항을 만난 시점부터 파싱 시작
            if current_q:
                questions.append(current_q)
            current_q = {
                "number": q_match.group(1),
                "content": q_match.group(2).strip(),
                "options": [],
                "answer": "",
                "explanation": "",
                "raw": raw_line
            }
            continue
            
        if not quiz_started or not current_q:
            continue
            
        # 2. 보기 확인
        opt_match = opt_start_re.match(line)
        if opt_match:
            opt_text = opt_match.group(1).strip()
            # "10 진법" 같은 단어와 "1. 보기"를 구분하기 위해 길이가 너무 짧은 패턴 제외
            if opt_text:
                current_q["options"].append(opt_text)
                current_q["raw"] += "\n" + raw_line
                continue
                
        # 3. 정답 확인
        a_match = ans_re.match(line)
        if a_match:
            current_q["answer"] = a_match.group(1).strip()
            current_q["raw"] += "\n" + raw_line
            continue
            
        # 4. 해설 확인
        e_match = exp_re.match(line)
        if e_match:
            current_q["explanation"] = e_match.group(1).strip()
            current_q["raw"] += "\n" + raw_line
            continue
            
        # 5. 기타: 문제 본문의 연장이거나 해설의 연장
        if current_q["explanation"]:
            current_q["explanation"] += " " + line
        elif not current_q["options"] and not current_q["answer"]:
            # 보기가 나오기 전이면 문제 본문의 연장으로 간주
            current_q["content"] += " " + line
        
        current_q["raw"] += "\n" + raw_line

    if current_q:
        questions.append(current_q)
        
    return questions

def extract_pdf_text(file_bytes: bytes) -> tuple[str, int]:
    if not _PYPDF_OK:
        return "", 0
    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        pages.append(f"[페이지 {i + 1}]\n{text.strip()}")
    return "\n\n".join(pages), len(reader.pages)

def pdf_pages_to_images(file_bytes: bytes, max_pages: int = 20, selected_pages: set[int] | None = None) -> list[str]:
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
        mat = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("jpeg")
        images.append(base64.b64encode(img_bytes).decode("utf-8"))
    doc.close()
    return images

def is_pdf_text_sufficient(text: str, page_count: int) -> bool:
    if not text.strip() or page_count == 0:
        return False
    # 상수 정의가 없으므로 직접 수치 입력
    avg_chars = len(text.replace("\n", "").replace(" ", "")) / page_count
    return avg_chars >= 80

def _pdf_extract_content(file_bytes: bytes, page_count: int, page_range: str) -> tuple[str, list[str] | None, str]:
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
        images = pdf_pages_to_images(file_bytes, 999, selected_pages)
        return "", images, "vision"
    return extracted_text, None, "text"

def _parse_question_list(text: str) -> list[dict]:
    # 기존에 정의된 문제 리스트 파서 (일관성 유지)
    questions = []
    # 단순 패턴 매칭
    matches = re.findall(r'(\d+)[\.번]\s*(.*?)(?=\n\s*\d+[\.번]|$)', text, re.DOTALL)
    for num, content in matches:
        questions.append({"번호": num, "내용": content.strip()})
    return questions
