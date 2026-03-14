from pypdf import PdfWriter

writer = PdfWriter()
writer.add_blank_page(width=300, height=300)
writer.encrypt("test123")

with open("pdf_protegido_test.pdf", "wb") as f:
    writer.write(f)

print("PDF protegido creado")
