name: ETF Intelligence — Weekly Sync

on:
  schedule:
    # Every Friday at 07:00 UTC = 08:00 Irish Standard Time (UTC+1 summer)
    - cron: '0 7 * * 5'
  workflow_dispatch:   # Manual trigger button in GitHub Actions UI

permissions:
  contents: write      # Needed to commit the updated CSV + dashboard back to repo

jobs:
  sync:
    runs-on: ubuntu-latest

    steps:
      # ── 1. Checkout repo ──────────────────────────────────────────────────
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 0   # Full history so git diff works correctly

      # ── 2. Set up Python ──────────────────────────────────────────────────
      - name: Set up Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      # ── 3. Install dependencies ───────────────────────────────────────────
      - name: Install dependencies
        run: |
          pip install --upgrade pip
          pip install requests beautifulsoup4 pdfplumber pandas openpyxl

      # ── 4. Run CBI sync ───────────────────────────────────────────────────
      - name: Run CBI sync script
        run: python scripts/cbi_shadow_sync_v2.py

      # ── 5. Generate ETF Intelligence dashboard ────────────────────────────
      - name: Generate ETF Intelligence dashboard
        run: python scripts/generate_dashboard.py

      # ── 6. Commit updated data + dashboard back to repo ───────────────────
      - name: Commit and push changes
        run: |
          git config user.name  "etf-intelligence-bot"
          git config user.email "bot@users.noreply.github.com"
          git add data/cbi_shadow_db.csv docs/index.html
          git diff --staged --quiet || git commit -m "chore: weekly sync $(date +'%Y-%m-%d')"
          git push

      # ── 7. Send summary email ─────────────────────────────────────────────
      - name: Send weekly summary email
        if: success()
        env:
          SENDGRID_API_KEY: ${{ secrets.SENDGRID_API_KEY }}
          EMAIL_TO:         ${{ secrets.EMAIL_TO }}
          EMAIL_FROM:       ${{ secrets.EMAIL_FROM }}
        run: python scripts/send_email.py

      # ── 8. Report on failure ──────────────────────────────────────────────
      - name: Report failure
        if: failure()
        run: |
          echo "Sync failed — check the Actions log for details."
          echo "GitHub will notify the repo owner automatically."
