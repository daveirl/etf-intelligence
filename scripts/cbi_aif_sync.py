"""
cbi_aif_sync.py
───────────────
Downloads the CBI register of Authorised ICAV-form Alternative Investment
Funds (AIFs) and parses it into data/aif_db.csv. Reuses the parsing
machinery from cbi_shadow_sync_v2 — the AIF ICAV PDF has the same column
structure as the UCITS register (Fund Name, Auth Date, ManCo, Trustee).

The other four AIF registers (Plc / Unit Trust / CCF / ILP) are out of
scope for now; add separate sync scripts when they're needed.
"""

from cbi_shadow_sync_v2 import run_sync

TARGET_TEXT = (
    "Authorised Irish Collective Asset-management Vehicles, Irish Collective "
    "Asset-management Vehicles Act 2015"
)
DB_FILE = "data/aif_db.csv"

if __name__ == "__main__":
    run_sync(target_text=TARGET_TEXT, db_file=DB_FILE)
