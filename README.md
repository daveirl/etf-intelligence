# ETF Intelligence — CBI Register Tracker

A self-updating dashboard that tracks fund registrations on the [Central Bank of Ireland](https://registers.centralbank.ie/) registers, plus live LEI lookup against the [GLEIF database](https://api.gleif.org).

Runs automatically every Friday via GitHub Actions — downloads the CBI register PDFs, extracts fund data, rebuilds the shadow databases, and publishes a live dashboard to GitHub Pages.

## Live Dashboard

👉 **[daveirl.github.io/etf-intelligence](https://daveirl.github.io/etf-intelligence)**

Four tabs:

- **CBI Fund Register** — every UCITS authorisation in the CBI register (~6,500 funds). Search and filter by name, management company, depositary, and date. ETF-only view with 30/90-day and YTD new-registration counts, top-ManCo and depositary market-share charts, and a stacked-bar chart of authorisations by year split ETF vs non-ETF. CSV export respects active filters.
- **CBI AIF Register** — every ICAV-form Alternative Investment Fund (CBI ICAV Act 2015 register, ~2,400 funds). Same UX as the Fund Register tab.
- **CBI ICAV Register** — every Irish Collective Asset-management Vehicle (the corporate vehicle, not its sub-funds). Each row shows a sub-fund count joined from both the UCITS and AIF registers; the *No sub-funds yet* filter surfaces freshly incorporated ICAVs that haven't yet had any fund authorised — an early signal of incoming launches.
- **LEI Lookup** — live data from the GLEIF API. Auto-loads the most recently registered UCITS-ETF LEIs across all jurisdictions (Ireland, Luxembourg, Germany, France, …), paginated 10 per page, including PENDING_VALIDATION / PENDING_TRANSFER records. Search by fund name, ManCo, or LEI code; CBI-register cross-reference shown when a match exists.

## Repository Structure

```
etf-intelligence/
├── .github/
│   └── workflows/
│       └── weeklysync.yml         # GitHub Actions — runs every Friday at 07:00 UTC
├── data/
│   ├── cbi_shadow_db.csv          # UCITS register (auto-updated)
│   ├── aif_db.csv                 # ICAV-form AIF register (auto-updated)
│   └── icav_db.csv                # ICAV register — corporate vehicles (auto-updated)
├── docs/
│   ├── index.html                 # Dashboard (served by GitHub Pages)
│   └── .nojekyll                  # Disables Jekyll so Pages serves HTML directly
├── scripts/
│   ├── cbi_shadow_sync_v2.py      # Downloads + parses a CBI register PDF (parametric)
│   ├── cbi_aif_sync.py            # Thin wrapper for the ICAV-form AIF register
│   ├── icav_sync.py               # ICAV register sync (different PDF format)
│   └── generate_dashboard.py      # Reads CSVs, writes docs/index.html
├── .gitignore
└── README.md
```

## How It Works

1. **`cbi_shadow_sync_v2.py`** — POSTs to the CBI ASP.NET downloads page to fetch the register PDF, runs `pdftotext -layout` to preserve column positions, and walks the output line by line. Umbrella rows (which carry a ManCo name in the column-1 position after the date) update `current_manco`, `current_trustee`, and `current_umbrella`; sub-fund rows beneath inherit those values until the next umbrella. Output schema: `Fund Name, Umbrella, ManCo, Depositary, Auth_Date, First_Seen`. Both `download_pdf()` and `run_sync()` accept `target_text` / `db_file` parameters so the same machinery handles different register PDFs.

2. **`cbi_aif_sync.py`** — thin wrapper that points `run_sync` at the ICAV-form AIF register and writes `data/aif_db.csv`. The PDF has the same column structure as UCITS, with an extra "Internally Managed" Yes/No flag and a separate Depositary column further along — handled by scanning for the last company-looking column past the ManCo.

3. **`icav_sync.py`** — fetches the ICAV register, which is a different PDF format (a list of corporate vehicles, not a list of funds). Uses `pdfplumber` and emits `data/icav_db.csv` with columns `ICAV Name, Reg Date, Reg Number, In Liquidation, ETF Related`.

4. **`generate_dashboard.py`** — reads all three CSVs and bakes everything into a self-contained `docs/index.html` with all data embedded as JSON. The ICAV tab's sub-fund count is computed by joining ICAV names against the `Umbrella` column of both the UCITS and AIF CSVs (case-insensitive exact match, with `(in Liquidation)` suffixes stripped).

5. **`weeklysync.yml`** — runs all three syncs every Friday morning, regenerates the dashboard, and pushes back to `main`. The push step rebases onto any concurrent merges with up to three retries.

## Setup

### 1. Enable GitHub Pages
**Settings → Pages**: source `Deploy from a branch`, branch `main`, folder `/docs`.

### 2. Run Manually
**Actions → ETF Intelligence — Weekly Sync → Run workflow** triggers a sync outside the Friday schedule.

## Local Development

```bash
pip install requests beautifulsoup4 pdfplumber pandas
sudo apt-get install poppler-utils    # for pdftotext

python scripts/cbi_shadow_sync_v2.py   # writes data/cbi_shadow_db.csv
python scripts/cbi_aif_sync.py         # writes data/aif_db.csv
python scripts/icav_sync.py            # writes data/icav_db.csv
python scripts/generate_dashboard.py   # regenerates docs/index.html
```

Open `docs/index.html` in your browser to preview locally.

## Notes

- Parsing the CBI register PDFs depends on the column layout that `pdftotext -layout` produces. If the CBI changes the PDF format, the heuristic in `parse_pdf_text()` (umbrella detection via `looks_like_company` on the first column after the date) is the place to adjust.
- The dashboard is entirely static — no server, no API key.
- The LEI tab queries the GLEIF API directly from the browser.
- The CBI site blocks requests from some cloud IP ranges. If `download_pdf()` starts returning a 6 KB HTML page instead of a PDF, the ASP.NET session POST may need updating.
- Company-vs-address detection uses a corporate-suffix shortlist (`Limited`, `Ltd`, `Plc`, `S.A.`, `S.à r.l.`, `GmbH`, `LLP`, `LLC`, `DAC`, `SE`, `(Dublin) Branch`, etc.) plus a keyword fallback. Edge cases already handled: Irish ManCos containing the word "Ireland" (e.g. *BlackRock Asset Management Ireland Limited*), trustee names containing "Trustees" (e.g. *SMT Trustees (Ireland) Limited*), foreign-bank Dublin branches (e.g. *J.P. Morgan SE Dublin Branch*), and IFSC addresses being misread as ManCos.

## Roadmap

### Near-term

**Daily CBI change detection**
Instead of running the full sync every Friday regardless, check the CBI downloads page daily and only trigger the full parse if a register PDF has actually been updated (compare file size or last-modified header against the previous run). Catches mid-week registrations and avoids unnecessary runs. Implementation: a lightweight daily workflow that stores the last-seen PDF size in a repo file and only proceeds if it changes.

**Other AIF registers (Plc / Unit Trust / CCF / ILP)**
The CBI publishes five AIF registers; only ICAV-form is currently parsed. The Plc-form (Designated Investment Companies, Companies Act 1990 Part XIII), Unit Trust schemes (UT Act 1990), Common Contractual Funds (IFCMP Act 2005), and Investment Limited Partnerships (ILP Act 1994) cover the remaining non-ICAV AIF universe. Each would be a separate `cbi_*_sync.py` wrapper around the same `run_sync` helper, modulo a likely format tweak per PDF.

### Medium-term

**Luxembourg ETF register**
The CSSF (Commission de Surveillance du Secteur Financier) publishes a register of Luxembourg-domiciled UCITS. LU is the second-largest ETF domicile in Europe after Ireland, covering major Amundi, DWS, and Franklin Templeton ranges. Adding a `cssf_sync.py` script alongside the CBI syncs would give a more complete picture of the European ETF landscape.

### Also planned

**New ETF alert emails**
Trigger a notification when new ETFs appear in the register, using the existing `First_Seen` date to detect them. The daily change detection workflow (above) would handle the triggering logic — if new ETFs are found in a sync run, send a summary email via SendGrid.

**AuM data enrichment**
Cross-reference fund names against a public AuM source (e.g. justETF or ETFdb) to add size context to each fund in the register. Would allow filtering and sorting by AuM, and surface the largest new launches rather than treating all new registrations equally.

**SEC filings (EDGAR)**
The SEC's EDGAR system is publicly accessible via API and covers N-1A (ETF registration statements), 485BPOS (post-effective amendments), and 497 (prospectus) filings. While SEC-registered funds are US-domiciled and out of scope for the CBI register, cross-referencing is useful for two reasons:

1. **US issuers launching Irish UCITS mirrors** — when BlackRock, Invesco, or State Street file a new N-1A for a US ETF, an Irish UCITS equivalent often follows within 6–18 months. Tracking SEC filings gives early visibility of the product pipeline before it shows up in the CBI register.
2. **ManCo and sub-adviser relationships** — SEC filings disclose the full adviser/sub-adviser chain in detail, which can be used to enrich the ManCo data for funds where the CBI register only shows the Irish management company.

Implementation: a `sec_sync.py` script that polls the EDGAR full-text search API for new N-1A and 485BPOS filings from known Irish-ETF issuers, stores results in `data/sec_filings.csv`, and surfaces them in a new dashboard tab.
