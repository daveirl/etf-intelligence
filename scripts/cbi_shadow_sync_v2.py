"""
cbi_shadow_sync_v2.py
─────────────────────
Downloads the CBI UCITS register PDF, extracts fund data including
Platform/ICAV umbrella headers, Management Company, and Depositary columns,
then updates data/cbi_shadow_db.csv.


Usage:
    python scripts/cbi_shadow_sync_v2.py
"""

import re
import os
import csv
import json
import requests
import pdfplumber
from datetime import datetime, date
from io import BytesIO

# ── Config ────────────────────────────────────────────────────────────────────
CBI_PDF_URL = "https://registers.centralbank.ie/DownloadsListPage?reg=6"
DATA_DIR    = os.path.join(os.path.dirname(__file__), '..', 'data')
CSV_PATH    = os.path.join(DATA_DIR, 'cbi_shadow_db.csv')
TODAY       = date.today().isoformat()

# ── Platform / ManCo / Depositary lookup ─────────────────────────────────────
# Fallback enrichment when column parsing is ambiguous.
PLATFORM_MAP = [
    (['iShares'],         'BlackRock UCITS ETF ICAV / iShares plc',        'BlackRock Asset Management Ireland Limited',          'State Street Custodial Services (Ireland) Limited'),
    (['Xtrackers'],       'Xtrackers (IE) plc / DWS Xtrackers ICAV',       'DWS Investment S.A.',                                 'State Street Bank International GmbH'),
    (['Invesco'],         'Invesco Markets plc / Invesco Markets II plc',   'Invesco Investment Management Limited',               'The Bank of New York Mellon SA/NV'),
    (['SPDR'],            'SPDR ETFs Ireland plc',                          'State Street Global Advisors Europe Limited',         'State Street Custodial Services (Ireland) Limited'),
    (['Amundi'],          'Amundi UCITS ETF ICAV / Amundi Index Solutions', 'Amundi Asset Management',                             'CACEIS Bank, Ireland Branch'),
    (['Vanguard'],        'Vanguard Funds plc',                             'Vanguard Group (Ireland) Limited',                    'Brown Brothers Harriman Trustee Services (Ireland) Limited'),
    (['WisdomTree'],      'WisdomTree UCITS ICAV',                          'WisdomTree Management Limited',                       'Citi Depositary Services Ireland DAC'),
    (['VanEck'],          'VanEck UCITS ETFs plc',                          'VanEck Asset Management B.V.',                        'State Street Custodial Services (Ireland) Limited'),
    (['Franklin'],        'Franklin Templeton ETF ICAV',                    'Franklin Templeton International Services S.à r.l.', 'The Bank of New York Mellon SA/NV'),
    (['Goldman Sachs'],   'Goldman Sachs ETF UCITS ICAV',                   'Goldman Sachs Asset Management International',        'State Street Custodial Services (Ireland) Limited'),
    (['JPMorgan', 'J.P.'],'JPMorgan ETFs (Ireland) ICAV',                   'JPMorgan Asset Management (Europe) S.à r.l.',        'The Bank of New York Mellon SA/NV'),
    (['PIMCO'],           'PIMCO Fixed Income Source ETFs plc',             'PIMCO Europe GmbH',                                  'State Street Custodial Services (Ireland) Limited'),
    (['Fidelity'],        'Fidelity UCITS ICAV',                            'FIL Fund Management (Ireland) Limited',               'The Bank of New York Mellon SA/NV'),
    (['HANetf'],          'HANetf ICAV',                                    'HANetf Limited',                                     'The Bank of New York Mellon SA/NV'),
    (['Tabula'],          'Tabula ICAV',                                    'Tabula Investment Management Limited',                'The Bank of New York Mellon SA/NV'),
    (['L&G', 'Legal'],    'L&G UCITS ETF plc',                              'Legal & General UCITS ETF plc',                      'The Bank of New York Mellon SA/NV'),
    (['First Trust'],     'First Trust Global Funds plc',                   'First Trust Global Portfolios Limited',               'The Bank of New York Mellon SA/NV'),
    (['Ossiam'],          'Ossiam UCITS ICAV',                              'Ossiam',                                              'Société Générale S.A.'),
    (['HSBC'],            'HSBC ETFs plc',                                  'HSBC Global Asset Management (UK) Limited',           'The Bank of New York Mellon SA/NV'),
    (['UBS'],             'UBS ETF plc / UBS ETFs plc',                     'UBS Asset Management (UK) Ltd',                      'State Street Custodial Services (Ireland) Limited'),
    (['Lyxor'],           'Lyxor UCITS ETF plc',                            'Lyxor International Asset Management S.A.S.',         'State Street Custodial Services (Ireland) Limited'),
]


def enrich_from_name(name: str) -> tuple:
    """Return (platform, manco, depositary) based on fund name keywords."""
    for keywords, platform, manco, depositary in PLATFORM_MAP:
        if any(kw.lower() in name.lower() for kw in keywords):
            return platform, manco, depositary
    return 'Other', 'Unknown', 'Unknown'


