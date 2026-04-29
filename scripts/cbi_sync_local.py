"""
cbi_sync_local.py
─────────────────
Run this locally (not via GitHub Actions).
1. Downloads the CBI UCITS register PDF (requires a real browser session)
2. Extracts Fund Name, ManCo, Depositary, Auth_Date from the PDF tables
3. Rebuilds data/cbi_shadow_db.csv from scratch
4. Pushes the CSV + regenerated dashboard to GitHub via the API

Setup:
    pip install requests beautifulsoup4 pdfplumber pandas

Usage:
    python cbi_sync_local.py

    # To also push to GitHub, set these env vars first:
    export GITHUB_TOKEN=your_personal_access_token
    export GITHUB_REPO=daveirl/etf-intelligence
"""

import requests
from bs4 import BeautifulSoup
import pdfplumber
import pandas as pd
import io
import re
import os
import base64
import json
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
DOWNLOADS_PAGE = "https://registers.centralbank.ie/DownloadsPage.aspx"
TARGET_TEXT    = "Authorised UCITS, European Communities (Undertakings for Collective Investment in Transferable Securities) Regulations 2011"
DB_FILE        = "data/cbi_shadow_db.csv"
GITHUB_TOKEN   = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO    = os.environ.get("GITHUB_REPO", "daveirl/etf-intelligence")
TODAY          = datetime.now().strftime("%Y-%m-%d")

