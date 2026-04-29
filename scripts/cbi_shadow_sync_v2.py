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

def standardize_date(date_str):
    for fmt in ("%d %b %Y", "%d-%b-%y", "%d %B %Y", "%d-%b-%Y"):
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

def parse_pdf(pdf_bytes):
    """
    Extract Fund Name, ManCo, Depositary, Auth_Date from the CBI register PDF.
    Tries structured table extraction first, falls back to text parsing.
    """
    records = []
    date_pattern = re.compile(r"(\d{1,2}[- ](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[- ]\d{2,4})")

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        print("PDF has " + str(len(pdf.pages)) + " pages")

        for page in pdf.pages:
            tables = page.extract_tables()

            if tables:
                for table in tables:
                    for row in table:
                        if not row or not any(row):
                            continue
                        cells = [str(c).strip().replace("\n", " ") if c else "" for c in row]

                        # Skip header rows
                        if cells[0].lower() in ("fund name", "name", "ucits", ""):
                            continue

                        # Find the date cell
                        date_str = ""
                        date_col = -1
                        for i, cell in enumerate(cells):
                            m = date_pattern.search(cell)
                            if m:
                                date_str = m.group(1)
                                date_col = i
                                break

                        if not date_str or not cells[0] or len(cells[0]) < 3:
                            continue

                        # Columns are typically: Fund Name | ManCo | Depositary | Auth Date
                        fund_name  = cells[0]
                        manco      = cells[1] if len(cells) > 1 and date_col != 1 else ""
                        depositary = cells[2] if len(cells) > 2 and date_col not in (1, 2) else ""

                        records.append({
                            "Fund Name":  fund_name,
                            "ManCo":      manco,
                            "Depositary": depositary,
                            "Auth_Date":  standardize_date(date_str),
                            "First_Seen": datetime.now().strftime("%Y-%m-%d")
                        })

            else:
                # Fallback: text line parsing (original approach)
                text = page.extract_text()
                if text:
                    for line in text.split("\n"):
                        m = date_pattern.search(line)
                        if m:
                            name = re.sub(r"\s+", " ", line[:m.start()]).strip().rstrip(",")
                            if len(name) > 3:
                                records.append({
                                    "Fund Name":  name,
                                    "ManCo":      "",
                                    "Depositary": "",
                                    "Auth_Date":  standardize_date(m.group(1)),
                                    "First_Seen": datetime.now().strftime("%Y-%m-%d")
                                })

    # Deduplicate by Fund Name
    seen = set()
    deduped = []
    for r in records:
        if r["Fund Name"] not in seen:
            seen.add(r["Fund Name"])
            deduped.append(r)

    print("Extracted " + str(len(deduped)) + " unique funds")
    return deduped

def run_sync():
    # Load existing DB if present
    if os.path.exists(DB_FILE):
        existing_df = pd.read_csv(DB_FILE)
        existing_names = set(existing_df["Fund Name"].values)
    else:
        existing_df = pd.DataFrame(columns=["Fund Name", "ManCo", "Depositary", "Auth_Date", "First_Seen"])
        existing_names = set()

    # Download and parse
    pdf_bytes = download_pdf()
    records   = parse_pdf(pdf_bytes)

    # Split into new vs existing
    new_records = [r for r in records if r["Fund Name"] not in existing_names]

    # Merge: fresh parse replaces existing (so ManCo/Depositary gets populated)
    # Build full dataframe from fresh parse, preserving First_Seen from existing where possible
    first_seen_map = {}
    if not existing_df.empty and "First_Seen" in existing_df.columns:
        for _, row in existing_df.iterrows():
            first_seen_map[row["Fund Name"]] = row.get("First_Seen", "")

    for r in records:
        if r["Fund Name"] in first_seen_map and first_seen_map[r["Fund Name"]]:
            r["First_Seen"] = first_seen_map[r["Fund Name"]]

    df = pd.DataFrame(records, columns=["Fund Name", "ManCo", "Depositary", "Auth_Date", "First_Seen"])
    df["Auth_Date_DT"] = pd.to_datetime(df["Auth_Date"], errors="coerce")
    df = df.sort_values("Auth_Date_DT", ascending=False).drop(columns=["Auth_Date_DT"])

    os.makedirs("data", exist_ok=True)
    df.to_csv(DB_FILE, index=False)

    etf_count = df["Fund Name"].str.contains("ETF", case=False, na=False).sum()
    manco_populated = (df["ManCo"] != "").sum()
    print("Total funds: " + str(len(df)))
    print("ETFs: " + str(etf_count))
    print("New this run: " + str(len(new_records)))
    print("ManCo populated: " + str(manco_populated) + " / " + str(len(df)))

if __name__ == "__main__":
    run_sync()
