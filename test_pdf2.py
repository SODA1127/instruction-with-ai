from markdown_pdf import MarkdownPdf, Section
import io
pdf = MarkdownPdf()
pdf.add_section(Section("안녕 하세요"))
buf = io.BytesIO()
pdf.save(buf)
print(len(buf.getvalue()))
