import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from pathlib import Path
from sixel_ai.sixel_ocr import ocr_pdf_google_vision

pdf = Path("_inbox_raw/Chifa_faktura_19.12.2025.pdf")

text, debug = ocr_pdf_google_vision(pdf, cleanup=False)

print("=== OCR TEXT SAMPLE ===")
print(text[:2000])
print("\n=== DEBUG ===")
print(debug)
