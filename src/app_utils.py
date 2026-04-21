from __future__ import annotations
import re
import io
import json
import os
import base64

# PDF 처리 라이브러리 (선택적 임포트)
try:
    import pypdf
    _PYPDF_OK = True
except ImportError:
    _PYPDF_OK = False

try:
    import fitz  # pymupdf
    _FITZ_OK = True
except ImportError:
    _FITZ_OK = False

from src.config import _PDF_TEXT_MIN_CHARS_PER_PAGE
_PDF_MAX_IMAGE_PAGES = 10

# 순수 Python 표준 라이브러리만 사용하는 함수들은 최상위에 배치 (에러 방지)
def encode_image_to_base64(image_file):
    return base64.b64encode(image_file.read()).decode("utf-8")

def safe_filename(filename: str) -> str:
    clean = re.sub(r'[^\w\s\-\.]', '', filename)
    clean = clean.replace(' ', '_')
    return clean if clean.strip() else "downloaded_file"

def parse_quiz_markdown(text: str) -> list[dict]:
    """상태 머신 방식을 사용하여 퀴즈 문항을 정교하게 추출합니다."""
    lines = text.split('\n')
    questions = []
    current_q = None
    
    # 정규식 패턴 정의
    q_start_re = re.compile(r'^\s*(?:[^\w\s]\s*)*(?:(?:문항|질문|문제|Q)\s*(\d+)[\.번\)]?|(\d+)(?:번\s*\.?|\.|\)))\s*(.*)', re.IGNORECASE)
    opt_start_re = re.compile(r'^\s*(?:[\-\*]\s+)?([①-⑩]|[1-5][\)\.]|(?:\([1-5]\))|[1-5](?=\s*[\(\[A-E가-힣]))\s*(.*)')
    ans_re = re.compile(r'(?:정답|답)\s*(?:\*\*|\*)?[:：]?\s*(?:\*\*|\*)?\s*([1-5①-⑤]|[A-Ea-e]+)', re.IGNORECASE)
    
    in_answer_block = False
    
    for line in lines:
        raw_line = line
        line = line.strip()
        if not line: continue
        
        if "[ANSWER_START]" in line:
            in_answer_block = True
            continue
        if "[ANSWER_END]" in line:
            in_answer_block = False
            continue
            
        q_match = q_start_re.match(line)
        is_explicit_q = bool(re.search(r'문항|문제|질문|Q', line, re.IGNORECASE))
        
        if q_match:
            num = q_match.group(1) or q_match.group(2)
            content = q_match.group(3) or ""
            
            is_sub_item = False
            if current_q:
                try:
                    curr_num_val = int(re.sub(r'\D', '', str(current_q["number"])))
                    new_num_val = int(re.sub(r'\D', '', str(num)))
                    if new_num_val <= curr_num_val and not is_explicit_q:
                        is_sub_item = True
                except: pass

                if not is_sub_item and (in_answer_block or current_q["explanation"]):
                    if not is_explicit_q and not line.startswith("###"):
                        is_sub_item = True

            if is_explicit_q:
                in_answer_block = False
                is_sub_item = False

            if in_answer_block or is_sub_item:
                if current_q:
                    if in_answer_block:
                        current_q["explanation"] += "\n" + raw_line
                    else:
                        current_q["content"] += "\n" + raw_line
                continue

            if current_q:
                questions.append(current_q)
            
            current_q = {
                "number": num,
                "content": content.strip(),
                "options": [],
                "answer": "",
                "explanation": "",
                "raw": raw_line
            }
            continue
            
        if not current_q:
            continue
            
        if in_answer_block:
            a_match = ans_re.search(line)
            if a_match and not current_q["answer"]:
                current_q["answer"] = a_match.group(1).strip()
            
            clean_line = re.sub(r'</?(?:b|style|details|summary|div)[^>]*>|\[ANSWER_START\]|\[ANSWER_END\]', '', raw_line, flags=re.IGNORECASE)
            if clean_line.strip():
                current_q["explanation"] += (("\n" if current_q["explanation"] else "") + clean_line.strip())
            continue

        opt_match = opt_start_re.match(line)
        if opt_match and not current_q["answer"] and not current_q["explanation"]:
            marker = opt_match.group(1)
            option_text = f"{marker} {opt_match.group(2).strip()}"
            
            has_circle = any(any(c in "①②③④⑤⑥⑦⑧⑨⑩" for c in o) for o in current_q["options"])
            new_is_circle = any(c in "①②③④⑤⑥⑦⑧⑨⑩" for c in marker) if marker else False
            
            if has_circle and not new_is_circle:
                current_q["content"] += "\n" + raw_line
            elif not has_circle and new_is_circle:
                current_q["content"] += "\n" + "\n".join(current_q["options"])
                current_q["options"] = [option_text]
            else:
                current_q["options"].append(option_text)
        else:
            a_match = ans_re.search(line)
            if a_match:
                current_q["answer"] = a_match.group(1).strip()
            if "해설" in line or "이유" in line:
                current_q["explanation"] += (("\n" if current_q["explanation"] else "") + line)
            elif current_q["explanation"]:
                current_q["explanation"] += "\n" + line
            elif not current_q["options"]:
                current_q["content"] += "\n" + line
            else:
                current_q["explanation"] += (("\n" if current_q["explanation"] else "") + line)
        
        current_q["raw"] += "\n" + raw_line

    if current_q:
        questions.append(current_q)
    for q in questions:
        q["content"] = q["content"].strip("-*# ")
        q["answer"] = q["answer"].replace('①','1').replace('②','2').replace('③','3').replace('④','4').replace('⑤','5')
    return questions

