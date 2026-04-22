from __future__ import annotations
import re
import io
import json
import os
import base64
import functools

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

# 수식 및 PDF 전용 라이브러리
import markdown
import requests
import urllib.parse
try:
    from weasyprint import HTML, CSS
    from weasyprint.text.fonts import FontConfiguration
    _WEASYPRINT_OK = True
except ImportError:
    _WEASYPRINT_OK = False

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    _MATPLOTLIB_OK = True
except ImportError:
    _MATPLOTLIB_OK = False

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
    # 문제 시작: "문항 1", "Q1", "1." 등
    q_start_re = re.compile(r'^\s*(?:[^\w\s]\s*)*(?:(?:문항|질문|문제|Q)\s*(\d+)[\.번\)]?|(\d+)(?:번\s*\.?|\.|\)))\s*(.*)', re.IGNORECASE)
    # 보기 시작: "1)", "(1)", "①", "1." 등
    opt_start_re = re.compile(r'^\s*(?:[\-\*]\s+)?([①-⑩]|[1-5][\)\.]|(?:\([1-5]\))|[1-5](?=\s*[\(\[A-E가-힣]))\s*(.*)')
    # 정답 키워드: "정답: 2", "답: 2" 등
    ans_re = re.compile(r'(?:정답|답)\s*(?:\*\*|\*)?[:：]?\s*(?:\*\*|\*)?\s*([1-5①-⑤]|[A-Ea-e]+)', re.IGNORECASE)
    
    in_answer_block = False
    
    for line in lines:
        raw_line = line
        line = line.strip()
        if not line: continue
        
        # 특수 태그 처리
        if "[ANSWER_START]" in line:
            in_answer_block = True
            continue
        if "[ANSWER_END]" in line:
            in_answer_block = False
            continue
            
        # 1. 새로운 문제 시작 감지
        q_match = q_start_re.match(line)
        # 만약 명확한 문항 접두어(문항, 문제, Q)가 있으면 강제로 새로운 문제로 인식
        is_explicit_q = bool(re.search(r'문항|문제|질문|Q', line, re.IGNORECASE))
        
        if q_match:
            num = q_match.group(1) or q_match.group(2)
            content = q_match.group(3) or ""
            
            # 현재 상태가 해설 블록이거나 서브 아이템인지 확인
            is_sub_item = False
            if current_q:
                # 💡 [번호 역행 방지 로직 추가]
                try:
                    curr_num_val = int(re.sub(r'\D', '', str(current_q["number"])))
                    new_num_val = int(re.sub(r'\D', '', str(num)))
                    
                    # 현재 번호보다 작거나 같은 번호가 나오면 '새 문항' 키워드가 없는 한 무시
                    if new_num_val <= curr_num_val and not is_explicit_q:
                        is_sub_item = True
                except: pass

                # 해설 블록 내부이거나 이미 해설이 시작된 경우, ### 가 아니면 문제로 인정 안 함
                if not is_sub_item and (in_answer_block or current_q["explanation"]):
                    if not is_explicit_q and not line.startswith("###"):
                        is_sub_item = True

            # 해설 블록 내부여도 명시적인 새로운 '문항' 키워드가 나오면 해설 블록 강제 종료
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

            # 이전 문항 저장 및 새 문항 시작
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
            
        # 2. 정답 섹션 내부 또는 정답/해설 키워드 감지
        if in_answer_block:
            a_match = ans_re.search(line)
            if a_match and not current_q["answer"]:
                current_q["answer"] = a_match.group(1).strip()
            
            # 정답/해설 섹션 내부에서는 새로운 보기가 나타나지 않는다고 가정
            clean_line = re.sub(r'</?(?:b|style|details|summary|div)[^>]*>|\[ANSWER_START\]|\[ANSWER_END\]', '', raw_line, flags=re.IGNORECASE)
            if clean_line.strip():
                current_q["explanation"] += (("\n" if current_q["explanation"] else "") + clean_line.strip())
            continue

        # 3. 보기(Option) 감지
        opt_match = opt_start_re.match(line)
        # 이미 정답이 나온 뒤라면 더 이상 보기를 추가하지 않음 (본문/해설로 처리)
        if opt_match and not current_q["answer"] and not current_q["explanation"]:
            marker = opt_match.group(1)
            option_text = f"{marker} {opt_match.group(2).strip()}"
            
            # 원문자 우선 정책
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
            # 문제 본문 연장
            a_match = ans_re.search(line)
            if a_match:
                current_q["answer"] = a_match.group(1).strip()
            # "해설" 단어 포함 시 설명 모드로 전환 시도 (태그가 누락된 경우 대비)
            if "해설" in line or "이유" in line:
                current_q["explanation"] += (("\n" if current_q["explanation"] else "") + line)
            elif current_q["explanation"]:
                current_q["explanation"] += "\n" + line
            elif not current_q["options"]:
                current_q["content"] += "\n" + line
            else:
                # 선택지 이후에 나오는 텍스트는 보통 설명의 시작임
