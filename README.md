# ETF Intelligence — CBI Register Tracker

A self-updating dashboard that tracks fund registrations on the [Central Bank of Ireland UCITS register](https://registers.centralbank.ie/).

Runs automatically every Friday via GitHub Actions — downloads the CBI register PDF, extracts fund data, rebuilds the shadow database, and publishes a live dashboard to GitHub Pages.

## Live Dashboard

👉 **[daveirl.github.io/etf-intelligence](https://daveirl.github.io/etf-intelligence)**

Features:
- Search and filter all 6,000+ CBI-registered funds by name, management company, depositary, and date
- ETF-only view with 30-day / 90-day / YTD new-registration counts
- Top management company and depositary market share charts
- CSV export (respects active filters)
- Live LEI lookup via the [GLEIF API](https://api.gleif.org) — EU/EEA entities only, with full entity detail cards and CBI register cross-referencing

## Repository Structure

```
etf-intelligence/
├── .github/
│   └── workflows/
│       └── weeklysync.yml         # GitHub Actions — runs every Friday at 07:00 UTC
├── data/
│   └── cbi_shadow_db.csv          # Shadow database (auto-updated by Actions)
├── docs/
│   ├── index.html                 # Dashboard (served by GitHub Pages)
│   └── .nojekyll                  # Disables Jekyll so GitHub Pages serves HTML directly
├── scripts/
│   ├── cbi_shadow_sync_v2.py      # Downloads + parses CBI PDF, updates CSV
│   └── generate_dashboard.py      # Reads CSV, writes docs/index.html
├── .gitignore
└── README.md
```

## How It Works

1. **`cbi_shadow_sync_v2.py`** uses a session POST to the CBI ASP.NET downloads page to fetch the register PDF. It then uses `pdfplumber` with word-level bounding boxes to detect the four columns in the PDF (Fund Name, Auth Date, ManCo, Trustee/Depositary). Umbrella fund lines carry the ManCo and Depositary; sub-funds inherit from the umbrella above them. Results are written to `data/cbi_shadow_db.csv`, preserving `First_Seen` dates for existing entries.

2. **`generate_dashboard.py`** reads the CSV and bakes everything into a self-contained `docs/index.html` with all data embedded as JSON — no server required.

3. **`weeklysync.yml`** runs both scripts every Friday morning, then commits the updated CSV and dashboard back to the repo. GitHub Pages picks up the new `index.html` automatically.

## Setup

### 1. Enable GitHub Pages
Go to **Settings → Pages** and set:
- Source: `Deploy from a branch`
- Branch: `main`
- Folder: `/docs`

The dashboard will be live at `https://daveirl.github.io/etf-intelligence` within a minute.

### 2. Run Manually
Go to **Actions → ETF Intelligence — Weekly Sync → Run workflow** to trigger a sync outside the Friday schedule.

## Local Development

```bash
pip install requests beautifulsoup4 pdfplumber pandas

# Run the full pipeline
python scripts/cbi_shadow_sync_v2.py    # Downloads PDF, updates data/cbi_shadow_db.csv
python scripts/generate_dashboard.py    # Regenerates docs/index.html
```

Open `docs/index.html` in your browser to preview the dashboard locally.

## Notes

- The CBI register PDF uses a fixed column layout — if parsing breaks after a CBI format change, check the `COL_DATE_START`, `COL_MANCO_START`, and `COL_TRUSTEE_START` constants in `cbi_shadow_sync_v2.py`.
- The dashboard is entirely static (no server needed).
- The LEI tab queries the GLEIF API directly from the browser — no API key required.
- The CBI site blocks requests from some cloud IP ranges. If the GitHub Actions runner starts returning a 6KB HTML page instead of the PDF, the ASP.NET session POST logic in `download_pdf()` may need updating.

## Roadmap

### Near-term

**Daily CBI change detection**
Instead of running the full sync every Friday regardless, check the CBI downloads page daily and only trigger the full parse if the PDF has actually been updated (compare file size or last-modified header against the previous run). This would catch mid-week registrations and avoid unnecessary runs. Implementation: add a lightweight daily workflow that stores the last-seen PDF size in a repo file and only proceeds if it changes.

**ICAV Register**
The CBI also publishes a separate register of Irish Collective Asset-management Vehicles (ICAVs) — the dominant legal wrapper for Irish-domiciled ETFs. Adding this would let us cross-reference every ETF sub-fund against its ICAV umbrella, confirm the ICAV registration date, and track new ICAV incorporations as an early signal of incoming fund launches. The register is available on the same CBI downloads page under "Register of Registered Irish Collective Asset-management Vehicles (ICAV)" — same ASP.NET POST approach, different `__EVENTTARGET` value. The PDF format is similar enough that `cbi_shadow_sync_v2.py` could handle it with a second download+parse pass.

### Medium-term

**Luxembourg ETF register**
The CSSF (Commission de Surveillance du Secteur Financier) publishes a register of Luxembourg-domiciled UCITS. LU is the second-largest ETF domicile in Europe after Ireland, covering major Amundi, DWS, and Franklin Templeton ranges. Adding a `cssf_sync.py` script alongside the CBI sync would give a more complete picture of the European ETF landscape. The CSSF register is publicly accessible and updated regularly.

### Also planned

**New ETF alert emails**
Trigger a notification when new ETFs appear in the register, using the existing `First_Seen` date to detect them. The daily change detection workflow (above) would handle the triggering logic — if new ETFs are found in a sync run, send a summary email via SendGrid. Independent of the old weekly email script which lives in a separate repo.

**AuM data enrichment**
Cross-reference fund names against a public AuM source (e.g. justETF or ETFdb) to add size context to each fund in the register. Would allow filtering and sorting by AuM, and surface the largest new launches rather than treating all new registrations equally.

**Sub-fund count per ICAV**
Group the register by umbrella and show how many sub-funds each ICAV contains. Useful as a measure of platform scale — a large issuer adding sub-fund #50 to an existing ICAV is a different signal to a new ICAV being incorporated. Feeds naturally into the ICAV register feature above.

**SEC filings (EDGAR)**
The SEC's EDGAR system is publicly accessible via API (`https://efts.sec.gov/LATEST/search-index?q=...&dateRange=custom&...`) and covers N-1A (ETF registration statements), 485BPOS (post-effective amendments), and 497 (prospectus) filings. While SEC-registered funds are US-domiciled and out of scope for the CBI register, cross-referencing is useful for two reasons:

1. **US issuers launching Irish UCITS mirrors** — when BlackRock, Invesco, or State Street file a new N-1A for a US ETF, an Irish UCITS equivalent often follows within 6–18 months. Tracking SEC filings gives early visibility of the product pipeline before it shows up in the CBI register.
2. **ManCo and sub-adviser relationships** — SEC filings disclose the full adviser/sub-adviser chain in detail, which can be used to enrich the ManCo data for funds where the CBI register only shows the Irish management company.

Implementation: a `sec_sync.py` script that polls the EDGAR full-text search API for new N-1A and 485BPOS filings from known Irish-ETF issuers (iShares, Invesco, State Street, Vanguard, etc.), stores results in `data/sec_filings.csv`, and surfaces them in a new dashboard tab alongside the CBI and LEI tabs. No API key required — EDGAR is open access with a declared `User-Agent` header.
