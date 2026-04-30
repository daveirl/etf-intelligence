import requests
from bs4 import BeautifulSoup
import pandas as pd
import subprocess
import tempfile
import re
import os
from datetime import datetime

DOWNLOADS_PAGE = "https://registers.centralbank.ie/DownloadsPage.aspx"
TARGET_TEXT = "Authorised UCITS, European Communities (Undertakings for Collective Investment in Transferable Securities) Regulations 2011"
DB_FILE = "data/cbi_shadow_db.csv"


def standardize_date(date_str):
    for fmt in ("%d %b %Y", "%d-%b-%y", "%d %B %Y", "%d-%b-%Y", "%d %b %y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return date_str.strip()


def download_pdf():
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    res = session.get(DOWNLOADS_PAGE)
    soup = BeautifulSoup(res.text, "html.parser")

    payload = {
        "__EVENTTARGET": "",
        "__EVENTARGUMENT": "",
        "__VIEWSTATE": soup.find("input", {"id": "__VIEWSTATE"})["value"],
        "__VIEWSTATEGENERATOR": soup.find("input", {"id": "__VIEWSTATEGENERATOR"})["value"],
        "__EVENTVALIDATION": soup.find("input", {"id": "__EVENTVALIDATION"})["value"]
    }

    for link in soup.find_all("a", href=True):
        if TARGET_TEXT in link.text:
            match = re.search(r"'(.*?)'", link["href"])
            if match:
                payload["__EVENTTARGET"] = match.group(1)
                break

    pdf_res = session.post(DOWNLOADS_PAGE, data=payload)
    print("Downloaded " + str(round(len(pdf_res.content) / 1024)) + " KB")
    return pdf_res.content


def looks_like_company(text):
    text = text.strip()
    if len(text) < 5:
        return False
    indicators = [
        "limited", "ltd", "plc", "s.a", "gmbh", "management",
        "asset", "trust", "capital", "investment", "services",
        "mellon", "state street", "northern trust", "deutsche", "bank",
        "global", "international", "europe", "ireland", "custody",
        "depositary", "branch"
    ]
    lower = text.lower()
    return any(i in lower for i in indicators)


def parse_pdf_text(pdf_bytes):
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(pdf_bytes)
        tmp_path = f.name

    result = subprocess.run(
        ["pdftotext", "-layout", tmp_path, "-"],
        capture_output=True, text=True
    )
    os.unlink(tmp_path)
    text = result.stdout

    date_pattern = re.compile(
        r"\b(\d{1,2}[-\s](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[-\s]\d{2,4}"
        r"|\d{2}\s(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s\d{4})\b",
        re.IGNORECASE
    )

    records = []
    current_manco = ""
    current_trustee = ""
    seen = set()

    for line in text.split("\n"):
        if re.search(
            r"Run Date:|Page \d+ of \d+|Name of UCITS|Date of|Authorisation|Management Company|Trustee",
            line
        ):
            continue
        if not line.strip():
            continue

        date_match = date_pattern.search(line)
        if not date_match:
            continue

        date_pos = date_match.start()
        date_str = standardize_date(date_match.group(0))
        after_date = line[date_match.end():].strip()
        fund_name = line[:date_pos].strip()

        if not fund_name or len(fund_name) < 3:
            continue

        after_parts = re.split(r"\s{2,}", after_date)
        after_parts = [p.strip() for p in after_parts if p.strip()]

        manco_candidate = after_parts[0] if len(after_parts) > 0 else ""
        trustee_candidate = after_parts[1] if len(after_parts) > 1 else ""

        if looks_like_company(manco_candidate):
            current_manco = manco_candidate
            current_trustee = trustee_candidate if looks_like_company(trustee_candidate) else ""

        if fund_name not in seen:
            seen.add(fund_name)
            records.append({
                "Fund Name": fund_name,
                "ManCo": current_manco,
                "Depositary": current_trustee,
                "Auth_Date": date_str,
                "First_Seen": datetime.now().strftime("%Y-%m-%d")
            })

    print("Extracted " + str(len(records)) + " unique funds")
    manco_pop = sum(1 for r in records if r["ManCo"])
    dep_pop = sum(1 for r in records if r["Depositary"])
    print("ManCo populated:      " + str(manco_pop) + "/" + str(len(records)))
    print("Depositary populated: " + str(dep_pop) + "/" + str(len(records)))

    return records


def run_sync():
    first_seen_map = {}
    if os.path.exists(DB_FILE):
        existing_df = pd.read_csv(DB_FILE)
        if "First_Seen" in existing_df.columns:
            for _, row in existing_df.iterrows():
                first_seen_map[row["Fund Name"]] = row.get("First_Seen", "")

    pdf_bytes = download_pdf()
    records = parse_pdf_text(pdf_bytes)

    for r in records:
        if r["Fund Name"] in first_seen_map and first_seen_map[r["Fund Name"]]:
            r["First_Seen"] = first_seen_map[r["Fund Name"]]

    df = pd.DataFrame(records, columns=["Fund Name", "ManCo", "Depositary", "Auth_Date", "First_Seen"])
    df["Auth_Date_DT"] = pd.to_datetime(df["Auth_Date"], errors="coerce")
    df = df.sort_values("Auth_Date_DT", ascending=False).drop(columns=["Auth_Date_DT"])

    os.makedirs("data", exist_ok=True)
    df.to_csv(DB_FILE, index=False)
    print("Saved " + str(len(df)) + " records to " + DB_FILE)


if __name__ == "__main__":
    run_sync()
