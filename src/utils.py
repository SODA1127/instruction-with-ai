from __future__ import annotations
import re
import io
import base64
import os

try:
    import markdown
except ImportError:
    markdown = None

try:
    from weasyprint import HTML
    try:
        from weasyprint.fonts import FontConfiguration
    except ImportError:
        try:
            from weasyprint.text.fonts import FontConfiguration
        except ImportError:
            FontConfiguration = None
except (ImportError, Exception):
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
    clean = re.sub(r'[^\w\s\-\.]', '', filename)
    clean = clean.replace(' ', '_')
    return clean if clean.strip() else "downloaded_file"

def make_pdf_bytes(markdown_text: str) -> bytes:
    try:
        if markdown is None or HTML is None:
            return b""
        html_body = markdown.markdown(markdown_text, extensions=['tables', 'fenced_code'])
        full_html = f"""
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: sans-serif; line-height: 1.6; padding: 40px; }}
                h1, h2, h3 {{ color: #1a202c; border-bottom: 2px solid #edf2f7; }}
                table {{ width: 100%; border-collapse: collapse; }}
                th, td {{ border: 1px solid #e2e8f0; padding: 12px; }}
            </style>
        </head>
        <body>{html_body}</body>
        </html>
        """
        font_config = FontConfiguration() if FontConfiguration else None
        return HTML(string=full_html).write_pdf(font_config=font_config)
    except Exception:
        return b""

def parse_thinking_response(text: str) -> tuple[str, str]:
    def clean_output(content: str) -> str:
        def repl_block(match): return match.group(0).replace("$", "")
        content = re.sub(r"```[\s\S]*?```", repl_block, content)
        def repl_inline(match):
            inner = match.group(1).strip()
            if re.search(r'[\^\\\{\}]', inner): return match.group(0)
            if re.search(r'[\[\]\'\"_\.]', inner) or re.search(r'^[a-zA-Z0-9\s,=\+\-\*]+$', inner) or inner in [",", "[ ]", "[]"]:
                return f"`{inner}`"
            return match.group(0)
        content = re.sub(r"\$([^\$\n]+)\$", repl_inline, content)
        content = re.sub(r"<br\s*/?>", "\n", content, flags=re.IGNORECASE)
        content = content.replace("\\*\\*", "**").replace("\\*", "*")
        content = re.sub(r'([①-⑩]|\([1-5]\))', r'\n\1', content)
        def repl_details(match):
            inner = match.group(0).strip()
            return f'\n\n<details>\n<summary>💡 정답 및 해설 확인하기</summary>\n<div markdown="1">\n\n{inner}\n\n</div>\n</details>\n\n'
        pattern = r'\n\s*((?:정답|답|해설)\s*[:：]?\s*[\s\S]*?)(?=\n\s*(?:문항|###|#|\d+[\.번])|$)'
        content = re.sub(pattern, repl_details, content)
        return re.sub(r'\n{3,}', '\n\n', content).strip()

    m = re.search(r'<\|channel>thought\n(.*?)<channel\|>', text, re.DOTALL)
    if m: return m.group(1).strip(), clean_output(text[m.end():].strip())
    m = re.search(r'<think>(.*?)</think>', text, re.DOTALL)
    if m: return m.group(1).strip(), clean_output(re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip())
    return "", clean_output(text)

