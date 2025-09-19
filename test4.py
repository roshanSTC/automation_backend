import pdfplumber
import pandas as pd
import json
import re

def extract_pdf_content(pdf_path):
    print("extract_pdf_content")
    tables = []
    broker_name = "Unknown"

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            print(text)
            # ✅ Detect broker from text (only once)
            if broker_name == "Unknown" and text:
                broker_name = detect_broker_name(text)
                
                

            # ✅ Contract Note Date
            contract_match = re.search(r"BSE MUTUAL FUND CONTRACT NOTE\s*:\s*(\d{2}/\d{2}/\d{4})", text)
            contract_date = contract_match.group(1) if contract_match else None

            # ✅ Order Date & Sett No
            order_match = re.search(r"Order Date\s+(\d{2}/\d{2}/\d{4})", text)
            sett_match = re.search(r"Sett No\s+(\d+)", text)
            order_date = order_match.group(1) if order_match else None
            sett_no = sett_match.group(1) if sett_match else None

            # ✅ Stamp Duty
            stamp_match = re.search(r"STAMPDUTY\s+([\d.,]+)", text)
            stamp_duty = float(stamp_match.group(1).replace(",", "")) if stamp_match else 0.0

            # ✅ Extract all tables first
            page_tables = [pd.DataFrame(t[1:], columns=t[0]) 
                           for t in page.extract_tables() if t and len(t) > 1]

            if not page_tables:
                continue

            # ✅ Count total rows across all tables on this page
            total_rows = 3
            per_row_stamp_duty = stamp_duty / total_rows if total_rows > 0 else 0.0

            # ✅ Tag metadata & distribute stamp duty
            for df in page_tables:
                df["__page__"] = page_num
                df["__contract_date__"] = contract_date
                df["__order_date__"] = order_date
                df["__sett_no__"] = sett_no
                df["__stamp_duty__"] = per_row_stamp_duty
                df["__broker__"] = broker_name
                tables.append(df)

    return {"tables": tables, "broker": broker_name}

def detect_broker_name(text: str) -> str:
    """Detect broker name from text"""
    brokers = {
        "motilal oswal": "Motilal Oswal Financial Services Limited",
        "zerodha": "Zerodha Broking Limited",
        "hdfc": "HDFC Securities Limited",
        "icici": "ICICI Securities Limited",
        "phillipcapital": "PHILLIPCAPITAL (INDIA) PVT LTD"
    }

    text_lower = text.lower()
    for key, fullname in brokers.items():
        if key in text_lower:
            return fullname
    return "Unknown"

def build_json_from_tables(tables, category, subcategory):
    print("build_json_from_tables")
    results = []

    for df in tables:
        if "ISIN" not in df.columns:
            continue

        for _, row in df.iterrows():
            scrip_name = str(row.get("Scrip Name", "")).strip()
            if not scrip_name or scrip_name.lower() == "none":
                continue

            isin = str(row.get("ISIN", "")).strip()
            contract_date = row.get("__contract_date__", "Unknown")
            order_date = row.get("__order_date__", None)
            sett_no = row.get("__sett_no__", None)
            per_row_stamp_duty = row.get("__stamp_duty__", 0.0)
            broker_name = row.get("__broker__", "Unknown")

            entity_table = {
                "scripname": scrip_name,
                "scripcode": str(row.get("Scrip Code", "")),
                "benchmark": "0",
                "category": category,
                "subcategory": subcategory,
                "nickname": scrip_name,
                "isin": isin
            }

            action_table = {
                "scrip_code": str(row.get("Scrip Code", "")),
                "mode": str(row.get("Mode", "")),
                "order_type": str(row.get("Order Type", "")),
                "scrip_name": scrip_name,
                "isin": isin,
                "order_number": str(row.get("Order No", "")),
                "folio_number": str(row.get("Folio No", "")),
                "nav": try_float(row.get("NAV")),
                "stt": try_float(row.get("STT")),
                "unit": try_float(row.get("Unit")),
                "redeem_amount": try_float(row.get("Reedem Amt")),
                "purchase_amount": try_float(row.get("Purchase Amt")),
                "net_amount":  try_float(row.get("Purchase Amt")),
                "order_date": order_date,
                "sett_no": sett_no,
                "stamp_duty": per_row_stamp_duty,
                "page_number": row.get("__page__", None),
            }

            results.append({
                "entityTable": entity_table,
                "actionTable": action_table
            })

    return results

def build_json_phillip(tables, category, subcategory):
    results = []
    print( tables )
    return results

def process_pdf(pdf_file, category, subcategory):
    print('process_pdf')
    extracted = extract_pdf_content(pdf_file)
    broker = extracted["broker"]

    # ✅ Dispatcher based on broker + category + subcategory
    if broker == "Motilal Oswal Financial Services Limited" and category == "Equity" and subcategory == "Mutual Fund":
        json_data = build_json_from_tables(extracted["tables"], category, subcategory)

    elif broker == "PHILLIPCAPITAL (INDIA) PVT LTD" and category == "Equity" and subcategory == "Mutual Fund":
        json_data = build_json_phillip(extracted["tables"], category, subcategory)

    else:
        raise ValueError(f"❌ No parser available for Broker: {broker}, "
                         f"Category: {category}, Subcategory: {subcategory}")

    return broker, json_data

def try_float(val):
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0

if __name__ == "__main__":
    pdf_file = "Motilal.pdf"
    category = "Equity"
    subcategory = "Mutual Fund"

    broker, json_data = process_pdf(pdf_file, category, subcategory)

    print(f"✅ Detected Broker: {broker}")
    print(json.dumps(json_data, indent=4))

    with open("output.json", "w") as f:
        json.dump(json_data, f, indent=4)

    print("✅ JSON saved to output.json")
