import pdfplumber
import pandas as pd
import json
import re

def extract_pdf_content(pdf_path):
    tables = []
    broker_name = "Unknown"

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            print(text)
            # ✅ Detect broker from text
            if broker_name == "Unknown":
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

            # ✅ Extract tables
            page_tables = [pd.DataFrame(t[1:], columns=t[0]) 
                           for t in page.extract_tables() if t and len(t) > 1]

            for df in page_tables:
                df["__page__"] = page_num
                tables.append(df)

    return {"tables": tables, "broker": broker_name}


def detect_broker_name(text: str) -> str:
    brokers = {
        "motilal oswal": "Motilal Oswal Financial Services Limited",
        "zerodha": "Zerodha Broking Limited",
        "hdfc": "HDFC Securities Limited",
        "phillip capital": "Phillip Capital (India) Pvt Ltd"
    }

    text_lower = text.lower()
    for key, fullname in brokers.items():
        if key in text_lower:
            return fullname
    return "Unknown"


# -------------------- PARSER: MOTILAL --------------------
def build_json_motilal(tables, category, subcategory):
    results = []
    for df in tables:

        for _, row in df.iterrows():
            print("RAW ROW:", row.to_dict()) 
            scrip_name = str(row.get("Scrip Name", "")).strip()
            if not scrip_name or scrip_name.lower() == "none":
                continue

            entity_table = {
                "scripname": scrip_name,
                "scripcode": str(row.get("Scrip Code", "")),
                "benchmark": "0",
                "category": category,
                "subcategory": subcategory,
                "nickname": scrip_name,
                "isin": str(row.get("ISIN", "")).strip()
            }

            action_table = {
                "scrip_code": str(row.get("Scrip Code", "")),
                "mode": str(row.get("Mode", "")),
                "order_type": str(row.get("Order Type", "")),
                "scrip_name": scrip_name,
                "isin": str(row.get("ISIN", "")),
                "order_number": str(row.get("Order No", "")),
                "folio_number": str(row.get("Folio No", "")),
                "nav": try_float(row.get("NAV")),
                "stt": try_float(row.get("STT")),
                "unit": try_float(row.get("Unit")),
                "redeem_amount": try_float(row.get("Reedem Amt")),
                "purchase_amount": try_float(row.get("Purchase Amt")),
                "net_amount": try_float(row.get("Net Amount")),
                "order_date": row.get("__order_date__", None),
                "sett_no": row.get("__sett_no__", None),
                "stamp_duty": row.get("__stamp_duty__", 0.0),
                "page_number": row.get("__page__", None)
            }

            results.append({"entityTable": entity_table, "actionTable": action_table})

    return results


# -------------------- PARSER: PHILLIP CAPITAL --------------------
def build_json_phillip(tables, category, subcategory):
    results = []
    for df in tables:
        # Phillip PDFs have different headers
        if "Mutual Fund Name" not in df.columns:
            continue

        for _, row in df.iterrows():
            scrip_code = str(row.get("Mutual Fund Name", "")).strip()
            scrip_name = str(row.get("Mutual Fund Scheme", "")).strip()

            entity_table = {
                "scripname": scrip_name,
                "scripcode": scrip_code,
                "benchmark": "0",
                "category": category,
                "subcategory": subcategory,
                "nickname": scrip_name,
                "isin": str(row.get("ISIN", "")) if "ISIN" in df.columns else ""
            }

            action_table = {
                "scrip_code": scrip_code,
                "mode": "DEMAT",  # Phillip typically DEMAT
                "order_type": "PURCHASE",  # assuming purchase
                "scrip_name": scrip_name,
                "isin": entity_table["isin"],
                "order_number": str(row.get("Order No", "")),
                "folio_number": str(row.get("Folio No", "")),
                "nav": try_float(row.get("Buy Rate")),
                "stt": 0.0,  # Phillip may not show STT
                "unit": try_float(row.get("Purchase Units")),
                "redeem_amount": 0.0,
                "purchase_amount": try_float(row.get("Buy Total")),
                "net_amount": 0.0,
                "order_date": str(row.get("Date", "")),   # ✅ "Order Date" is called "Date"
                "sett_no": str(row.get("Sett No", "")),
                "stamp_duty": 0.0,   # adjust if provided
                "page_number": row.get("__page__", None)
            }

            results.append({"entityTable": entity_table, "actionTable": action_table})

    return results


# -------------------- ROUTER --------------------
def process_pdf(pdf_file, category, subcategory):
    extracted = extract_pdf_content(pdf_file)
    broker = extracted["broker"]

    if broker == "Motilal Oswal Financial Services Limited":
        json_data = build_json_motilal(extracted["tables"], category, subcategory)
    elif broker == "Phillip Capital (India) Pvt Ltd":
        json_data = build_json_phillip(extracted["tables"], category, subcategory)
    else:
        raise ValueError(f"❌ No parser available for broker: {broker}")

    return broker, json_data


def try_float(val):
    try:
        return float(str(val).replace(",", ""))
    except (ValueError, TypeError, AttributeError):
        return 0.0


if __name__ == "__main__":
    pdf_file = "Motilal.pdf"
    category = "Equity"
    subcategory = "Mutual Fund"
    
    broker, json_data = process_pdf(pdf_file, category, subcategory)

    print(f"✅ Detected Broker: {broker}")
    print(json.dumps(json_data, indent=4))

    with open("output.json", "w") as f:
        json.dump(json_data, f, indent=4)
