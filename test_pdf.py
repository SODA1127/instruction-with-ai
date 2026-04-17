from markdown_pdf import MarkdownPdf, Section
pdf = MarkdownPdf()
pdf.add_section(Section("안녕 하세요"))
pdf.save("test.pdf")
