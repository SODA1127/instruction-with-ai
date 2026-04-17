import fitz  # PyMuPDF
import os

pdf_files = [
    '/Users/leekijung/Downloads/1_5_260415_미분법_문제지_Q1 (1).pdf',
    '/Users/leekijung/Downloads/pdf_analysis_result.pdf'
]

output_dir = '/Users/leekijung/.gemini/antigravity/brain/517be25a-5a32-4f57-bf0b-f9c3855a9570/'
os.makedirs(output_dir, exist_ok=True)

previews = []

for pdf_path in pdf_files:
    if not os.path.exists(pdf_path):
        continue
    
    doc = fitz.open(pdf_path)
    base_name = os.path.basename(pdf_path).rsplit('.', 1)[0]
    
    # Generate preview for first 2 pages if they exist
    for i in range(min(2, len(doc))):
        page = doc.load_page(i)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x scale for quality
        img_name = f"preview_{base_name}_p{i+1}.png"
        img_path = os.path.join(output_dir, img_name)
        pix.save(img_path)
        previews.append(img_path)
    doc.close()

print(f"Generated {len(previews)} previews.")
for p in previews:
    print(p)