# ── Date parsing ──────────────────────────────────────────────────────────────
def standardize_date(date_str):
    for fmt in ("%d %b %Y", "%d-%b-%y", "%d %B %Y", "%d-%b-%Y", "%d %b %y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return date_str.strip()

# ── PDF download ──────────────────────────────────────────────────────────────
def download_pdf():
    print("Fetching CBI downloads page...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-IE,en;q=0.9",
    }
    session = requests.Session()
    session.headers.update(headers)
    res = session.get(DOWNLOADS_PAGE, timeout=30)
    res.raise_for_status()
    print("  Page fetched:", len(res.content), "bytes")

    soup = BeautifulSoup(res.text, "html.parser")

    vs  = soup.find("input", {"id": "__VIEWSTATE"})
    vsg = soup.find("input", {"id": "__VIEWSTATEGENERATOR"})
    ev  = soup.find("input", {"id": "__EVENTVALIDATION"})

    if not vs or not vsg or not ev:
        print("  WARNING: ASP.NET form fields not found - page content:")
        print(res.text[:2000])
        raise RuntimeError("Could not find ASP.NET form fields")

    payload = {
        "__EVENTTARGET":        "",
        "__EVENTARGUMENT":      "",
        "__VIEWSTATE":          vs["value"],
        "__VIEWSTATEGENERATOR": vsg["value"],
        "__EVENTVALIDATION":    ev["value"],
    }

    for link in soup.find_all("a", href=True):
        if TARGET_TEXT in link.text:
            match = re.search(r"'(.*?)'", link["href"])
            if match:
                payload["__EVENTTARGET"] = match.group(1)
                print("  Found download link:", match.group(1))
                break

    if not payload["__EVENTTARGET"]:
        raise RuntimeError("Could not find UCITS register download link on page")

    print("  Downloading PDF...")
    pdf_res = session.post(DOWNLOADS_PAGE, data=payload, timeout=120)
    pdf_res.raise_for_status()
    print("  Downloaded:", round(len(pdf_res.content) / 1024), "KB")

    if len(pdf_res.content) < 10000:
        print("  ERROR - got back:", pdf_res.text[:1000])
        raise RuntimeError("Response too small — not a PDF")

    return pdf_res.content

# ── PDF parsing ───────────────────────────────────────────────────────────────
def parse_pdf(pdf_bytes):
    """
    Extract structured data from the CBI register PDF.
    The PDF has a table with columns: Fund Name | ManCo | Depositary | Auth Date
    Returns a list of dicts.
    """
    print("Parsing PDF...")
    records = []
    date_pattern = re.compile(
        r"\b(\d{1,2}[- ](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[- ]\d{2,4})\b"
    )

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        print("  Pages:", len(pdf.pages))

        for page_num, page in enumerate(pdf.pages):
            # Try structured table extraction first
            tables = page.extract_tables()

            if tables:
                for table in tables:
                    for row in table:
                        if not row or not any(row):
                            continue
                        cells = [str(c).strip().replace("\n", " ") if c else "" for c in row]

                        # Skip header rows
                        if any(h in cells[0].lower() for h in ["fund name", "name of fund", "ucits"]):
                            continue

                        # Look for a date in any cell
                        date_str = ""
                        date_col = -1
                        for i, cell in enumerate(cells):
                            m = date_pattern.search(cell)
                            if m:
                                date_str = m.group(1)
                                date_col = i
                                break

                        if not date_str:
                            continue

                        fund_name  = cells[0] if len(cells) > 0 else ""
                        manco      = cells[1] if len(cells) > 1 else ""
                        depositary = cells[2] if len(cells) > 2 else ""

                        # If date ended up in col 1 or 2, shift accordingly
                        if date_col == 1:
                            manco      = ""
                            depositary = ""
                        elif date_col == 2:
                            depositary = ""

                        if fund_name and len(fund_name) > 3:
                            records.append({
                                "Fund Name":  fund_name,
                                "ManCo":      manco,
                                "Depositary": depositary,
                                "Auth_Date":  standardize_date(date_str),
                                "First_Seen": TODAY,
                            })

            else:
                # Fallback: raw text parsing
                text = page.extract_text() or ""
                for line in text.split("\n"):
                    m = date_pattern.search(line)
                    if m:
                        fund_name = line[:m.start()].strip().rstrip(",").strip()
                        if len(fund_name) > 3:
                            records.append({
                                "Fund Name":  fund_name,
                                "ManCo":      "",
                                "Depositary": "",
                                "Auth_Date":  standardize_date(m.group(1)),
                                "First_Seen": TODAY,
                            })

    print("  Extracted", len(records), "records")

    # Deduplicate by Fund Name, keeping first occurrence
    seen = set()
    deduped = []
    for r in records:
        if r["Fund Name"] not in seen:
            seen.add(r["Fund Name"])
            deduped.append(r)
    print("  After dedup:", len(deduped), "records")
    return deduped

# ── Save CSV ──────────────────────────────────────────────────────────────────
def save_csv(records):
    df = pd.DataFrame(records, columns=["Fund Name", "ManCo", "Depositary", "Auth_Date", "First_Seen"])
    df["Auth_Date_DT"] = pd.to_datetime(df["Auth_Date"], errors="coerce")
    df = df.sort_values("Auth_Date_DT", ascending=False).drop(columns=["Auth_Date_DT"])
    os.makedirs("data", exist_ok=True)
    df.to_csv(DB_FILE, index=False)
    print("Saved", len(df), "records to", DB_FILE)

    # Print sample
    etf_count = df["Fund Name"].str.contains("ETF", case=False, na=False).sum()
    print("ETFs in register:", etf_count)
    print("\nSample (first 5 rows with ManCo populated):")
    sample = df[df["ManCo"] != ""].head(5)
    print(sample[["Fund Name", "ManCo", "Depositary", "Auth_Date"]].to_string(index=False))
    return df

# ── GitHub push ───────────────────────────────────────────────────────────────
def push_to_github(filepath, content_bytes, commit_msg):
    if not GITHUB_TOKEN:
        print("  No GITHUB_TOKEN set — skipping GitHub push for", filepath)
        return

    api_url = "https://api.github.com/repos/" + GITHUB_REPO + "/contents/" + filepath
    headers = {
        "Authorization": "token " + GITHUB_TOKEN,
        "Accept": "application/vnd.github.v3+json",
    }

    # Get current SHA if file exists
    sha = None
    r = requests.get(api_url, headers=headers)
    if r.status_code == 200:
        sha = r.json().get("sha")

    payload = {
        "message": commit_msg,
        "content": base64.b64encode(content_bytes).decode("utf-8"),
    }
    if sha:
        payload["sha"] = sha

    r = requests.put(api_url, headers=headers, data=json.dumps(payload))
    if r.status_code in (200, 201):
        print("  Pushed:", filepath)
    else:
        print("  ERROR pushing", filepath, r.status_code, r.text[:200])

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    # 1. Download PDF
    pdf_bytes = download_pdf()

    # 2. Parse
    records = parse_pdf(pdf_bytes)

    # 3. Save locally
    df = save_csv(records)

    # 4. Push CSV to GitHub
    print("\nPushing to GitHub...")
    with open(DB_FILE, "rb") as f:
        push_to_github(
            "data/cbi_shadow_db.csv",
            f.read(),
            "chore: full resync " + TODAY + " (" + str(len(df)) + " funds)"
        )

    print("\nDone. Run generate_dashboard.py next to rebuild the dashboard.")

if __name__ == "__main__":
    main()
