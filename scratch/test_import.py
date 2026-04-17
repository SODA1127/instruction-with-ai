from src.config import get_max_pdf_pages, LOCAL_PDF_MAX_PAGES, CLOUD_PDF_MAX_PAGES
print(f"Success: {get_max_pdf_pages('OpenAI')}, {LOCAL_PDF_MAX_PAGES}, {CLOUD_PDF_MAX_PAGES}")
