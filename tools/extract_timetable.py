from pathlib import Path
import re
from pypdf import PdfReader

pdf_path = Path(r"C:\Users\U\project\Study-hub\static\notes\261_TT_5th_Sem_Updated (7).pdf")
reader = PdfReader(str(pdf_path))
for i, page in enumerate(reader.pages, 1):
    text = page.extract_text() or ""
    print(f"===== PAGE {i} =====")
    print(text)
    print(f"===== END PAGE {i} =====\n")