def parse_quiz_markdown(text: str) -> list[dict]:
    lines = text.split('\n')
    questions, current_q = [], None
    q_start_re = re.compile(r'(?:[\*#\-\s]*)(?:문항\s*)?(\d+)[번\.]\s*(.*)', re.IGNORECASE)
    opt_start_re = re.compile(r'^\s*(?:[①-⑩\(\)\-\*]|[1-5][\)\.]|(?:\([1-5]\)))\s*(.*)')
    ans_re, exp_re = re.compile(r'(?:정답|답)\s*[:：]?\s*(.*)', re.IGNORECASE), re.compile(r'(?:해설)\s*[:：]?\s*(.*)', re.IGNORECASE)
    quiz_started = False
    for line in lines:
        raw_line = line
        line = line.strip()
        if not line: continue
        q_match = q_start_re.search(line)
        if q_match and q_match.start() < 10:
            quiz_started = True 
            if current_q: questions.append(current_q)
            current_q = {"number": q_match.group(1), "content": q_match.group(2).strip(), "options": [], "answer": "", "explanation": "", "raw": raw_line}
            continue
        if not quiz_started or not current_q: continue
        opt_match = opt_start_re.match(line)
        if opt_match:
            if opt_match.group(1).strip():
                current_q["options"].append(opt_match.group(1).strip())
                current_q["raw"] += "\n" + raw_line
                continue
        a_match = ans_re.search(line)
        if a_match and a_match.start() < 10:
            current_q["answer"] = a_match.group(1).strip()
            current_q["raw"] += "\n" + raw_line
            continue
        e_match = exp_re.search(line)
        if e_match and e_match.start() < 10:
            current_q["explanation"] = e_match.group(1).strip()
            current_q["raw"] += "\n" + raw_line
            continue
        if not current_q["options"] and not current_q["answer"] and not current_q["explanation"]:
            current_q["content"] += " " + line
        elif current_q["explanation"]:
            current_q["explanation"] += " " + line
        current_q["raw"] += "\n" + raw_line
    if current_q: questions.append(current_q)
    return questions

def extract_pdf_text(file_bytes: bytes) -> tuple[str, int]:
    if not _PYPDF_OK: return "", 0
    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    pages = [f"[페이지 {i + 1}]\n{p.extract_text().strip()}" for i, p in enumerate(reader.pages) if p.extract_text()]
    return "\n\n".join(pages), len(reader.pages)

def pdf_pages_to_images(file_bytes: bytes, max_pages: int = 20, selected_pages: set[int] | None = None) -> list[str]:
    if not _FITZ_OK: return []
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    images = []
    for i in range(len(doc)):
        if selected_pages is not None and i not in selected_pages: continue
        if len(images) >= max_pages: break
        pix = doc[i].get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
        images.append(base64.b64encode(pix.tobytes("jpeg")).decode("utf-8"))
    doc.close()
    return images

def is_pdf_text_sufficient(text: str, page_count: int) -> bool:
    if not text.strip() or page_count == 0: return False
    return (len(text.replace("\n", "").replace(" ", "")) / page_count) >= 80

def _pdf_extract_content(file_bytes: bytes, page_count: int, page_range: str) -> tuple[str, list[str] | None, str]:
    selected_pages = None
    if page_range.strip():
        try:
            selected_pages = set()
            for part in page_range.replace(" ", "").split(","):
                if "-" in part:
                    a, b = part.split("-")
                    selected_pages.update(range(int(a) - 1, int(b)))
                else: selected_pages.add(int(part) - 1)
        except Exception: selected_pages = None
    txt, n_p = extract_pdf_text(file_bytes)
    if selected_pages and txt:
        filtered, cur = [], 0
        for ln in txt.split("\n"):
            m = re.match(r"\[페이지 (\d+)\]", ln)
            if m: cur = int(m.group(1)) - 1
            if m is None or cur in selected_pages: filtered.append(ln)
        txt = "\n".join(filtered)
    if is_pdf_text_sufficient(txt, n_p or max(1, page_count)): return txt, None, "text"
    if _FITZ_OK: return "", pdf_pages_to_images(file_bytes, 999, selected_pages), "vision"
    return txt, None, "text"

def _parse_question_list(text: str) -> list[dict]:
    matches = re.findall(r'(\d+)[\.번]\s*(.*?)(?=\n\s*\d+[\.번]|$)', text, re.DOTALL)
    return [{"번호": num, "내용": content.strip()} for num, content in matches]
