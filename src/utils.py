from __future__ import annotations
import streamlit as st
import os
import io
import re
import json
import base64
import unicodedata
import latex2mathml.converter
from PIL import Image

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

from src.config import MAX_IMAGE_SIZE, _PDF_TEXT_MIN_CHARS_PER_PAGE


def safe_filename(name: str) -> str:
    """파일명에서 특수문자를 제거하고 안전한 이름으로 변환합니다. (NFC 정규화 포함)"""
    # Mac/Win 등 운영체제 간 한글 자모 분리 방지를 위해 NFC 정규화
    name = unicodedata.normalize('NFC', name)
    # 공백을 언더바로 변환
    name = name.replace(" ", "_")
    # 파일명으로 부적절한 특수문자 제거 (괄호, 따옴표, 경로 구분자 등)
    name = re.sub(r'[\\/*?:"<>|()\[\]]', "", name)
    return name


def encode_image_to_base64(uploaded_file, max_size: int = MAX_IMAGE_SIZE) -> str:
    img = Image.open(uploaded_file)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    w, h = img.size
    if max(w, h) > max_size:
        ratio = max_size / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def clean_math_for_pdf(text: str) -> str:
    """PDF 출력을 위해 Markdown 내의 LaTeX 수식을 읽기 좋은 유니코드 텍스트로 변환합니다."""
    try:
        from pylatexenc.latex2text import LatexNodes2Text
        converter = LatexNodes2Text()
        
        def replace_math(match):
            math_content = match.group(1) or match.group(2)
            try:
                # LaTeX 수식을 일반 텍스트/유니코드로 변환
                converted = converter.latex_to_text(math_content)
                return converted
            except:
                return math_content

        # 블록 수식 ($$...$$) 먼저 처리
        text = re.sub(r'\$\$(.*?)\$\$', replace_math, text, flags=re.DOTALL)
        # 인라인 수식 ($...$) 처리
        text = re.sub(r'\$(.*?)\$', replace_math, text)
        return text
    except Exception:
        return text