def download_pdf() -> BytesIO:
    """Fetch the CBI UCITS register PDF. Returns a BytesIO object."""
    print(f"[{TODAY}] Downloading CBI register PDF …")
    # The CBI page redirects to the actual PDF download
    headers = {'User-Agent': 'Mozilla/5.0 (ETF Intelligence Bot)'}
    r = requests.get(CBI_PDF_URL, headers=headers, timeout=30, allow_redirects=True)
    r.raise_for_status()
    content_type = r.headers.get('Content-Type', '')
    if 'pdf' not in content_type and len(r.content) < 50_000:
        # Might be an HTML redirect page — try to find the actual PDF link
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, 'html.parser')
        for a in soup.find_all('a', href=True):
            if '.pdf' in a['href'].lower():
                pdf_url = a['href']
                if not pdf_url.startswith('http'):
                    pdf_url = 'https://registers.centralbank.ie' + pdf_url
                r = requests.get(pdf_url, headers=headers, timeout=60)
                r.raise_for_status()
                break
    print(f"  Downloaded {len(r.content)/1024:.0f} KB")
    return BytesIO(r.content)


def parse_pdf(pdf_bytes: BytesIO) -> list[dict]:
    """
    Extract fund records from the CBI register PDF.
    Returns a list of dicts with keys:
        Platform, Fund Name, ManCo, Depositary, Auth_Date
    """
    records = []
    current_platform = ''

    date_pattern = re.compile(r'\d{1,2}[/-]\w+[/-]\d{4}|\d{4}-\d{2}-\d{2}')

    with pdfplumber.open(pdf_bytes) as pdf:
        for page in pdf.pages:
            # Try structured table extraction first
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if not row or not any(row):
                        continue
                    cells = [str(c).strip() if c else '' for c in row]
                    # Detect umbrella/platform header rows (usually single non-empty cell)
                    non_empty = [c for c in cells if c]
                    if len(non_empty) == 1 and len(non_empty[0]) > 5:
                        candidate = non_empty[0]
                        if not date_pattern.search(candidate):
                            current_platform = candidate
                            continue
                    # Detect data rows — need at least a fund name and a date
                    fund_name = cells[0] if cells else ''
                    date_str  = ''
                    manco     = ''
                    depositary = ''
                    for cell in cells[1:]:
                        if date_pattern.search(cell):
                            date_str = date_pattern.search(cell).group()
                        elif 'management' in cell.lower() or 'asset' in cell.lower():
                            manco = cell
                        elif 'depositary' in cell.lower() or 'custodial' in cell.lower() or 'mellon' in cell.lower():
                            depositary = cell
                    if fund_name and date_str and len(fund_name) > 5:
                        if not manco or not depositary:
                            inferred_platform, inferred_manco, inferred_dep = enrich_from_name(fund_name)
                            manco      = manco or inferred_manco
                            depositary = depositary or inferred_dep
                            platform   = current_platform or inferred_platform
                        else:
                            platform = current_platform
                        records.append({
                            'Platform':   platform,
                            'Fund Name':  fund_name,
                            'ManCo':      manco,
                            'Depositary': depositary,
                            'Auth_Date':  normalise_date(date_str),
                        })

            # Fall back to raw text if no tables found on this page
            if not tables:
                text = page.extract_text() or ''
                for line in text.split('\n'):
                    line = line.strip()
                    if not line:
                        continue
                    m = date_pattern.search(line)
                    if m:
                        fund_name = line[:m.start()].strip().rstrip(',').strip()
                        if len(fund_name) > 5:
                            platform, manco, depositary = enrich_from_name(fund_name)
                            platform = current_platform or platform
                            records.append({
                                'Platform':   platform,
                                'Fund Name':  fund_name,
                                'ManCo':      manco,
                                'Depositary': depositary,
                                'Auth_Date':  normalise_date(m.group()),
                            })

    print(f"  Parsed {len(records)} fund records from PDF")
    return records


def normalise_date(raw: str) -> str:
    """Convert various date formats to YYYY-MM-DD."""
    for fmt in ('%d/%m/%Y', '%d-%m-%Y', '%d %B %Y', '%d-%B-%Y', '%Y-%m-%d',
                '%d/%m/%y', '%B %d, %Y', '%d %b %Y'):
        try:
            return datetime.strptime(raw.strip(), fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return raw  # Return as-is if nothing matches


def load_existing_db() -> dict:
    """Load the existing CSV into a dict keyed by Fund Name."""
    db = {}
    if not os.path.exists(CSV_PATH):
        return db
    with open(CSV_PATH, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            db[row['Fund Name']] = row
    return db


def merge_and_save(fresh: list[dict], existing: dict) -> tuple[list, list]:
    """
    Merge fresh PDF records with the existing DB.
    Returns (new_entries, updated_entries).
    """
    new_entries     = []
    updated_entries = []

    for rec in fresh:
        name = rec['Fund Name']
        if name not in existing:
            rec['First_Seen'] = TODAY
            existing[name]    = rec
            new_entries.append(rec)
        else:
            old = existing[name]
            changed = False
            for field in ('Platform', 'ManCo', 'Depositary', 'Auth_Date'):
                if rec.get(field) and rec[field] != old.get(field):
                    old[field] = rec[field]
                    changed    = True
            if changed:
                updated_entries.append(old)

    os.makedirs(DATA_DIR, exist_ok=True)
    fieldnames = ['Platform', 'Fund Name', 'ManCo', 'Depositary', 'Auth_Date', 'First_Seen']
    with open(CSV_PATH, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        w.writeheader()
        for row in sorted(existing.values(), key=lambda r: r.get('Auth_Date', ''), reverse=True):
            w.writerow(row)

    print(f"  DB updated — {len(new_entries)} new, {len(updated_entries)} updated, {len(existing)} total")
    return new_entries, updated_entries


def main():
    pdf_bytes = download_pdf()
    fresh     = parse_pdf(pdf_bytes)
    existing  = load_existing_db()
    new_e, upd_e = merge_and_save(fresh, existing)
    print("Done ✓")


if __name__ == '__main__':
    main()
