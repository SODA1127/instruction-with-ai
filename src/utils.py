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
    """마크다운 텍스트에서 퀴즈 문항을 엄격하게 추출합니다."""
    # 1. 도입부 제거 (첫 번째 문항 번호가 나올 때까지)
    # 문항 1., 1번., 1. 등으로 시작하는 지점 찾기
    start_match = re.search(r'(?:\n|^)(?:(?:문항\s*)?1[\.번])', text)
    if start_match:
        text = text[start_match.start():]
    
    questions = []
    # 2. 문항별 블록 분리 (줄 시작 부분의 '문항 N.' 또는 'N.' 패턴 사용)
    blocks = re.split(r'\n(?=(?:문항\s*)?\d+[번\.])', '\n' + text.strip())
    
    for block in blocks:
        block = block.strip()
        if not block: continue
        
        # 문제 번호와 전체 설명 추출
        head_m = re.match(r'(?:문항\s*)?(\d+)[번\.]\s*(.*)', block, re.DOTALL)
        if not head_m: continue
        
        q_num = head_m.group(1)
        full_body = head_m.group(2)
        
        # 3. 정답 및 해설 분리
        # 정답: 혹은 답: 이후를 정답/해설 영역으로 분리
        ans_split = re.split(r'\n\s*(?:정답|답|해설)\s*[:：]?', full_body, flags=re.IGNORECASE)
        question_area = ans_split[0].strip()
        ans_area = "\n".join(ans_split[1:]).strip() if len(ans_split) > 1 else ""
        
        # 4. 보기(Options) 추출
        # 줄 시작이 ①-⑩, (1)-(5), 1)-5) 인 경우만 보기로 인정
        option_lines = re.findall(r'^\s*([①-⑩\(\d][\d\)\. ]+.*)', question_area, re.MULTILINE)
        
        # 실제 보기 텍스트만 추출 (기호 제거)
        options = []
        for opt in option_lines:
            # 보기 기호(예: ①, (1), 1.) 제거
            clean_opt = re.sub(r'^[\s\(①-⑩\d]+[\)\. ]+\s*', '', opt).strip()
            if clean_opt and len(clean_opt) > 1:
                options.append(clean_opt)
        
        # 문제 본문 (보기 기호가 시작되기 전까지의 텍스트)
        content_main = re.split(r'\n\s*[①\(\d]', question_area)[0].strip()
        
        # 정답 추출 (간단하게 첫 줄 혹은 특정 패턴)
        answer = ans_area.split('\n')[0].strip() if ans_area else ""
        explanation = "\n".join(ans_area.split('\n')[1:]).strip() if ans_area else ""
        
        # 만약 정갑/해설 키워드가 없었다면 영역 내에서 찾아보기
        if not answer:
            ans_internal = re.search(r'(?:정답|답)\s*[:：]?\s*([^\n]+)', block)
            if ans_internal: answer = ans_internal.group(1).strip()
        
        questions.append({
            "number": q_num,
            "content": content_main,
            "options": options,
            "answer": answer,
            "explanation": explanation,
            "raw": block
        })
    
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
