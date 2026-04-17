import os
import sys
import re
from markdown_pdf import MarkdownPdf, Section

def fallback_make_pdf(markdown_content, title):
    # 1. :::box tags -> Standard Markdown
    containers = [
        ("problem", "📝 문제"),
        ("concept", "💡 핵심 개념"),
        ("solving", "🔍 풀이 과정"),
        ("explanation", "✅ 해설 및 분석"),
    ]
    
    lines = markdown_content.splitlines()
    processed_lines = [f"# {title}\n"] # Ensure level 1 header exists
    i = 0
    while i < len(lines):
        ln = lines[i].strip()
        if ln.startswith(":::") and any(ln.lower().startswith(f":::{c[0]}") for c in containers):
            tag_name = ln.lstrip(":").strip().split()[0].lower()
            tag_title = next((c[1] for c in containers if c[0] == tag_name), "정보")
            processed_lines.append(f"\n## {tag_title}\n") # Level 2
            i += 1
            while i < len(lines) and lines[i].strip() != ":::":
                processed_lines.append(f"> {lines[i]}")
                i += 1
            processed_lines.append("\n")
        else:
            processed_lines.append(lines[i])
        i += 1
    
    text = "\n".join(processed_lines)
    
    # 2. PDF generation
    pdf = MarkdownPdf()
    pdf.add_section(Section(text, toc=False)) # Try to disable toc for the section if supported
    return pdf

files_to_convert = [
    ('/Users/leekijung/Downloads/1_5_260415_미분법_문제지_Q1 (1).md', '미분법 문제지 풀이'),
    ('/Users/leekijung/Downloads/pdf_analysis_result.md', '반복문 학습 가이드')
]

for md_path, title in files_to_convert:
    if not os.path.exists(md_path):
        print(f"File not found: {md_path}")
        continue
    
    print(f"Converting {md_path} with fallback (markdown-pdf)...")
    try:
        with open(md_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        pdf = fallback_make_pdf(content, title)
        
        pdf_path = md_path.rsplit('.', 1)[0] + '.pdf'
        pdf.save(pdf_path)
        print(f"Successfully created: {pdf_path}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error converting {md_path}: {e}")
