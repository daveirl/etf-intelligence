#!/usr/bin/env python3
"""
cbi_shadow_sync_v2.py
---------------------
Downloads the CBI UCITS register PDF, parses fund names and auth dates,
and upserts into cbi_shadow_db.csv (adding First_Seen date on new entries).

Also downloads the ICAV register PDF and maintains icav_register.csv.

Run manually or via GitHub Actions on a schedule.
"""

import io, re, os, csv, hashlib, requests, pdfplumber
from datetime import date
from bs4 import BeautifulSoup

DOWNLOADS_PAGE = "https://registers.centralbank.ie/DownloadsPage.aspx"

UCITS_TARGET = (
    "Authorised UCITS, European Communities (Undertakings for Collective "
    "Investment in Transferable Securities) Regulations 2011"
)
ICAV_TARGET = "Register of Registered Irish Collective Asset-management Vehicles"

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
UCITS_CSV = os.path.join(DATA_DIR, "cbi_shadow_db.csv")
ICAV_CSV  = os.path.join(DATA_DIR, "icav_register.csv")
META_FILE = os.path.join(DATA_DIR, ".last_seen_hashes")

ICAV_DATE_RE = re.compile(
    r"\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+\d{4}\b", re.IGNORECASE)
CRO_RE   = re.compile(r"\bC\d{4,7}\b")
PREV_RE  = re.compile(r"\((previously|converted from|prev)\s+(.+?)\)", re.IGNORECASE)
UCITS_DATE_RE = re.compile(
    r"\b(\d{1,2}[\s\-](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
    r"[\s\-]\d{4}|\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})\b", re.IGNORECASE)


# ── helpers ──────────────────────────────────────────────────────────────────

def get_session():
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0 (ETF Intelligence Sync)"})
    return s

def fetch_downloads_page(session):
    res = session.get(DOWNLOADS_PAGE, timeout=20)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")
    hidden = {t["name"]: t.get("value", "") for t in soup.find_all("input", type="hidden")}
    return soup, hidden

def find_eventtarget(soup, label_text):
    for link in soup.find_all("a", href=True):
        if label_text in link.get_text():
            m = re.search(r"'(.*?)'", link["href"])
            if m:
                return m.group(1)
    raise ValueError(f"Could not find download link: {label_text!r}")

def download_pdf(session, soup, hidden, label_text):
    et = find_eventtarget(soup, label_text)
    payload = dict(hidden)
    payload.update({"__EVENTTARGET": et, "__EVENTARGUMENT": ""})
    res = session.post(DOWNLOADS_PAGE, data=payload, timeout=60)
    res.raise_for_status()
    if b"%PDF" not in res.content[:8]:
        raise RuntimeError(f"Response for '{label_text}' is not a PDF")
    return res.content

def pdf_hash(b): return hashlib.md5(b).hexdigest()

def load_hashes():
    if not os.path.exists(META_FILE): return {}
    with open(META_FILE) as f:
        return dict(l.strip().split("=", 1) for l in f if "=" in l)

def save_hashes(hashes):
    with open(META_FILE, "w") as f:
        [f.write(f"{k}={v}\n") for k, v in hashes.items()]


# ── UCITS ────────────────────────────────────────────────────────────────────

def parse_ucits_pdf(pdf_bytes):
    records, current_platform = [], ""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            rows = page.extract_table()
            if not rows: continue
            for row in rows:
                if not row: continue
                cells = [c.strip() if c else "" for c in row]
                if not any(UCITS_DATE_RE.search(c) for c in cells):
                    if any(k in " ".join(cells) for k in ["plc","ICAV","S.A.","SICAV","Fund"]):
                        current_platform = cells[0] or current_platform
                    continue
                fund_name = cells[0]
                auth_date = next((UCITS_DATE_RE.search(c).group(0) for c in cells[1:] if UCITS_DATE_RE.search(c)), "")
                if fund_name and auth_date:
                    records.append({"Fund_Name": fund_name, "Auth_Date": auth_date, "Platform": current_platform})
    return records

