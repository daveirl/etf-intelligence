"""
icav_sync.py
============
Downloads the CBI ICAV register PDF via ASP.NET session POST,
parses all ICAV records, and merges into data/icav_db.csv.

Output CSV columns:
    ICAV Name       — registered name
    Reg Date        — registration date (YYYY-MM-DD)
    Reg Number      — CBI registration number (C######)
    In Liquidation  — "Yes" if name contains "(in Liquidation)"
    ETF Related     — "Yes" if name contains "ETF"
    First_Seen      — date first captured by this script
"""

import io
import os
import re
import sys
import logging
from datetime import date, datetime
from pathlib import Path

import requests
import pdfplumber
import pandas as pd
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%Y-%m-%d")
log = logging.getLogger(__name__)

SCRIPT_DIR     = Path(__file__).parent
REPO_ROOT      = SCRIPT_DIR.parent
CSV_PATH       = REPO_ROOT / "data" / "icav_db.csv"
DOWNLOADS_PAGE = "https://registers.centralbank.ie/DownloadsPage.aspx"
TARGET_TEXT    = "Register of Registered Irish Collective Asset-management Vehicles"

DATE_RE    = re.compile(
    r"\b(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+\d{4})\b"
)
REG_NUM_RE = re.compile(r"\b(C\d{4,7})\b")
SKIP_RE    = re.compile(r"Accurate as at|ICAVs\)|Central Bank|ICAV Name|Registration", re.I)


def download_pdf() -> io.BytesIO:
    log.info("Downloading ICAV register PDF …")
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; ETF-Intelligence/2)"})

    res = session.get(DOWNLOADS_PAGE, timeout=20)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")

    def _val(id_):
        tag = soup.find("input", {"id": id_})
        return tag["value"] if tag else ""

    payload = {
        "__EVENTTARGET":        "",
        "__EVENTARGUMENT":      "",
        "__VIEWSTATE":          _val("__VIEWSTATE"),
        "__VIEWSTATEGENERATOR": _val("__VIEWSTATEGENERATOR"),
        "__EVENTVALIDATION":    _val("__EVENTVALIDATION"),
    }

    for link in soup.find_all("a", href=True):
        if TARGET_TEXT.lower() in link.get_text().lower():
            m = re.search(r"'(.*?)'", link["href"])
            if m:
                payload["__EVENTTARGET"] = m.group(1)
                log.info(f"  Found ICAV link: __EVENTTARGET = {m.group(1)}")
                break

    if not payload["__EVENTTARGET"]:
        raise RuntimeError("Could not find ICAV register link on CBI downloads page")

    pdf_res = session.post(DOWNLOADS_PAGE, data=payload, timeout=60)
    pdf_res.raise_for_status()

    content_type = pdf_res.headers.get("Content-Type", "")
    if "pdf" not in content_type.lower() and len(pdf_res.content) < 50_000:
        raise RuntimeError(
            f"Expected PDF but got {len(pdf_res.content)} bytes "
            f"(Content-Type: {content_type!r}). "
            "CBI may be blocking the runner IP — try running locally."
        )

    log.info(f"  Downloaded {len(pdf_res.content) / 1024:.0f} KB")
    return io.BytesIO(pdf_res.content)


def parse_pdf(pdf_bytes: io.BytesIO) -> list[dict]:
    records = []
    seen    = set()

    with pdfplumber.open(pdf_bytes) as pdf:
        log.info(f"  Parsing {len(pdf.pages)} pages …")
        for page in pdf.pages:
            words = page.extract_words(x_tolerance=3, y_tolerance=3)
            if not words:
                continue

            lines: dict[float, list] = {}
            for w in words:
                lines.setdefault(round(w["top"], 0), []).append(w)

            for y in sorted(lines):
                line_words = sorted(lines[y], key=lambda w: w["x0"])
                line_text  = " ".join(w["text"] for w in line_words)

                if SKIP_RE.search(line_text):
                    continue

                m_date = DATE_RE.search(line_text)
                if not m_date:
                    continue

                m_reg   = REG_NUM_RE.search(line_text)
                reg_num = m_reg.group(1) if m_reg else ""

                name = line_text[:m_date.start()].strip()
                if not name or len(name) < 5:
                    continue

                key = name.lower()
                if key in seen:
                    continue
                seen.add(key)

                date_raw = m_date.group(1)
                try:
                    reg_date = datetime.strptime(date_raw, "%d %B %Y").strftime("%Y-%m-%d")
                except ValueError:
                    reg_date = date_raw

                in_liq   = "Yes" if re.search(r"\(in liquidation\)", name, re.I) else ""
                etf_rel  = "Yes" if re.search(r"\bETF\b", name, re.I) else ""

                records.append({
                    "ICAV Name":      name,
                    "Reg Date":       reg_date,
                    "Reg Number":     reg_num,
                    "In Liquidation": in_liq,
                    "ETF Related":    etf_rel,
                })

    log.info(f"  Extracted {len(records)} ICAV records")
    return records


def merge_csv(new_records: list[dict]) -> pd.DataFrame:
    today = date.today().isoformat()

    if CSV_PATH.exists():
        existing = pd.read_csv(CSV_PATH, dtype=str).fillna("")
        first_seen_map = dict(zip(existing["ICAV Name"], existing.get("First_Seen", "")))
    else:
        first_seen_map = {}

    for r in new_records:
        r["First_Seen"] = first_seen_map.get(r["ICAV Name"]) or today

    df = pd.DataFrame(new_records, columns=[
        "ICAV Name", "Reg Date", "Reg Number", "In Liquidation", "ETF Related", "First_Seen"
    ])
    df = df.sort_values("Reg Date").reset_index(drop=True)

    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(CSV_PATH, index=False)
    log.info(f"  Saved {len(df)} records to {CSV_PATH}")
    return df


def run_sync():
    pdf_bytes = download_pdf()
    records   = parse_pdf(pdf_bytes)
    if not records:
        log.error("No ICAV records extracted — check PDF format")
        sys.exit(1)
    merge_csv(records)
    log.info("ICAV sync complete.")


if __name__ == "__main__":
    run_sync()
