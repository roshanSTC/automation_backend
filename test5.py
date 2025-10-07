import pdfplumber
import pandas as pd
import re
import json
import getpass
from PyPDF2 import PdfReader

def extract_pdf_content(pdf_path_or_file, category, subcategory, password=None):
    """
    Extract tables and metadata from PDF (Mutual Fund contract notes).
    Automatically dispatch to broker-specific parsing if recognized.
    """
    tables = []
    broker_name = "Unknown"
    text = ""
    print("function ectracted pdf content")

    with open_pdf(pdf_path_or_file, password=password) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            page_text = page.extract_text() or ""
            
            # Detect broker once
            if broker_name == "Unknown" and page_text:
                broker_name = detect_broker_name(page_text)

              # ✅ Skip extra pages for Phillip Capital
            if broker_name == "Phillip Capital (India) Pvt Ltd" and page_num > 1:
                continue  

            # Save only first page’s text (or concatenate for other brokers)
            if broker_name == "Phillip Capital (India) Pvt Ltd":
                if page_num == 1:
                    text = page_text
            else:
                text += "\n" + page_text  # concat for others
            
            # Extract contract note date
            contract_date = extract_date_from_text(text)
               
            # Stamp duty
            stamp_match = re.search(r"STAMPDUTY\s+([\d.,]+)", text)
            stamp_duty = float(stamp_match.group(1).replace(",", "")) if stamp_match else 0.0
           
            page_tables = [
                pd.DataFrame(t[1:], columns=t[0])
                for t in page.extract_tables() if t and len(t) > 1
            ]
            
            
            if not page_tables:
                continue
               
            # ✅ Count total rows across all tables on this page
            total_rows = 3
            per_row_stamp_duty = stamp_duty / total_rows if total_rows > 0 else 0.0

            for df in page_tables:
                df["__page__"] = page_num
                df["__contract_date__"] = contract_date
                df["__stamp_duty__"] = per_row_stamp_duty
                df["__broker__"] = broker_name
                tables.append(df)        

    return {"tables": tables, "broker": broker_name, "text": text,   }

def open_pdf(pdf_path_or_file, password=None):
    """
    Try opening a PDF with or without a password.
    If encrypted, ask for password if not provided.
    """
    # Step 1: Check encryption using PyPDF2
    try:
        reader = PdfReader(pdf_path_or_file)
        if reader.is_encrypted:
            print("⚠️ This PDF is password protected.")
            if not password:
                password = getpass.getpass("Enter PDF password: ")

            if not reader.decrypt(password):
                raise ValueError("❌ Incorrect password provided.")
            
            # ✅ If decrypted successfully, reopen with pdfplumber
            return pdfplumber.open(pdf_path_or_file, password=password)
        else:
            # Not encrypted, just open
            return pdfplumber.open(pdf_path_or_file)
    except Exception as e:
        raise RuntimeError(f"Error opening PDF: {e}")
    