def parse_quiz_json(text: str) -> dict:
    """텍스트 내의 JSON 블록을 찾아 추출하여 지문(passage)과 문항 리스트(questions)를 반환합니다."""
    # 0. 전처리
    preamble_match = re.search(r'(\[|\{|\s*```json)', text)
    if preamble_match and preamble_match.start() > 0:
        text = text[preamble_match.start():]

    text = re.sub(r'<\|channel>.*?<channel\|>', '', text, flags=re.DOTALL)
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    text = re.sub(r'</?(?:details|summary|b|style|div|span)[^>]*>', '', text, flags=re.IGNORECASE)
    
    result = {"passage": "", "questions": []}
    
    try:
        data = None
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if json_match:
            data = json.loads(json_match.group(1))
        else:
            json_match = re.search(r'(\[[\s\S]*\]|\{[\s\S]*\})', text)
            if json_match:
                data = json.loads(json_match.group(0))
            else:
                result["questions"] = parse_quiz_markdown(text)
                return result
        
        # 데이터 구조 정규화
        if isinstance(data, list):
            result["questions"] = data
        elif isinstance(data, dict):
            if "questions" in data:
                result["questions"] = data["questions"]
                result["passage"] = data.get("passage", "")
            elif "problems" in data:
                result["questions"] = data["problems"]
                result["passage"] = data.get("passage", "")
            elif "quiz" in data:
                result["questions"] = data["quiz"]
            else:
                result["questions"] = [data]
        
        # 문항 데이터 보정
        for q in result["questions"]:
            q.setdefault("number", "1")
            q.setdefault("type", "multiple_choice" if q.get("options") else "short_answer")
            q["content"] = clean_text_symbols(str(q.get("content", "")))
            q["answer"] = clean_text_symbols(str(q.get("answer", "")))
            q["explanation"] = clean_text_symbols(str(q.get("explanation", "")))
            if q.get("options"):
                q["options"] = [clean_text_symbols(str(opt)) for opt in q["options"]]
            
            if q["type"] == "multiple_choice" and not q.get("options"):
                found_opts = re.findall(r'(\d+[\)\.]|[①-⑩])\s*([^\d①-⑩\n]+)', q["content"])
                if found_opts:
                    q["options"] = [f"{m}{t.strip()}" for m, t in found_opts]
                    for m, t in found_opts:
                        q["content"] = q["content"].replace(f"{m}{t}", "").strip()

            if q["answer"]:
                q["answer"] = q["answer"].replace('①','1').replace('②','2').replace('③','3').replace('④','4').replace('⑤','5')
        
        return result
    except Exception as e:
        print(f"JSON Parsing Error: {e}")
        result["questions"] = parse_quiz_markdown(text)
        return result

def questions_to_markdown(quiz_data: dict or list) -> str:
    """JSON 데이터를 사람이 읽기 좋은 예쁜 마크다운 문서로 변환합니다."""
    if isinstance(quiz_data, list):
        passage = ""
        questions = quiz_data
    else:
        passage = quiz_data.get("passage", "")
        questions = quiz_data.get("questions", [])

    md = ""
    if passage:
        md += "## 📖 다음 지문을 읽고 물음에 답하시오.\n\n"
        md += f"> {passage}\n\n"
        md += "---\n\n"

    for q in questions:
        md += f"### 문항 {q.get('number', '')}\n\n"
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
        # JSON 모드일 때는 최소한의 정지만 수행
        if "```json" in content or content.strip().startswith("["):
            return content.strip()
            
        # 1. 수식 내 $ 중복 제거 및 백틱 오류 등 기본 전처리
        def repl_block(match): return match.group(0).replace("$", "")
        content = re.sub(r"```[\s\S]*?```", repl_block, content)
        
        # 공통 기호 정제 로직 사용
        content = clean_text_symbols(content)
        
        content = re.sub(r"<br\s*/?>", "\n", content, flags=re.IGNORECASE)
        
        # 2. n지선다 줄바꿈 처리
        placeholders = {}
        def repl_math(match):
            key = f"__MATH_{len(placeholders)}__"
            placeholders[key] = match.group(0)
            return key
        content = re.sub(r'\$\$.*?\$\$', repl_math, content, flags=re.DOTALL)
        content = re.sub(r'\$[^\$\n]*?\$', repl_math, content)
        
        #Aggressive splitting for merged options like 1 (A)... 2 (B)...
        content = re.sub(r'([^\n\-\*:#])\s+([①-⑩]|\([1-5]\)|[1-5][\)\.]|[1-5]\s*\(?[A-E가-힣]\)?)', r'\1\n\2', content)
        content = re.sub(r'(문항|문제|질문|Q)\n\s*(\d+)', r'\1 \2', content)
        
        for k, v in placeholders.items():
            content = content.replace(k, v)
        
        # 3. 정답 및 해설 섹션 처리
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