def clean_text_symbols(text: str) -> str:
    """텍스트 내의 불필요한 수학 기호($) 및 코드 백틱 중복 문제를 정제합니다."""
    if not text: return ""
    text = re.sub(r'\${4,}', '$$', text)
    return text.strip()

def parse_quiz_json(text: str) -> list[dict]:
    """텍스트 내의 JSON 블록을 찾아 추출하고 리스트 형태로 반환합니다."""
    preamble_match = re.search(r'(\[|\{|\s*```json)', text)
    if preamble_match and preamble_match.start() > 0:
        text = text[preamble_match.start():]

    text = re.sub(r'<\|channel>.*?<channel\|>', '', text, flags=re.DOTALL)
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    text = re.sub(r'</?(?:details|summary|b|style|div|span)[^>]*>', '', text, flags=re.IGNORECASE)
    
    try:
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if json_match:
            data = json.loads(json_match.group(1))
        else:
            json_match = re.search(r'\[\s*\{.*\}\s*\]', text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
            else:
                return parse_quiz_markdown(text)
        
        if isinstance(data, dict):
            if "questions" in data: data = data["questions"]
            elif "quiz" in data: data = data["quiz"]
            else: data = [data]
        
        for q in data:
            q.setdefault("number", "1")
            q.setdefault("type", "multiple_choice" if q.get("options") else "short_answer")
            q["content"] = clean_text_symbols(str(q.get("content", "")))
            q["answer"] = clean_text_symbols(str(q.get("answer", "")))
            q["explanation"] = clean_text_symbols(str(q.get("explanation", "")))
            if q.get("options"):
                q["options"] = [clean_text_symbols(str(opt)) for opt in q["options"]]
            if q["answer"]:
                q["answer"] = q["answer"].replace('①','1').replace('②','2').replace('③','3').replace('④','4').replace('⑤','5')
        return data
    except Exception as e:
        print(f"JSON Parsing Error: {e}")
        return parse_quiz_markdown(text)

def questions_to_markdown(questions: list[dict]) -> str:
    """JSON 데이터를 사람이 읽기 좋은 예쁜 마크다운 문서로 변환합니다."""
    md = ""
    for q in questions:
        md += f"### 문항 {q.get('number', '')}\n\n"
        
        # 이미지 참조가 있는 경우 마크다운에 표시
        img_idx = q.get("image_index")
        if img_idx is not None:
             md += f"*(그림/그래프 참고: 이미지 {img_idx + 1})*\n\n"
             
        md += f"{q.get('content', '')}\n\n"
        if q.get("options"):
            for opt in q["options"]:
                md += f"- {opt}\n"
            md += "\n"
        md += "[ANSWER_START]\n"
        md += f"**✅ 정답:** {q.get('answer', '')}\n\n"
        md += f"**📝 해설:**\n{q.get('explanation', '')}\n"
        md += "[ANSWER_END]\n\n"
        md += "---\n\n"
    return md.strip()

def parse_thinking_response(text: str) -> tuple[str, str]:
    def clean_output(content: str) -> str:
        if "```json" in content or content.strip().startswith("["):
            return content.strip()
            
        def repl_block(match): return match.group(0).replace("$", "")
        content = re.sub(r"```[\s\S]*?```", repl_block, content)
        content = clean_text_symbols(content)
        content = re.sub(r"<br\s*/?>", "\n", content, flags=re.IGNORECASE)
        
        # 줄바꿈 최적화 및 퀴즈 섹션 분리
        content = re.sub(r'([^\n\-\*:#])\s+([①-⑩]|\([1-5]\)|[1-5][\)\.]|[1-5]\s*\(?[A-E가-힣]\)?)', r'\1\n\2', content)
        content = re.sub(r'(문항|문제|질문|Q)\n\s*(\d+)', r'\1 \2', content)
        
        def repl_details(match):
            inner = match.group(1).strip()
            return f"\n\n[ANSWER_START]\n{inner}\n[ANSWER_END]\n"
        
        lookahead = r'(?=\n\s*(?:[^\w\s]\s*)*(?:(?:문항|질문|문제|Q\.?|Quiz)\s*\d+[\.번\)]?|###|#|\d+(?:번\s*\.?|\.|\)))\s*|$)'
        pattern = r'\n\s*(?:[^\w\s]\s*)*((?:정답|답|해설)\s*[:：]?\s*[\s\S]*?)' + lookahead
        content = re.sub(pattern, repl_details, content, flags=re.IGNORECASE)
        return re.sub(r'\n{3,}', '\n\n', content).strip()

    m = re.search(r'<\|channel>thought\n(.*?)<channel\|>', text, re.DOTALL)
    if m: return m.group(1).strip(), clean_output(text[m.end():].strip())
    m = re.search(r'<think>(.*?)</think>', text, re.DOTALL)
    if m: return m.group(1).strip(), clean_output(re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip())
    return "", clean_output(text)

def make_pdf_bytes(markdown_text: str) -> bytes | None:
    """마크다운 텍스트를 PDF 바이트로 변환합니다. 한글 폰트 및 줄바꿈을 지원합니다."""
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.lib.utils import simpleSplit
        
        # [중요] 사고 과정(Thinking) 제거 후 본문만 추출
        _, clean_md = parse_thinking_response(markdown_text)
        
        font_paths = [
            ("/System/Library/Fonts/Supplemental/AppleGothic.ttf", None),
            ("/System/Library/Fonts/AppleSDGothicNeo.ttc", 0),
            ("/usr/share/fonts/truetype/nanum/NanumGothic.ttf", None),
            ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", None)
        ]
        
        font_name = "Helvetica"
        for path, index in font_paths:
            if os.path.exists(path):
                try:
                    if path.endswith(".ttc"):
                        pdfmetrics.registerFont(TTFont("KoreanFont", path, subfontIndex=index))
                    else:
                        pdfmetrics.registerFont(TTFont("KoreanFont", path))
                    font_name = "KoreanFont"
                    break
                except: continue

        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        margin = 50
        max_width = width - (margin * 2)
        
        text_content = re.sub(r'<[^>]+>', '', clean_md)
        text_content = text_content.replace('[ANSWER_START]', '\n--- [정답 및 해설 시작] ---\n')
        text_content = text_content.replace('[ANSWER_END]', '\n--- [정답 및 해설 끝] ---\n')
        
        curr_y = height - margin
        c.setFont(font_name, 10)
        
        for paragraph in text_content.split('\n'):
            lines = simpleSplit(paragraph, font_name, 10, max_width) if paragraph.strip() else [""]
            for line in lines:
                if curr_y < margin + 20:
                    c.showPage()
                    curr_y = height - margin
                    c.setFont(font_name, 10)
                c.drawString(margin, curr_y, line)
                curr_y -= 15
        c.save()
        return buffer.getvalue()
    except Exception as e:
        print(f"PDF Generation Error: {e}")
        return None

def extract_pdf_text(file_bytes: bytes) -> tuple[str, int]:
    """pypdf로 PDF에서 텍스트를 추출합니다."""
    if not _PYPDF_OK: return "", 0
    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        pages.append(f"[페이지 {i + 1}]\n{text.strip()}")
    return "\n\n".join(pages), len(reader.pages)

def pdf_pages_to_images(file_bytes: bytes, max_pages: int = _PDF_MAX_IMAGE_PAGES, selected_pages: set[int] | None = None) -> list[str]:
    """pymupdf(fitz)로 PDF 페이지를 base64 이미지 리스트로 변환합니다."""
    if not _FITZ_OK: return []
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    images = []
    for i in range(len(doc)):
        if selected_pages is not None and i not in selected_pages: continue
        if len(images) >= max_pages: break
        page = doc[i]
        mat = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("jpeg")
        images.append(base64.b64encode(img_bytes).decode("utf-8"))
    doc.close()
    return images

def is_pdf_text_sufficient(text: str, page_count: int) -> bool:
    if not text.strip() or page_count == 0: return False
    avg_chars = len(text.replace("\n", "").replace(" ", "")) / page_count
    return avg_chars >= _PDF_TEXT_MIN_CHARS_PER_PAGE

def _pdf_extract_content(file_bytes, page_count, page_range=""):
    selected_pages: set[int] | None = None
    if page_range and page_range.strip():
        try:
            selected_pages = set()
            for part in page_range.replace(" ", "").split(","):
                if "-" in part:
                    a, b = part.split("-")
                    selected_pages.update(range(int(a) - 1, int(b)))
                else:
                    selected_pages.add(int(part) - 1)
        except: selected_pages = None

    extracted_text, n_pages = extract_pdf_text(file_bytes)
    if selected_pages and extracted_text:
        filtered = []
        curr_page = 0
        for line in extracted_text.split("\n"):
            m = re.match(r"\[페이지 (\d+)\]", line)
            if m: curr_page = int(m.group(1)) - 1
            if curr_page in selected_pages: filtered.append(line)
        extracted_text = "\n".join(filtered)

    if is_pdf_text_sufficient(extracted_text, n_pages or 1):
        return extracted_text, [], "text"
    elif _FITZ_OK:
        images = pdf_pages_to_images(file_bytes, _PDF_MAX_IMAGE_PAGES, selected_pages)
        return "", images, "vision"
    return extracted_text, [], "text (sparse)"

def _parse_question_list(text: str) -> list[dict]:
    import json
    try:
        from json_repair import repair_json
    except ImportError:
        def repair_json(t): return t

    json_str = text.strip()
    match = re.search(r'\[\s*\{[\s\S]*\}\s*\]', text)
    if match: json_str = match.group(0)
    else:
        match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if match: json_str = match.group(1)

    try:
        repaired = repair_json(json_str)
        data = json.loads(repaired)
        if not isinstance(data, list):
            if isinstance(data, dict):
                if "questions" in data: data = data["questions"]
                elif "items" in data: data = data["items"]
                else: data = [data]
            else: return []
        refined = []
        for i, item in enumerate(data):
            if not isinstance(item, dict): continue
            num = str(item.get("번호", item.get("number", item.get("no", i + 1))))
            content = str(item.get("내용", item.get("content", item.get("text", ""))))
            if content.strip():
                refined.append({"number": num.strip(), "content": content.strip()})
        return refined
    except Exception as e:
        print(f"Error parsing question list: {e}")
        return []