def parse_phillip_text_format(text):
    """
    Parse Phillip Capital text format when table extraction fails
    """
    lines = text.split('\n')
    transactions = []
    print(" parse_phillip_text_format ",text)
    
    # Look for transaction lines
    for i, line in enumerate(lines):
        # Match lines that contain ISIN codes (format: INF followed by alphanumeric)
        if re.search(r'INF[A-Z0-9]{6}', line):
            # This line likely contains transaction data
            parts = line.split()
            if len(parts) >= 8:  # Ensure we have enough parts
                try:
                    # Extract data based on the format seen in your PDF
                    mutual_fund_name = parts[0] if parts else ""
                    
                    # Find scheme name (everything before ISIN)
                    isin_match = re.search(r'(INF[A-Z0-9]{6}[A-Z0-9]*)', line)
                    if isin_match:
                        isin = isin_match.group(1)
                        scheme_part = line[:isin_match.start()].strip()
                        # Extract scheme name (remove the fund code)
                        scheme_parts = scheme_part.split(' ', 1)
                        mutual_fund_scheme = scheme_parts[1] if len(scheme_parts) > 1 else scheme_part
                    else:
                        continue
                    
                    # Extract numerical values
                    numbers = re.findall(r'[\d,]+\.?\d*', line)
                    if len(numbers) >= 3:
                        purchase_units = numbers[-3].replace(',', '') if len(numbers) >= 3 else "0"
                        buy_rate = numbers[-2].replace(',', '') if len(numbers) >= 2 else "0"
                        buy_total = numbers[-1].replace(',', '') if len(numbers) >= 1 else "0"
                    else:
                        continue
                    
                    # Extract time and order number
                    time_match = re.search(r'(\d{2}:\d{2}:\d{2})', line)
                    order_time = time_match.group(1) if time_match else ""
                    
                    order_match = re.search(r'(\d{10})', line)  # 10 digit order number
                    order_no = order_match.group(1) if order_match else ""
                    
                    transactions.append({
                        'MUTUAL FUND NAME': mutual_fund_name,
                        'MUTUAL FUND SCHEME': mutual_fund_scheme,
                        'ISIN': isin,
                        'ORDER TIME': order_time,
                        'ORDER No': order_no,
                        'PURCHASE UNITS': purchase_units,
                        'BUY RATE': buy_rate,
                        'BUY TOTAL': buy_total,
                        'DATE': extract_date_from_text(text)
                    })
                except Exception as e:
                    print(f"Error parsing line: {line[:50]}... - {e}")
                    continue
    
    if transactions:
        return [pd.DataFrame(transactions)]
    return []

def extract_date_from_text(text):
    """
    Extract date from text in various formats
    """
    # Try different date formats
    date_patterns = [
        r"Date\s+(\d{2}/\d{2}/\d{4})",
        r"(\d{2}/\d{2}/\d{4})",
        r"Date:\s*(\d{2}/\d{2}/\d{4})",
    ]
    
    for pattern in date_patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return None

def detect_broker_name(text: str) -> str:
    brokers = {
        "motilal oswal": "Motilal Oswal Financial Services Limited",
        "zerodha": "Zerodha Broking Limited", 
        "hdfc": "HDFC Securities Limited",
        "icici": "ICICI Securities Limited",
        "phillipcapital": "Phillip Capital (India) Pvt Ltd",
        "phillip capital": "Phillip Capital (India) Pvt Ltd"
    }
    text_lower = text.lower()
    for key, fullname in brokers.items():
        if key in text_lower:
            return fullname
    return "Unknown"

def try_float(val):
    if val is None:
        return 0.0
    try:
        # Handle string values with commas
        if isinstance(val, str):
            val = val.replace(',', '').strip()
        return float(val)
    except (ValueError, TypeError):
        return 0.0

def build_json_from_tables(tables, category, subcategory):
    """
    Build JSON for Motilal Oswal PDFs
    """
    results = []
    
    for df in tables:
        # Normalize columns
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

        if "isin" not in df.columns:
            continue

        for _, row in df.iterrows():
            scrip_name = str(row.get("scrip_name") or row.get("scheme_name") or "").strip()
            if not scrip_name or scrip_name.lower() == "none":
                continue

            isin = str(row.get("isin") or "").strip()
            contract_date = row.get("__contract_date__", "Unknown")
            per_row_stamp_duty = row.get("__stamp_duty__", 0.0)
            
            entity_table = {
                "scripname": scrip_name,
                "scripcode": str(row.get("scrip_code") or ""),
                "benchmark": "0",
                "category": category,
                "subcategory": subcategory,
                "nickname": scrip_name,
                "isin": isin
            }

            action_table = {
                "scrip_code": str(row.get("scrip_code") or ""),
                "mode": str(row.get("mode") or ""),
                "order_type": str(row.get("order_type") or ""),
                "scrip_name": scrip_name,
                "isin": isin,
                "order_number": str(row.get("order_no") or ""),
                "folio_number": str(row.get("folio_no") or ""),
                "nav": try_float(row.get("nav")),
                "stt": try_float(row.get("stt")),
                "unit": try_float(row.get("unit")),
                "redeem_amount": try_float(row.get("redeem_amt") or row.get("reedem_amt")),
                "purchase_amount": try_float(row.get("purchase_amt") or row.get("purchase_amount")),
                "net_amount": try_float(row.get("purchase_amt") or row.get("purchase_amount")),
                "order_date": contract_date,
                "stamp_duty": per_row_stamp_duty,
                "page_number": row.get("__page__", None),
            }

            results.append({"entityTable": entity_table, "actionTable": action_table})

    return results

