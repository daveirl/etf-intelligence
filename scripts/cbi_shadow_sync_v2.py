import requests
from bs4 import BeautifulSoup
import pdfplumber
import pandas as pd
import io
import re
import os
from datetime import datetime

DOWNLOADS_PAGE = "https://registers.centralbank.ie/DownloadsPage.aspx"
TARGET_TEXT = "Authorised UCITS, European Communities (Undertakings for Collective Investment in Transferable Securities) Regulations 2011"
DB_FILE = "data/cbi_shadow_db.csv"

# Column x-boundaries in PDF points (detected from header row)
COL_DATE_START    = 210
COL_MANCO_START   = 370
COL_TRUSTEE_START = 600

DATE_PATTERN = re.compile(
    r"\b(\d{1,2}[-\s](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[-\s]\d{2,4}"
    r"|\d{1,2}\s(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s\d{4})\b",
    re.IGNORECASE
)


def standardize_date(date_str):
    for fmt in ("%d %b %Y", "%d-%b-%y", "%d %B %Y", "%d-%b-%Y", "%d %b %y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return date_str.strip()


def looks_like_company(text):
    if not text or len(text.strip()) < 5:
        return False
    indicators = [
        "limited", "ltd", "plc", "s.a", "gmbh", "management", "asset", "trust",
        "capital", "investment", "services", "mellon", "state street",
        "northern trust", "deutsche", "bank", "global", "international",
        "custody", "depositary", "branch"
    ]
    return any(i in text.lower() for i in indicators)


def looks_like_address(text):
    if not text:
        return True
    t = text.strip()
    # Starts with a street number
    if re.match(r"^\d+", t):
        return True
    # Dublin postcode e.g. D02 FT59
    if re.match(r"^d\d{2}\s", t, re.I):
        return True
    # Address-specific keywords (not "ireland" — too common in company names)
    keywords = ["floor", "quay", "road", "street", "place", "house", "court",
                "square", "avenue", "lane", "dock", "dublin 2", "dublin 1",
                "sir john", "merrion", "grand canal"]
    return any(k in t.lower() for k in keywords)


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


def parse_pdf(pdf_bytes):
    records = []
    current_manco = ""
    current_trustee = ""
    seen = set()

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        print("Pages: " + str(len(pdf.pages)))

        for page in pdf.pages:
            words = page.extract_words(x_tolerance=3, y_tolerance=3)
            if not words:
                continue

            # Group words into lines by vertical position
            lines = {}
            for w in words:
                y = round(w["top"])
                matched = None
                for ey in lines:
                    if abs(ey - y) <= 4:
                        matched = ey
                        break
                if matched is None:
                    lines[y] = []
                    matched = y
                lines[matched].append(w)

            for y in sorted(lines.keys()):
                line_words = sorted(lines[y], key=lambda w: w["x0"])
                line_text  = " ".join(w["text"] for w in line_words)

                # Skip header/footer lines
                if re.search(
                    r"Run Date:|Page \d+ of \d+|Name of UCITS|Date of|Authorisation|Management Company",
                    line_text
                ):
                    continue

                # Must contain a date
                date_match = DATE_PATTERN.search(line_text)
                if not date_match:
                    continue

                # Split words into columns by x position
                name_words    = [w for w in line_words if w["x0"] < COL_DATE_START]
                manco_words   = [w for w in line_words if COL_MANCO_START <= w["x0"] < COL_TRUSTEE_START]
                trustee_words = [w for w in line_words if w["x0"] >= COL_TRUSTEE_START]

                fund_name  = " ".join(w["text"] for w in name_words).strip()
                manco_text = " ".join(w["text"] for w in manco_words).strip()
                dep_text   = " ".join(w["text"] for w in trustee_words).strip()

                if not fund_name or len(fund_name) < 3:
                    continue

                # Umbrella line: ManCo column has a real company name (not an address)
                if looks_like_company(manco_text) and not looks_like_address(manco_text):
                    current_manco   = manco_text
                    current_trustee = dep_text if looks_like_company(dep_text) and not looks_like_address(dep_text) else ""

                if fund_name not in seen:
                    seen.add(fund_name)
                    records.append({
                        "Fund Name":  fund_name,
                        "ManCo":      current_manco,
                        "Depositary": current_trustee,
                        "Auth_Date":  standardize_date(date_match.group(0)),
                        "First_Seen": datetime.now().strftime("%Y-%m-%d")
                    })

    print("Extracted " + str(len(records)) + " unique funds")
    manco_pop = sum(1 for r in records if r["ManCo"])
    dep_pop   = sum(1 for r in records if r["Depositary"])
    print("ManCo populated:      " + str(manco_pop) + "/" + str(len(records)))
    print("Depositary populated: " + str(dep_pop)   + "/" + str(len(records)))

    print("\nSample ETFs:")
    for r in [r for r in records if "ETF" in r["Fund Name"]][:4]:
        print("  " + r["Fund Name"])
        print("    ManCo: " + r["ManCo"])
        print("    Dep:   " + r["Depositary"])

    return records


def run_sync():
    first_seen_map = {}
    if os.path.exists(DB_FILE):
        existing_df = pd.read_csv(DB_FILE)
        if "First_Seen" in existing_df.columns:
            for _, row in existing_df.iterrows():
                first_seen_map[row["Fund Name"]] = row.get("First_Seen", "")

    pdf_bytes = download_pdf()
    records   = parse_pdf(pdf_bytes)

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