@functools.lru_cache(maxsize=256)
def latex_to_svg(latex_str: str) -> str | None:
    """온라인 API(CodeCogs)를 사용하여 LaTeX 수식을 고품질 SVG로 변환합니다.
    캐싱을 적용하여 동일한 수식의 중복 처리를 방지합니다.
    """
    clean_latex = latex_str.strip()
    if clean_latex.startswith('$') and clean_latex.endswith('$'):
        clean_latex = clean_latex[1:-1]
    
    try:
        # 1. CodeCogs API 사용 (가장 안정적이고 고품질)
        encoded_latex = urllib.parse.quote(clean_latex)
        url = f"https://latex.codecogs.com/svg.latex?{encoded_latex}"
        
        response = requests.get(url, timeout=1.5)
        if response.status_code == 200 and b'svg' in response.content.lower():
            b64_svg = base64.b64encode(response.content).decode('utf-8')
            return f"data:image/svg+xml;base64,{b64_svg}"
    except Exception as e:
        print(f"Online Math API error: {e}")
    
    # 2. 오프라인이거나 API 실패 시 Matplotlib 로컬 폴백
    if _MATPLOTLIB_OK:
        try:
            fig = plt.figure(figsize=(0.1, 0.1), dpi=100)
            plt.text(0, 0, f"${clean_latex}$", fontsize=14)
            plt.axis('off')
            
            buf = io.BytesIO()
            plt.savefig(buf, format='svg', bbox_inches='tight', pad_inches=0.02, transparent=True)
            plt.close(fig)
            return f"data:image/svg+xml;base64,{base64.b64encode(buf.getvalue()).decode('utf-8')}"
        except Exception as me:
            print(f"Matplotlib fallback error: {me}")
    
    return None