def build_json_phillip_with_contract_note(tables, category, subcategory):
    """Parser for Phillip Capital format WITH CONTRACT NOTE NO (equity contract notes)"""
    results = []
    print("Parsing Phillip Contract Note (equity format)...")
    print("working on phillips capital second format")
    print("tables :- ", tables)
    # column mapping to handle variations
    col_map = {
        "order_no": ["order_no.", "order_no"],
        "security": ["security_/_contract_description", "security_/_contract\ndescription"],
        "buy_sell": ["buy(b)_/_sell(s)", "buy/sell"],
        "quantity": ["quantity"],
        "gross_rate": ["gross_rate/_trade_price_per_unit_(rs.)@", "gross_rate/_trade_price"],
        "brokerage": ["brokerage_per_unit_(rs.)", "brokerage"],
        "net_rate": ["net_rate_per_unit_(rs.)**", "net_rate_per_unit_(rs.)"],
        "stt": ["stt"],
        "net_total": ["net_total_(before_levies)_(rs.)", "net_total"],
    }

    def get_val(row, keys, default=""):
        for k in keys:
            if k in row:
                return row[k]
        return default

    for df in tables:
        # normalize column names
        df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
        print("df.columns :-", df.columns)

        # drop "NSE - CAPITAL - Normal..." lines
        df = df[~df.iloc[:, 0].astype(str).str.contains("NSE - CAPITAL", na=False, case=False)]
        print("cleaned df:-", df)

        for _, row in df.iterrows():
            try:
                row = row.to_dict()

                # ISIN is separate, may need to join with following row
                isin_match = re.search(r"isin[: ]+([A-Z0-9]+)", " ".join([str(v) for v in row.values()]), re.IGNORECASE)
                isin = isin_match.group(1) if isin_match else ""

                scrip_name = str(get_val(row, col_map["security"], "")).strip()
                order_type = "PURCHASE" if str(get_val(row, col_map["buy_sell"], "")).upper() == "BUY" else "SELL"

                entity_table = {
                    "scrip_name": scrip_name,
                    "scrip_code": scrip_name.split()[0] if scrip_name else "",
                    "benchmark": "0",
                    "category": category,
                    "subcategory": subcategory,
                    "nickname": scrip_name,
                    "isin": isin,
                }

                action_table = {
                    "scrip_code": scrip_name.split()[0] if scrip_name else "",
                    "mode": "DEMAT",
                    "order_type": order_type,
                    "scrip_name": scrip_name,
                    "isin": isin,
                    "order_number": str(get_val(row, col_map["order_no"], "")),
                    "folio_number": "0",
                    "nav": try_float(get_val(row, col_map["gross_rate"], 0)),
                    "stt": try_float(get_val(row, col_map["stt"], 0)),
                    "unit": try_float(get_val(row, col_map["quantity"], 0)),
                    "redeem_amount": 0.0 if order_type == "PURCHASE" else try_float(get_val(row, col_map["net_total"], 0)),
                    "purchase_amount": try_float(get_val(row, col_map["net_total"], 0)) if order_type == "PURCHASE" else 0.0,
                    "net_amount": try_float(get_val(row, col_map["net_total"], 0)),
                    "order_date": "",  # you can inject from header TRADE DATE
                    "stamp_duty": 0.0,
                    "page_number": row.get("__page__", None),
                    "contract_note_no": "",  # inject from header CONTRACT NOTE NO
                }

                results.append({"entityTable": entity_table, "actionTable": action_table})

            except Exception as e:
                print("Parse error:", e)
                continue

    return results