def make_pdf_bytes(md_text: str) -> bytes:
    """latex2mathml과 WeasyPrint를 사용하여 고품질 수식이 포함된 PDF를 생성합니다."""
    try:
        import markdown
        from pygments.formatters import HtmlFormatter
        from weasyprint import HTML
        from weasyprint.text.fonts import FontConfiguration
        import latex2mathml.converter
        
        # ── 0. 생각 과정(Thinking) 제거 ──────────────────────────
        # 분석 결과에서 추론 과정을 제외하고 최종 답변만 PDF에 포함
        _, final_text = parse_thinking_response(md_text)
        
        # ── 1. 지능형 수식 수선 (Repair) ──────────────────────────
        unicode_map = {
            '∑': r'\sum ', '∏': r'\prod ', '∫': r'\int ',
            '⋯': r'\dots ', '…': r'\dots ', '′': "'",
            '−': '-', '±': r'\pm ', '×': r'\times ',
            '÷': r'\div ', '∞': r'\infty ', '⊆': r'\subseteq ',
            '≥': r'\ge ', '≤': r'\le ', '≠': r'\ne ',
            '≈': r'\approx ', '→': r'\to ', '⇒': r'\Rightarrow ',
            '⏟': r'\underbrace', 'Δ': r'\Delta ', 'δ': r'\delta '
        }
        for u_char, l_cmd in unicode_map.items():
            final_text = final_text.replace(u_char, l_cmd)

        # ── 1. 수식 추출 및 플레이스홀더 처리 ─────────────────────
        math_map = {}
        math_idx = 0

        def protect_math(text):
            nonlocal math_idx
            
            # ── 1. 명시적 수식 보호 ($$, $) ────────────────────────
            def block_repl(m):
                nonlocal math_idx
                key = f"MATHTAGBLOCK{math_idx}TAG"
                math_map[key] = (m.group(1).strip(), True)
                math_idx += 1
                return f"\n\n{key}\n\n"
            
            text = re.sub(r'\$\$(.*?)\$\$', block_repl, text, flags=re.DOTALL)

            def inline_repl(m):
                nonlocal math_idx
                key = f"MATHTAGINLINE{math_idx}TAG"
                math_map[key] = (m.group(1).strip(), False)
                math_idx += 1
                return f" {key} " 

            text = re.sub(r'\$([^\$]+?)\$', inline_repl, text)
            
            # ── 2. 줄 단위 수식 탐지 (코드 블록 내부 제외) ──────────
            lines = []
            in_code_block = False
            for line in text.split('\n'):
                stripped = line.strip()
                
                # 코드 블록 진입/탈출 감지
                if stripped.startswith("```"):
                    in_code_block = not in_code_block
                    lines.append(line)
                    continue
                
                # 코드 블록 내부라면 수식 탐지 패스
                if in_code_block:
                    lines.append(line)
                    continue

                if not any(tag in stripped for tag in math_map.keys()):
                    # 명백한 수식 기호가 포함된 경우만 수식 블록으로 취급
                    if re.search(r'^\s*ddx[\s\(]|\\Delta|\\sum|\\frac|[\d.n]+\s*[+\-*/=]|\^', stripped):
                        # 리스트 기호나 헤더 등은 제외
                        if not (stripped.startswith('#') or stripped.startswith('*') or stripped.startswith('- ') or re.match(r'^\d+\.', stripped)):
                            nonlocal math_idx
                            key = f"MATHTAGBLOCK{math_idx}TAG"
                            math_map[key] = (stripped, True)
                            math_idx += 1
                            line = f"\n\n{key}\n\n"
                lines.append(line)
            text = '\n'.join(lines)
            return text

        def process_containers(text):
            # 모든 컨테이너 태그(:::tag)를 제거하고 내용만 유지
            # 대소문자 구분 없이, 태그 앞뒤 공백 허용하도록 개선
            tags = ["problem", "concept", "solving", "explanation"]
            for tag in tags:
                pattern = rf":::\s*{tag}\s*(.*?)\s*:::"
                text = re.sub(pattern, r"\1", text, flags=re.DOTALL | re.IGNORECASE)
            return text

        protected_text = protect_math(final_text)
        processed_text = process_containers(protected_text)

        # ── 2. 마크다운 -> HTML 변환 ─────────────────────────────
        html_body = markdown.markdown(
            processed_text,
            extensions=['codehilite', 'fenced_code', 'tables']
        )
        
        # ── 3. 플레이스홀더를 SVG 이미지로 교체 ───────────────────
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from io import BytesIO
        import base64
        import matplotlib.path as mpath
        import matplotlib.patches as mpatches

        def latex_to_svg_img(latex, is_block):
            try:
                plt.rc('text', usetex=False)
                plt.rcParams.update({
                    "font.family": "AppleGothic",
                    "mathtext.fontset": "custom",
                    "mathtext.rm": "AppleGothic",
                })
                def get_balanced(s, start_idx):
                    """중괄호 쌍이 맞는 구간을 추출합니다."""
                    stack = 0
                    found_start = False
                    first_pos = -1
                    for i in range(start_idx, len(s)):
                        if s[i] == '{':
                            if not found_start:
                                found_start = True
                                first_pos = i
                            stack += 1
                        elif s[i] == '}':
                            stack -= 1
                            if found_start and stack == 0:
                                return s[first_pos+1:i], i + 1
                    return None, -1

                # \underbrace 직접 파싱
                ub_pos = latex.find(r'\underbrace')
                match = False
                if ub_pos != -1:
                    prefix = latex[:ub_pos]
                    content, next_idx = get_balanced(latex, ub_pos + 11)
                    if content is not None:
                        sub_pos = latex.find('_', next_idx)
                        if sub_pos != -1:
                            label, final_idx = get_balanced(latex, sub_pos)
                            if label is not None:
                                suffix = latex[final_idx:]
                                p, c, l, s = prefix, content, label, suffix
                                match = True 

                if match:
                    # 1. 길이 측정
                    fig_test = plt.figure()
                    res = fig_test.canvas.get_renderer()
                    t_p = fig_test.text(0,0, fr"${p.strip()} \ $", fontsize=12)
                    t_c = fig_test.text(0,0, fr"${c.strip()}$", fontsize=12)
                    t_s = fig_test.text(0,0, fr"$\ {s.strip()}$", fontsize=12)
                    w_p = t_p.get_window_extent(res).width
                    w_c = t_c.get_window_extent(res).width
                    w_s = t_s.get_window_extent(res).width
                    plt.close(fig_test)
                    
                    dpi = 100
                    total_w_px = w_p + w_c + w_s + 20
                    fig = plt.figure(figsize=(total_w_px/dpi, 0.8), dpi=dpi)
                    ax = fig.add_axes([0, 0, 1, 1])
                    ax.set_axis_off()
                    ax.set_xlim(0, total_w_px)
                    ax.set_ylim(0, 80)
                    
                    y_baseline = 45 
                    ax.text(10, y_baseline, fr"${p.strip()} \ $", fontsize=12, va='baseline')
                    ax.text(10 + w_p, y_baseline, fr"${c.strip()}$", fontsize=12, va='baseline')
                    ax.text(10 + w_p + w_c, y_baseline, fr"$\ {s.strip()}$", fontsize=12, va='baseline')
                    
                    # 중괄호 좌표 및 디자인
                    x0, x1 = 10 + w_p + 2, 10 + w_p + w_c - 2
                    xm = (x0 + x1) / 2
                    
                    # 뾰족한 중앙 팁을 가진 TeX 스타일 중괄호 디자인
                    y_top = 38      # 상단 높이
                    y_bottom = 18   # 최하단 팁 높이 (더 깊고 뾰족하게)
                    y_mid = 30      # 중간 높이
                    cp_w = min(12, (x1 - x0) / 4)
                    
                    verts = [
                        (x0, y_top),                                  # 1. 시작 (왼쪽 위)
                        (x0, y_mid), (x0 + cp_w, y_mid),              # 2. 부드러운 어깨 (왼쪽)
                        (xm - cp_w/2, y_mid),                         # 3. 수평 본체 (왼쪽)
                        (xm - cp_w/4, y_mid), (xm, y_bottom),         # 4. 날카로운 팁 인 (왼쪽 -> 팁)
                        (xm + cp_w/4, y_mid), (xm + cp_w/2, y_mid),   # 5. 날카로운 팁 아웃 (팁 -> 오른쪽)
                        (x1 - cp_w, y_mid),                           # 6. 수평 본체 (오른쪽)
                        (x1, y_mid), (x1, y_top)                      # 7. 부드러운 어깨 (오른쪽)
                    ]
                    codes = [
                        mpath.Path.MOVETO,
                        mpath.Path.CURVE3, mpath.Path.CURVE3,         # 어깨 (Curve)
                        mpath.Path.LINETO,                            # 본체 (Line)
                        mpath.Path.CURVE3, mpath.Path.CURVE3,         # 뾰족한 팁 왼쪽 (Curve)
                        mpath.Path.CURVE3, mpath.Path.CURVE3,         # 뾰족한 팁 오른쪽 (Curve)
                        mpath.Path.LINETO,                            # 본체 (Line)
                        mpath.Path.CURVE3, mpath.Path.CURVE3,         # 어깨 (Curve)
                    ]
                    ax.add_patch(mpatches.PathPatch(mpath.Path(verts, codes), fill=False, color='black', lw=1.2))
                    
                    # 라벨 배치
                    clean_label = l.strip().replace(r'\text', '').replace('{', '').replace('}', '')
                    ax.text(xm, 12, fr"$\text{{ {clean_label} }}$", fontsize=10, ha='center', va='top')
                    
                    buf = BytesIO()
                    fig.savefig(buf, format='svg', transparent=True, bbox_inches=None)
                    plt.close(fig)
                    b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
                    style = f"display: {'block' if is_block else 'inline-block'}; margin: {'1em auto' if is_block else '0'}; width: {total_w_px * 0.9}px; height: auto;"
                    return f'<img src="data:image/svg+xml;base64,{b64}" style="{style}">'
                else:
                    # 일반 수식
                    mpl_latex = latex.replace("'", r"^{\prime}")
                    if r"\text" not in mpl_latex: mpl_latex = re.sub(r'([가-힣\s]+)', r'\\text{\1}', mpl_latex)
                    if not mpl_latex.startswith('$'): mpl_latex = f"${mpl_latex}$"
                    
                    fig = plt.figure(figsize=(0.1, 0.1), dpi=200)
                    t = fig.text(0, 0, mpl_latex, fontsize=12)
                    buf = BytesIO()
                    fig.savefig(buf, format='svg', transparent=True, bbox_inches='tight', pad_inches=0.03)
                    plt.close(fig)
                    b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
                    style = "display: block; margin: 1em auto; max-width: 90%; height: auto;" if is_block else "display: inline-block; vertical-align: middle; height: 1.1em;"
                    return f'<img src="data:image/svg+xml;base64,{b64}" style="{style}">'
            except Exception as e:
                try:
                    import latex2mathml.converter
                    mathml = latex2mathml.converter.convert(latex.replace("'", r"^{\prime}"))
                    return f'<div class="math-display">{mathml}</div>' if is_block else f'<span class="math-inline">{mathml}</span>'
                except Exception as e2:
                    return f'<span>${latex}$</span>'
        for key, (latex, is_block) in math_map.items():
            replacement = latex_to_svg_img(latex, is_block)
            html_body = html_body.replace(key, replacement)


        
        # ── 4. 최종 HTML 패키징 ──────────────────────────────────
        # Pygments 신택스 하이라이팅 CSS 생성
        pygments_css = HtmlFormatter(style='monokai').get_style_defs('.codehilite')
        
        full_html = f"""
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                /* Pygments Syntax Highlighting */
                {pygments_css}
                
                @page {{ margin: 2.5cm; }}
                body {{ 
                    font-family: 'NanumGothic', 'NanumBarunGothic', 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif;
                    line-height: 1.7;
                    color: #333;
                    font-size: 11pt;
                }}
                h1, h2, h3 {{ color: #1a202c; margin-top: 1.5em; border-bottom: 1px solid #edf2f7; padding-bottom: 0.3em; }}
                
                .math-display {{ 
                    text-align: center; 
                    margin: 1.5em 0; 
                    display: block;
                }}
                .math-inline {{ 
                    display: inline-block;
                    vertical-align: middle;
                    margin: 0 0.1em;
                }}
                math {{ font-size: 1.2em; }}
                
                code {{ 
                    background: #f1f5f9; 
                    padding: 2px 5px; 
                    border-radius: 4px; 
                    font-family: "NanumGothicCoding", "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
                    font-size: 0.9em;
                    color: #e11d48;
                }}
                pre {{ 
                    background: #1e293b; 
                    color: #f8fafc;
                    padding: 1.2rem; 
                    border-radius: 10px; 
                    overflow-x: auto; 
                    font-family: "NanumGothicCoding", "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
                    font-size: 0.82em;
                    line-height: 1.5;
                    margin: 1.2rem 0;
                    border: 1px solid #0f172a;
                    white-space: pre-wrap;
                    word-wrap: break-word;
                }}
                pre code {{ 
                    background: transparent; 
                    padding: 0; 
                    color: inherit; 
                    font-size: inherit; 
                }}
                blockquote {{ border-left: 4px solid #3182ce; padding-left: 1rem; color: #2d3748; margin: 1.5rem 0; background: #ebf8ff; padding: 1rem; border-radius: 0 8px 8px 0; }}
                table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; border: 1px solid #e2e8f0; }}
                th, td {{ border: 1px solid #e2e8f0; padding: 10px; }}
                th {{ background: #edf2f7; font-weight: bold; }}
            </style>
        </head>
        <body>
            {html_body}
        </body>
        </html>
        """
        
        # ── 5. PDF 생성 ───────────────────────────────────────────
        font_config = FontConfiguration()
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
    m = re.search(r'<\|channel>thought\n(.*?)<channel\|>', text, re.DOTALL)
    if m:
        return m.group(1).strip(), text[m.end():].strip()

    m = re.search(r'<think>(.*?)</think>', text, re.DOTALL)
    if m:
        thinking = m.group(1).strip()
        final = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
        return thinking, final

    return "", text


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
    avg_chars = len(text.replace("\n", "").replace(" ", "")) / page_count
    return avg_chars >= _PDF_TEXT_MIN_CHARS_PER_PAGE


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
        max_pg = 999 
        images = pdf_pages_to_images(file_bytes, max_pg, selected_pages)
        if images:
            return "", images, "vision"

    return extracted_text, None, "text (sparse)"


def _parse_question_list(raw: str) -> list[dict]:
    json_match = re.search(r"\[[\s\S]*\]", raw)
    if json_match:
        try:
            data = json.loads(json_match.group())
            return [
                {"번호": str(q.get("번호", i + 1)), "내용": q.get("내용", "").strip()}
                for i, q in enumerate(data)
                if q.get("내용", "").strip()
            ]
        except json.JSONDecodeError:
            pass

    questions = []
    matches = re.findall(r'"번호"\s*:\s*"([^"]+)"\s*,\s*"내용"\s*:\s*"(.*?)"\s*\}', raw, re.DOTALL)
    if matches:
        for num, content in matches:
            questions.append({"번호": num, "내용": content.strip().replace('\\"', '"').replace('\\\\', '\\')})
        if questions:
            return questions

    pattern = re.split(r"(?m)^(?:문제\s*)?(\d+)[.)]\s+", raw)
    if len(pattern) > 2:
        for i in range(1, len(pattern) - 1, 2):
            num = pattern[i]
            content = pattern[i + 1].strip()
            if content:
                questions.append({"번호": num, "내용": content[:500]})
    return questions