def make_pdf_bytes(markdown_text: str) -> bytes | None:
    """Markdown을 HTML로 변환 후 수식은 SVG 이미지로 대체하여 고품질 PDF를 생성합니다."""
    if not _WEASYPRINT_OK:
        print("Error: WeasyPrint is not installed or failed to import.")
        return None

    try:
        # 1. 씽킹 블록 제거
        _, clean_md = parse_thinking_response(markdown_text)
        
        # 2. LaTeX 수식 -> SVG 이미지 (플레이스홀더 전략)
        math_placeholders = {}
        
        def repl_math(match, is_block=False):
            latex = match.group(1).strip()
            placeholder = f"@@MATH_SVG_{len(math_placeholders)}@@"
            svg_uri = latex_to_svg(latex)
            
            if svg_uri:
                if is_block:
                    img_html = f'<div style="text-align:center; margin: 1.5em 0;"><img src="{svg_uri}" style="max-height: 4.5em;" /></div>'
                else:
                    img_html = f'<img src="{svg_uri}" style="vertical-align: middle; max-height: 1.4em; margin: 0 0.1em;" />'
                math_placeholders[placeholder] = img_html
            else:
                math_placeholders[placeholder] = match.group(0)
            return placeholder

        # 블록 수식 처리 ($$ ... $$)
        clean_md = re.sub(r'\$\$(.*?)\$\$', lambda m: repl_math(m, True), clean_md, flags=re.DOTALL)
        # 인라인 수식 처리 ($ ... $)
        clean_md = re.sub(r'\$(.*?)\$', lambda m: repl_math(m, False), clean_md)
        
        # 3. Markdown -> HTML 변환
        html_body = markdown.markdown(clean_md, extensions=['extra', 'codehilite', 'tables'])
        
        # 4. 플레이스홀더를 실제 SVG 이미지 태그로 복구
        for ph, img_tag in math_placeholders.items():
            html_body = html_body.replace(ph, img_tag)
        
        # [ANSWER_START] 등을 스타일링 가능한 div로 치환
        html_body = html_body.replace('[ANSWER_START]', '<div class="answer-section">')
        html_body = html_body.replace('[ANSWER_END]', '</div>')
        
        # 5. PDF용 CSS 설정 (폰트 및 레이아웃)
        font_style = """
        @page {
            size: A4;
            margin: 2cm;
        }
        body {
            font-family: 'Apple SD Gothic Neo', 'NanumGothic', 'Malgun Gothic', sans-serif;
            font-size: 11pt;
            line-height: 1.7;
            word-break: break-all;
            color: #333;
        }
        h1, h2, h3, h4 { color: #2c3e50; border-bottom: 2px solid #eee; padding-bottom: 0.3em; margin-top: 1.5em; }
        code { background-color: #f8f9fa; padding: 2px 4px; border-radius: 4px; font-family: monospace; font-size: 90%; }
        pre { background-color: #f8f9fa; padding: 1.2em; border-radius: 8px; border: 1px solid #e9ecef; white-space: pre-wrap; font-size: 90%; }
        blockquote { border-left: 4px solid #dee2e6; padding-left: 1em; color: #6c757d; margin: 1em 0; background: #fdfdfd; padding: 1em; }
        table { border-collapse: collapse; width: 100%; margin: 1.5em 0; }
        th, td { border: 1px solid #dee2e6; padding: 10px; text-align: left; }
        th { background-color: #f8f9fa; font-weight: bold; }
        .answer-section { 
            background-color: #fdfdfe; 
            border: 2px dashed #e9ecef; 
            padding: 1.5em; 
            margin: 2em 0; 
            border-radius: 12px;
            box-shadow: inset 0 0 10px rgba(0,0,0,0.02);
        }
        .answer-section h3 { border-bottom: none; margin-top: 0; }
        """
        
        full_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>{font_style}</style>
        </head>
        <body>
            {html_body}
        </body>
        </html>
        """
        
        font_config = FontConfiguration()
        buffer = io.BytesIO()
        HTML(string=full_html).write_pdf(buffer, font_config=font_config)
        
        return buffer.getvalue()
    except Exception as e:
        print(f"Critical PDF Generation Error: {e}")
        import traceback
        traceback.print_exc()
        return None

def extract_pdf_text(file_bytes: bytes) -> tuple[str, int]:
    """pypdf로 PDF에서 텍스트를 추출합니다."""
    if not _PYPDF_OK:
        return "", 0
    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        pages.append(f"[페이지 {i + 1}]\n{text.strip()}")
    return "\n\n".join(pages), len(reader.pages)

def pdf_pages_to_images(file_bytes: bytes, max_pages: int = _PDF_MAX_IMAGE_PAGES, selected_pages: set[int] | None = None) -> list[str]:
    """pymupdf(fitz)로 PDF 페이지를 base64 이미지 리스트로 변환합니다."""
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
    """텍스트 품질이 충분한지 판별합니다."""
    if not text.strip() or page_count == 0:
        return False
    avg_chars = len(text.replace("\n", "").replace(" ", "")) / page_count
    return avg_chars >= _PDF_TEXT_MIN_CHARS_PER_PAGE

def _pdf_extract_content(file_bytes, page_count, page_range=""):
    """
    PDF에서 텍스트 또는 이미지를 추출합니다.
    Returns: (content_text, images_b64_list, extraction_method)
    """
    # 페이지 범위 파싱
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
    
    # 범위 필터링
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
    """AI가 반환한 문제 목록(JSON 형태)을 파싱하여 표준화된 리스트로 반환합니다."""
    import json
    try:
        from json_repair import repair_json
    except ImportError:
        def repair_json(t): return t

    # 1. JSON 블록 추출 시도
    json_str = text.strip()
    # [ ] 형태의 배열 탐색
    match = re.search(r'\[\s*\{[\s\S]*\}\s*\]', text)
    if match:
        json_str = match.group(0)
    else:
        # ```json ... ``` 형태 탐색
        match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if match:
            json_str = match.group(1)

    try:
        # JSON 복구 및 파싱
        repaired = repair_json(json_str)
        data = json.loads(repaired)

        if not isinstance(data, list):
            if isinstance(data, dict):
                if "questions" in data: data = data["questions"]
                elif "items" in data: data = data["items"]
                else: data = [data]
            else:
                return []

        # 키값 표준화 및 데이터 정제
        refined = []
        for i, item in enumerate(data):
            if not isinstance(item, dict): continue
            
            # 다양한 언어/형태의 키값 지원
            num = str(item.get("번호", item.get("number", item.get("no", i + 1))))
            content = str(item.get("내용", item.get("content", item.get("text", ""))))
            
            if content.strip():
                refined.append({
                    "number": num.strip(),
                    "content": content.strip()
                })
        return refined
    except Exception as e:
        print(f"Error parsing question list: {e}")
        return []

generate_pdf_bytes = make_pdf_bytes