def build_json_phillip_without_contract_note(tables, category, subcategory):
    collected_values = []  # store only values
    print("without contract note ")
    
    for df in tables:
        # Detect header row and normalize columns
        if df.iloc[0].astype(str).str.contains("MUTUAL FUND NAME", case=False, na=False).any():
            df.columns = (
                df.iloc[0]
                .astype(str)
                .str.strip()
                .str.lower()
                .str.replace(" ", "_")
                .str.replace("/", "_")
            )
            df = df.drop(index=0).reset_index(drop=True)

        for _, row in df.iterrows():
            collected_values.append(list(row.values))  # store all values

    # ✅ Filter out unnecessary rows and remove empty strings
    filtered_values = []
    for row in collected_values:
        if not row or not row[0]:  # skip empty rows
            continue
        if str(row[0]).strip().lower() in [
            'net obligation',
            'cgst (@ 9.00%)',
            'sgst (@ 9.00%)',
            'stamp duty',
            'total amount rs.'
        ]:
            continue
        # Remove empty strings from the row
        cleaned_row = [value for value in row if value not in (None, '')]
        if cleaned_row:  # only add non-empty rows
            filtered_values.append(cleaned_row)
      # Create objects with entityTable and actionTable
    final_results = []
    
    for row in filtered_values:
        # Build actionTable
        action_table = {
            "scrip_code": row[0] if len(row) > 0 else "",
            "mode": "DEMAT",
            "order_type": "PURCHASE",
            "scrip_name": row[1] if len(row) > 1 else "",
            "isin": str(row[2]).replace(' ', ''),
            "order_number": str(row[4]),
            "folio_number": "0",
            "nav": float(str(row[6]).replace(' ', '')),
            "stt":0.0,
            "unit": float(str(row[5]).replace(' ', '')) ,
            "redeem_amount": 0.0,
            "purchase_amount": float(row[7]) ,
            "net_amount": float(row[7]) ,
            "order_date": row[9] if len(row) > 9 else "",
            "stamp_duty": float(row[17]) if len(row) > 17 and str(row[17]).replace('.', '', 1).isdigit() else 0.0,
            "page_number": None
        }

        # Build entityTable (example: some key info, can customize)
        entity_table = {
            "scrip_name": row[1] if len(row) > 1 else "",
            "scrip_code": row[0] if len(row) > 0 else "",
            "benchmark": "0",
            "category": category,
            "subcategory": subcategory,
            "nickname": row[1] if len(row) > 1 else "",
            "isin": str(row[2]).replace(' ', ''),
        }

        final_results.append({
            "entityTable": entity_table,
            "actionTable": action_table
        })
       
       

    print("📌 Filtered & cleaned transaction rows:",final_results )
    return final_results

def clean_columns(df):
    """Normalize messy Phillip Capital headers to clean names"""
    mapping = {}
    for col in df.columns:
        if not col:  # skip empty
            continue
        col_clean = str(col).strip().lower().replace(" ", "_")
        
        if "mutual" in col_clean and "name" in col_clean:
            mapping[col] = "mutual_fund_name"
        elif "mutual" in col_clean and "scheme" in col_clean:
            mapping[col] = "mutual_fund_scheme"
        elif "isin" in col_clean:
            mapping[col] = "isin"
        elif "order" in col_clean and "no" in col_clean:
            mapping[col] = "order_no"
        elif "order" in col_clean and "time" in col_clean:
            mapping[col] = "order_time"
        elif "purchase" in col_clean and "unit" in col_clean:
            mapping[col] = "purchase_units"
        elif "buy" in col_clean and "rate" in col_clean:
            mapping[col] = "buy_rate"
        elif "buy" in col_clean and "total" in col_clean:
            mapping[col] = "buy_total"
        elif "date" in col_clean:
            mapping[col] = "date"
        elif "folio" in col_clean:
            mapping[col] = "folio_no"
        else:
            mapping[col] = col_clean  # keep original (normalized)

    return mapping

