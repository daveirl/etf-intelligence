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
    for fmt in ("%d %b %Y", "%d-%b-%y", "%d %B %Y"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return date_str

def run_sync():
    if os.path.exists(DB_FILE):
        shadow_df = pd.read_csv(DB_FILE)
    else:
        shadow_df = pd.DataFrame(columns=["Fund Name", "Auth_Date", "First_Seen"])

    print("Step 1: Fetching downloads page...")
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    res = session.get(DOWNLOADS_PAGE, timeout=30)
    print("  GET status: " + str(res.status_code))
    print("  Content-Type: " + res.headers.get("Content-Type", "?"))
    print("  Size: " + str(len(res.content)) + " bytes")

    soup = BeautifulSoup(res.text, "html.parser")

    vs  = soup.find("input", {"id": "__VIEWSTATE"})
    vsg = soup.find("input", {"id": "__VIEWSTATEGENERATOR"})
    ev  = soup.find("input", {"id": "__EVENTVALIDATION"})
    print("  __VIEWSTATE found: " + str(vs is not None))
    print("  __VIEWSTATEGENERATOR found: " + str(vsg is not None))
    print("  __EVENTVALIDATION found: " + str(ev is not None))

    if not vs or not vsg or not ev:
        print("ERROR: ASP.NET form fields missing. Page snippet:")
        print(res.text[:3000])
        raise RuntimeError("ASP.NET form fields not found")

    payload = {
        "__EVENTTARGET": "",
        "__EVENTARGUMENT": "",
        "__VIEWSTATE": vs["value"],
        "__VIEWSTATEGENERATOR": vsg["value"],
        "__EVENTVALIDATION": ev["value"]
    }

    print("Step 2: Looking for UCITS register link...")
    found_link = False
    for link in soup.find_all("a", href=True):
        if TARGET_TEXT in link.text:
            match = re.search(r"'(.*?)'", link["href"])
            if match:
                payload["__EVENTTARGET"] = match.group(1)
                print("  Found it — __EVENTTARGET = " + match.group(1))
                found_link = True
                break

    if not found_link:
        print("WARNING: Target link not found. All links on page:")
        for link in soup.find_all("a", href=True)[:30]:
            print("  [" + link.text.strip()[:80] + "] -> " + link["href"][:80])
        raise RuntimeError("Target link not found")

    print("Step 3: POSTing to download PDF...")
    pdf_res = session.post(DOWNLOADS_PAGE, data=payload, timeout=60)
    print("  POST status: " + str(pdf_res.status_code))
    print("  Content-Type: " + pdf_res.headers.get("Content-Type", "?"))
    print("  Size: " + str(len(pdf_res.content)) + " bytes (" + str(round(len(pdf_res.content)/1024, 1)) + " KB)")
    print("  First bytes: " + str(pdf_res.content[:20]))

    if len(pdf_res.content) < 10000:
        print("ERROR: Too small to be a PDF. Full response:")
        print(pdf_res.text[:3000])
        raise RuntimeError("Got HTML instead of PDF")

    print("Step 4: Parsing PDF...")
    new_found = []
    date_pattern = re.compile(r"(\d{1,2}[- ](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[- ]\d{2,4})")

    with pdfplumber.open(io.BytesIO(pdf_res.content)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                for line in text.split("\n"):
                    match = date_pattern.search(line)
                    if match:
                        name = re.sub(r"\s+", " ", line[:match.start()]).strip()
                        if name and name not in shadow_df["Fund Name"].values:
                            new_found.append({
                                "Fund Name": name,
                                "Auth_Date": standardize_date(match.group(0).strip()),
                                "First_Seen": datetime.now().strftime("%Y-%m-%d")
                            })

    if new_found:
        shadow_df = pd.concat([shadow_df, pd.DataFrame(new_found)], ignore_index=True)

    shadow_df["Auth_Date_DT"] = pd.to_datetime(shadow_df["Auth_Date"], errors="coerce")
    shadow_df = shadow_df.sort_values(by="Auth_Date_DT", ascending=False).drop(columns=["Auth_Date_DT"])
    os.makedirs("data", exist_ok=True)
    shadow_df.to_csv(DB_FILE, index=False)
    print("Done — " + str(len(new_found)) + " new, " + str(len(shadow_df)) + " total")

if __name__ == "__main__":
    run_sync()