def upsert_ucits(records):
    today = date.today().isoformat()
    existing = {}
    if os.path.exists(UCITS_CSV):
        with open(UCITS_CSV, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                existing[row["Fund_Name"]] = row
    new_count = 0
    for rec in records:
        name = rec["Fund_Name"]
        if name not in existing:
            existing[name] = {"Fund_Name": name, "Auth_Date": rec["Auth_Date"],
                              "Platform": rec.get("Platform",""), "First_Seen": today}
            new_count += 1
        elif rec.get("Platform") and not existing[name].get("Platform"):
            existing[name]["Platform"] = rec["Platform"]
    rows = sorted(existing.values(), key=lambda r: r.get("Auth_Date",""))
    with open(UCITS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["Fund_Name","Auth_Date","Platform","First_Seen"])
        w.writeheader(); w.writerows(rows)
    print(f"UCITS: {len(rows)} total, {new_count} new.")
    return new_count


# ── ICAV ─────────────────────────────────────────────────────────────────────

def _build_icav_record(name_raw, date_str, reg_office, cro_source):
    in_liq = bool(re.search(r"in\s+liquidation", name_raw, re.IGNORECASE))
    prev_names = [m.group(2).strip() for m in PREV_RE.finditer(name_raw)]
    clean_name = re.sub(r"\s{2,}", " ", re.sub(r"\(.*?\)", "", name_raw)).strip()
    cro_m = CRO_RE.search(cro_source)
    office = re.sub(r"\s+", " ", reg_office).strip()
    city = next((c for c in ("Dublin","Cork","Limerick","Galway","Wicklow") if c in office), "")
    return {
        "ICAV_Name":            clean_name,
        "Date_of_Registration": date_str.strip(),
        "Registered_Office":    office,
        "City":                 city,
        "CRO_Number":           cro_m.group(0) if cro_m else "",
        "In_Liquidation":       "Yes" if in_liq else "No",
        "Previous_Names":       " | ".join(prev_names),
    }

def parse_icav_pdf(pdf_bytes):
    """
    Parse the ICAV register PDF.

    Table columns:
      [0] ICAV Name
      [1] Date of Registration   (DD Month YYYY)
      [2] Registered Office
      [3] Head Office (if different)
      [4] Related Documents      (contains CRO number e.g. C139365)
    """
    records = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            if tables:
                for table in tables:
                    for row in table:
                        if not row or len(row) < 2: continue
                        cells = [c.strip() if c else "" for c in row]
                        if not cells[0] or any(skip in cells[0] for skip in
                           ("ICAV Name", "Under the powers", "Central Bank",
                            "Accurate as at", "Page ")):
                            continue
                        date_str = cells[1] if len(cells) > 1 else ""
                        if not ICAV_DATE_RE.search(date_str): continue
                        reg_off  = cells[2] if len(cells) > 2 else ""
                        cro_src  = cells[4] if len(cells) > 4 else (
                                   cells[3] if len(cells) > 3 else "")
                        records.append(_build_icav_record(cells[0], date_str, reg_off, cro_src))
            else:
                _parse_icav_text_fallback(page.extract_text() or "", records)

    # Deduplicate by CRO number
    seen, deduped = set(), []
    for r in records:
        key = r["CRO_Number"] or r["ICAV_Name"]
        if key not in seen:
            seen.add(key); deduped.append(r)
    return deduped

def _parse_icav_text_fallback(text, records):
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for i, line in enumerate(lines):
        dm = ICAV_DATE_RE.search(line)
        if not dm or i == 0: continue
        name_raw = lines[i-1]
        if not name_raw or any(s in name_raw for s in ("Central Bank","Under the powers","ICAV Name")): continue
        date_str = dm.group(0)
        office_parts, cro_src = [], ""
        j = i + 1
        while j < len(lines) and j < i + 10:
            if ICAV_DATE_RE.search(lines[j]): break
            cm = CRO_RE.search(lines[j])
            if cm: cro_src = cm.group(0); break
            office_parts.append(lines[j]); j += 1
        records.append(_build_icav_record(name_raw, date_str, " ".join(office_parts), cro_src))

def upsert_icav(records):
    today = date.today().isoformat()
    FIELDS = ["ICAV_Name","Date_of_Registration","Registered_Office",
              "City","CRO_Number","In_Liquidation","Previous_Names","First_Seen"]
    existing = {}
    if os.path.exists(ICAV_CSV):
        with open(ICAV_CSV, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                existing[row.get("CRO_Number") or row["ICAV_Name"]] = row
    new_count = 0
    for rec in records:
        key = rec["CRO_Number"] or rec["ICAV_Name"]
        if key not in existing:
            rec["First_Seen"] = today; existing[key] = rec; new_count += 1
        else:
            for fld in ["ICAV_Name","Previous_Names","In_Liquidation"]:
                if rec.get(fld): existing[key][fld] = rec[fld]
    rows = sorted(existing.values(), key=lambda r: r.get("Date_of_Registration",""))
    with open(ICAV_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)
    print(f"ICAV: {len(rows)} total, {new_count} new.")
    return new_count


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    session = get_session()
    hashes  = load_hashes()
    changed = False

    print("Fetching CBI downloads page...")
    try:
        soup, hidden = fetch_downloads_page(session)
    except Exception as e:
        print(f"ERROR fetching downloads page: {e}"); return

    for label, parse_fn, upsert_fn, key in [
        (UCITS_TARGET, parse_ucits_pdf, upsert_ucits, "ucits"),
        (ICAV_TARGET,  parse_icav_pdf,  upsert_icav,  "icav"),
    ]:
        short = key.upper()
        print(f"Downloading {short} register PDF...")
        try:
            pdf_bytes = download_pdf(session, soup, hidden, label)
            h = pdf_hash(pdf_bytes)
            if hashes.get(key) != h:
                print(f"{short} PDF changed — parsing...")
                upsert_fn(parse_fn(pdf_bytes))
                hashes[key] = h; changed = True
            else:
                print(f"{short} PDF unchanged — skipping.")
        except Exception as e:
            print(f"ERROR on {short} register: {e}")

    if changed:
        save_hashes(hashes)
    print("Done.")

if __name__ == "__main__":
    main()