def detect_phillip_format(text: str) -> str:
    print("detect phillips format:- ",text)
    text_lower = text.lower()
    
    if "contract note no" in text_lower:
        return "contract_note"
    elif "mutual fund transaction confirmation note" in text_lower:
        return "mfss"
    else:
        return "unknown"

def process_pdf(pdf_file, category, subcategory):
    """
    Main function to process PDF and return JSON data
    """
    json_data = []
    try:
        extracted = extract_pdf_content(pdf_file, category, subcategory)  # ✅ Pass category + subcategory
        broker = extracted["broker"]
              
        
        for i, df in enumerate(extracted["tables"]):
            if isinstance(df, pd.DataFrame) and not df.empty:
                print(f" df.columns df.columns")

        if broker == "Motilal Oswal Financial Services Limited":
            json_data = build_json_from_tables(extracted["tables"], category, subcategory)
        elif broker == "Phillip Capital (India) Pvt Ltd":
            format_type = detect_phillip_format(extracted["text"])
            if format_type == "contract_note":
                json_data = build_json_phillip_with_contract_note(extracted["tables"], category, subcategory)
            elif format_type == "mfss":
                json_data = build_json_phillip_without_contract_note(extracted["tables"], category, subcategory)
            else:
                raise ValueError("Unsupported Phillip Capital format")

        print(f"DEBUG: JSON data length -> {len(json_data)}")
        return broker, json_data
        
    except Exception as e:
        print(f"ERROR: Failed to process PDF: {e}")
        raise

if __name__ == "__main__":
    # Update this to your PDF file path
    pdf_file = "PDF/Password.pdf"  # Update with your actual file path
    category = "Equity"
    subcategory = "Mutual Fund"

    try:
        broker, json_data = process_pdf(pdf_file, category, subcategory)

        print(f"\nDetected Broker: {broker}")
        print(f"Number of transactions processed: {len(json_data)}")
        
        if json_data:
            print("\nSample transaction:")
            # print(json.dumps(json_data[0], indent=2))
            
            # Validate data before saving
            print("\n=== VALIDATION CHECK ===")
            for i, record in enumerate(json_data[:3]):  # Check first 3 records
                entity = record.get("entityTable", {})
                action = record.get("actionTable", {})
                
                print(f"Record {i+1}:")
                print(f"  - ISIN: {entity.get('isin', 'MISSING')}")
                print(f"  - Script Name: {entity.get('scripname', 'MISSING')}")
                print(f"  - Units: {action.get('unit', 'MISSING')}")
                print(f"  - NAV: {action.get('nav', 'MISSING')}")
                print(f"  - Purchase Amount: {action.get('purchase_amount', 'MISSING')}")
                
                # Check for common issues
                if not entity.get('isin'):
                    print(f"  ⚠️ WARNING: Missing ISIN")
                if action.get('unit', 0) == 0:
                    print(f"  ⚠️ WARNING: Zero units")
                if action.get('purchase_amount', 0) == 0:
                    print(f"  ⚠️ WARNING: Zero purchase amount")
            
            # Save to file
            with open("output.json", "w") as f:
                json.dump(json_data, f, indent=4)
            print(f"\nJSON saved to output.json")
            
            # Additional check - save raw extracted data for debugging
            with open("debug_raw_data.json", "w") as f:
                debug_data = {
                    "broker": broker,
                    "total_records": len(json_data),
                    "sample_record": json_data[0] if json_data else None,
                    "all_records": json_data
                }
                json.dump(debug_data, f, indent=4)
            print("Debug data saved to debug_raw_data.json")
            
        else:
            print("❌ No transactions were extracted from the PDF")
            print("This might be why your API shows 'success' but inserts no data!")
            
    except Exception as e:
        print(f"Error processing PDF: {e}")
        import traceback
        traceback.print_exc()