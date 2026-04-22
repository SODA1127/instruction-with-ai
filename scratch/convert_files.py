import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from src.app_utils import make_pdf_bytes
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)

files_to_convert = [
    '/Users/leekijung/Downloads/1_5_260415_미분법_문제지_Q1 (1).md',
    '/Users/leekijung/Downloads/pdf_analysis_result.md'
]

for md_path in files_to_convert:
    if not os.path.exists(md_path):
        print(f"File not found: {md_path}")
        continue
    
    print(f"Converting {md_path}...")
    try:
        with open(md_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        pdf_bytes = make_pdf_bytes(content)
        
        pdf_path = md_path.rsplit('.', 1)[0] + '.pdf'
        with open(pdf_path, 'wb') as f:
            f.write(pdf_bytes)
        print(f"Successfully created: {pdf_path}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error converting {md_path}: {e}")
