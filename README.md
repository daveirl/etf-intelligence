# ETF Intelligence — CBI Register Tracker

A self-updating dashboard that tracks ETF registrations on the [Central Bank of Ireland UCITS register](https://registers.centralbank.ie/).

Runs automatically every Friday via GitHub Actions, keeping a searchable shadow database of the register and publishing a live dashboard to GitHub Pages.

## Live Dashboard

👉 **[daveirl.github.io/cbi-parse](https://daveirl.github.io/cbi-parse)**

Features:
- Search and filter all CBI-registered funds by name, platform, management company, depositary, and date
- ETF-only view with 30-day / 90-day / YTD new-registration counts
- Top issuers and depositary market share charts
- CSV export (respects active filters)
- Live LEI lookup via the [GLEIF API](https://api.gleif.org)

## Repository Structure

```
cbi-parse/
├── .github/
│   └── workflows/
│       └── weekly_sync.yml       # GitHub Actions — runs every Friday
├── data/
│   └── cbi_shadow_db.csv         # Shadow database (auto-updated by Actions)
├── docs/
│   └── index.html                # Dashboard (served by GitHub Pages)
├── scripts/
│   ├── cbi_shadow_sync_v2.py     # Downloads + parses CBI PDF, updates CSV
│   ├── generate_dashboard.py     # Reads CSV, writes docs/index.html
│   └── send_email.py             # Sends weekly summary via SendGrid
└── README.md
```

## Setup

### 1. Enable GitHub Pages
Go to **Settings → Pages** and set:
- Source: `Deploy from a branch`
- Branch: `main`
- Folder: `/docs`

The dashboard will be live at `https://daveirl.github.io/cbi-parse` within a minute.

### 2. Add GitHub Secrets
Go to **Settings → Secrets and variables → Actions** and add:

| Secret | Value |
|--------|-------|
| `SENDGRID_API_KEY` | Your SendGrid API key (free tier = 100 emails/day) |
| `EMAIL_TO` | Recipient address(es), comma-separated |
| `EMAIL_FROM` | Verified sender address in your SendGrid account |

### 3. Run Manually (optional)
Go to **Actions → ETF Intelligence — Weekly Sync → Run workflow** to trigger a sync immediately.

## Local Development

```bash
pip install requests beautifulsoup4 pdfplumber pandas openpyxl

# Run the full pipeline
python scripts/cbi_shadow_sync_v2.py    # Downloads PDF, updates data/cbi_shadow_db.csv
python scripts/generate_dashboard.py    # Regenerates docs/index.html
```

Open `docs/index.html` in your browser to preview the dashboard locally.

## How It Works

1. **`cbi_shadow_sync_v2.py`** downloads the CBI UCITS register PDF, extracts fund records (including umbrella platform headers, Management Company, and Depositary columns), and merges them into `data/cbi_shadow_db.csv`. New entries get a `First_Seen` date; existing entries are updated if any fields changed.

2. **`generate_dashboard.py`** reads the CSV, enriches Platform/ManCo/Depositary fields using a known-issuer lookup table, and bakes everything into a self-contained `docs/index.html` with all data embedded as JSON.

3. **`send_email.py`** sends a summary of new ETFs to the team via SendGrid.

4. **`weekly_sync.yml`** orchestrates all of the above on a Friday morning schedule and commits the updated files back to the repo.

## Notes

- The CBI register PDF format occasionally changes — if parsing breaks, check the column-detection logic in `cbi_shadow_sync_v2.py` and the `PLATFORM_MAP` lookup table.
- The dashboard is entirely static (no server needed) and works on any intranet or GitHub Pages.
- The LEI tab queries the GLEIF API directly from the browser — no API key required.
