"""Drive all per-issuer AUM scrapers and write data/aum_db.csv.

Each issuer module under scripts/aum/<name>.py exports a `fetch()` callable
that returns a list of records (see scripts/aum/base.py). This script
iterates over the configured issuer list, applies ECB FX to express every
AUM in EUR alongside its native currency, preserves prior `first_seen`
dates, and writes the combined output.

Add a new issuer by writing scripts/aum/<name>.py and appending the import
below.
"""

from __future__ import annotations

import csv
import logging
import os
from datetime import date

from aum import hanetf
from aum.base import build_session, load_fx_rates, to_eur

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

ISSUERS = [
    hanetf,
    # Follow-ups (each implements .fetch()): wisdomtree, global_x, tabula
]

OUTPUT = "data/aum_db.csv"
COLUMNS = ["issuer", "fund_name", "isin", "ticker",
           "aum_native", "currency", "aum_eur", "as_of",
           "source_url", "first_seen"]


def main() -> None:
    today = date.today().isoformat()

    # Preserve First_Seen for ISINs we've already captured.
    first_seen: dict[str, str] = {}
    if os.path.exists(OUTPUT):
        with open(OUTPUT, newline="") as f:
            for row in csv.DictReader(f):
                isin = (row.get("isin") or "").strip()
                fs   = (row.get("first_seen") or "").strip()
                if isin and fs:
                    first_seen[isin] = fs

    session = build_session()
    fx      = load_fx_rates(session)
    log.info("Loaded %d FX rates", len(fx))

    all_records: list[dict] = []
    for mod in ISSUERS:
        name = getattr(mod, "ISSUER", mod.__name__)
        log.info("Running %s scraper", name)
        try:
            records = mod.fetch()
        except Exception as e:  # noqa: BLE001 — one broken issuer shouldn't kill the run
            log.exception("%s scraper crashed: %s", name, e)
            continue
        for rec in records:
            rec["aum_eur"]    = to_eur(rec.get("aum_native"), rec.get("currency", ""), fx) or ""
            rec["first_seen"] = first_seen.get(rec["isin"], today)
            for col in COLUMNS:
                rec.setdefault(col, "")
        all_records.extend(records)

    os.makedirs(os.path.dirname(OUTPUT) or ".", exist_ok=True)
    with open(OUTPUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        for rec in all_records:
            w.writerow(rec)

    log.info("Saved %d AUM records to %s", len(all_records), OUTPUT)


if __name__ == "__main__":
    main()
