from __future__ import annotations
import re
import io
import base64
import os

# 순수 Python 표준 라이브러리만 사용하는 함수들은 최상위에 배치 (에러 방지)
def encode_image_to_base64(image_file):
    return base64.b64encode(image_file.read()).decode("utf-8")

def safe_filename(filename: str) -> str:
    clean = re.sub(r'[^\w\s\-\.]', '', filename)
    clean = clean.replace(' ', '_')
    return clean if clean.strip() else "downloaded_file"

def parse_quiz_markdown(text: str) -> list[dict]:
    """줄 단위 상태 머신 방식으로 퀴즈 문항을 정교하게 추출합니다."""
    lines = text.split('\n')
    questions, current_q = [], None
    q_start_re = re.compile(r'^\s*(?:[^\w\s]\s*)*(?:(?:문항|질문|문제|Q)\s*(\d+)[\.번\)]?\s*(.*)|(\d+)(?:번\s*\.?|\.)\s+(.*))', re.IGNORECASE)
    opt_start_re = re.compile(r'^\s*(?:[\-\*]\s+)?([①-⑩]|[1-5][\)\.]|(?:\([1-5]\)))\s*(.*)')
    ans_re, exp_re = re.compile(r'(?:정답|답)\s*[:：]?\s*(.*)', re.IGNORECASE), re.compile(r'(?:해설)\s*[:：]?\s*(.*)', re.IGNORECASE)
    quiz_started = False
    
    for line in lines:
        raw_line = line
        line = line.strip()
        if not line: continue
        
        # HTML 태그 줄 건너뛰기 (details, summary, div 등)
        if line.startswith('<') and line.endswith('>'):
            continue

        q_match = q_start_re.match(line)
        if q_match:
            num = q_match.group(1) or q_match.group(3)
            cont = q_match.group(2) or q_match.group(4) or ""
            cont = cont.strip("*#- ")
            
            quiz_started = True 
            if current_q: questions.append(current_q)
            current_q = {"number": num, "content": cont, "options": [], "answer": "", "explanation": "", "raw": raw_line}
            continue
        if not quiz_started or not current_q: continue
        opt_match = opt_start_re.match(line)
        if opt_match:
            if opt_match.group(2).strip():
                current_q["options"].append(f"{opt_match.group(1)} {opt_match.group(2).strip()}")
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
            current_q["content"] += "\n" + line
        elif current_q["explanation"]:
            current_q["explanation"] += "\n" + line
        current_q["raw"] += "\n" + raw_line
    if current_q: questions.append(current_q)
    return questions

def parse_thinking_response(text: str) -> tuple[str, str]:
    def clean_output(content: str) -> str:
        # 1. 수식 내 $ 중복 제거 및 백틱 오류 등 기본 전처리
        def repl_block(match): return match.group(0).replace("$", "")
        content = re.sub(r"```[\s\S]*?```", repl_block, content)
        
        # 모델이 수식을 백틱으로 감싸는 경우(예: `$\sqrt{2}$`)를 방지하여 Streamlit 수학 수식 렌더링 정상화
        content = re.sub(r'`(\$[^`\$]+\$)`', r'\1', content)
        
        content = re.sub(r"<br\s*/?>", "\n", content, flags=re.IGNORECASE)
        content = content.replace("\\*\\*", "**").replace("\\*", "*")
        
        # 2. n지선다 줄바꿈 처리 - 문장 중간의 기호들 앞에 줄바꿈 삽입
        # 단, 수식 내부의 1), (1) 등으로 인해 수식이 깨지는 것을 방지하기 위해 임시 치환
        placeholders = {}
        def repl_math(match):
            key = f"__MATH_{len(placeholders)}__"
            placeholders[key] = match.group(0)
            return key
            
        content = re.sub(r'\$\$.*?\$\$', repl_math, content, flags=re.DOTALL)
        content = re.sub(r'\$[^\$\n]*?\$', repl_math, content)
        
        # 문장 중간에 옵션이 연달아 나오는 경우 분리 (단, 줄 시작 마커 -, *, : 등 뒤에서는 분리하지 않음)
        content = re.sub(r'([^\n\-\*:#])\s+([①-⑩]|\([1-5]\)|[1-5][\)\.])', r'\1\n\2', content)
        
        for k, v in placeholders.items():
            content = content.replace(k, v)
        
        # 3. 정답 및 해설 섹션을 <details> 태그로 감싸기
        def repl_details(match):
            inner = match.group(1).strip()
            # 내부 마크다운이 잘 렌더링되도록 처리
            return f'\n\n<details>\n<summary>💡 정답 및 해설 확인하기</summary>\n<div markdown="1">\n\n{inner}\n\n</div>\n</details>\n\n'
        
        # "정답/답/해설"로 시작하는 블록을 찾음 (다음 문항 전이나 텍스트 끝까지)
        pattern = r'\n\s*((?:정답|답|해설)\s*[:：]?\s*[\s\S]*?)(?=\n\s*(?:문항|###|#|\d+[\.번\)])|$)'
        content = re.sub(pattern, repl_details, content)
        
        # 불필요한 공백/줄바꿈 정리
        return re.sub(r'\n{3,}', '\n\n', content).strip()

    m = re.search(r'<\|channel>thought\n(.*?)<channel\|>', text, re.DOTALL)
    if m: return m.group(1).strip(), clean_output(text[m.end():].strip())
    m = re.search(r'<think>(.*?)</think>', text, re.DOTALL)
    if m: return m.group(1).strip(), clean_output(re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip())
    return "", clean_output(text)

# 시스템 의존성이 있는 라이브러리를 사용하는 함수들은 함수 내에서 import (Lazy Import)
def make_pdf_bytes(markdown_text: str) -> bytes:
    try:
        import markdown
        from weasyprint import HTML
        try: from weasyprint.fonts import FontConfiguration
        except ImportError: FontConfiguration = None
        
        html_body = markdown.markdown(markdown_text, extensions=['tables', 'fenced_code'])
        full_html = f"<html><head><meta charset='utf-8'></head><body>{html_body}</body></html>"
        font_config = FontConfiguration() if FontConfiguration else None
        return HTML(string=full_html).write_pdf(font_config=font_config)
    except Exception: return b""

def _pdf_extract_content(file_bytes: bytes, page_count: int, page_range: str) -> tuple[str, list[str] | None, str]:
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        extracted_text = "\n\n".join([p.extract_text() for p in reader.pages if p.extract_text()])
        return extracted_text, None, "text"
    except Exception: return "", None, "text"

def _parse_question_list(text: str) -> list[dict]:
    matches = re.findall(r'(\d+)[\.번]\s*(.*?)(?=\n\s*\d+[\.번]|$)', text, re.DOTALL)
    return [{"번호": num, "내용": content.strip()} for num, content in matches]
