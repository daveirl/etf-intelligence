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
    print(f"  GET status: {res.status_code}")
    print(f"  Content-Type: {res.headers.get('Content-Type', '
