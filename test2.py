import pdfplumber
import pytesseract
from pdf2image import convert_from_path
import pandas as pd
import re
import os

def extract_text_with_ocr(pdf_path):
    """
    Extracts text from PDF.
    First tries pdfplumber (native text).
    Falls back to OCR if page has no text.
    """
    all_text = []
    
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text()
            if text and text.strip():
                all_text.append(text)
            else:
                # Fallback: OCR
                print(f"⚠️ Page {page_num}: No text found, running OCR...")
                images = convert_from_path(pdf_path, first_page=page_num, last_page=page_num)
                for img in images:
                    text = pytesseract.image_to_string(img)
                    all_text.append(text)
    return "\n".join(all_text)

def extract_tables_with_ocr(pdf_path):
    """
    Extracts tables. If no tables found with pdfplumber, tries OCR on images.
    """
    tables = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            page_tables = page.extract_tables()
            if page_tables:
                for t in page_tables:
                    df = pd.DataFrame(t[1:], columns=t[0])
                    df["__page__"] = page_num
                    tables.append(df)
            else:
                # OCR fallback (table as raw text, needs parsing later)
                print(f"⚠️ Page {page_num}: No structured table, using OCR text.")
                images = convert_from_path(pdf_path, first_page=page_num, last_page=page_num)
                for img in images:
                    text = pytesseract.image_to_string(img)
                    # Here you can write regex to capture table-like text
                    tables.append(pd.DataFrame({"RawText": text.splitlines(), "__page__": page_num}))
    return tables

if __name__ == "__main__":
    pdf_file = "Phillip.pdf"
    POPPLER_PATH = r"C:\poppler\bin"   # 👈 update to your path
    # ✅ Extract plain text
    text = extract_text_with_ocr(pdf_file)
    print("📄 Extracted Text:\n", text[:1000], "...")  # print first 1000 chars

    # ✅ Extract tables
    tables = extract_tables_with_ocr(pdf_file)
    print(f"✅ Extracted {len(tables)} tables")

    if tables:
        print(tables[0].head())
