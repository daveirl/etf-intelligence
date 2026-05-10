"""
generate_dashboard.py
─────────────────────
Reads data/cbi_shadow_db.csv and writes docs/index.html.
No guessing — uses ManCo and Depositary exactly as parsed from the CBI PDF.
"""

import pandas as pd
import json
import os
import re
from datetime import date

CSV_PATH      = os.path.join(os.path.dirname(__file__), "..", "data", "cbi_shadow_db.csv")
AIF_CSV_PATH  = os.path.join(os.path.dirname(__file__), "..", "data", "aif_db.csv")
ICAV_CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "icav_db.csv")
HTML_OUT      = os.path.join(os.path.dirname(__file__), "..", "docs", "index.html")
TODAY         = date.today().isoformat()

def build_html(df, aif_df, icav_df):
    df["is_etf"] = df["Fund Name"].str.contains("ETF", case=False, na=False)
    df["Auth_Date"] = pd.to_datetime(df["Auth_Date"], errors="coerce")
    now = pd.Timestamp(TODAY)

    df_etf   = df[df["is_etf"]]
    total    = len(df)
    total_etf = len(df_etf)
    new_30   = len(df_etf[df_etf["Auth_Date"] >= now - pd.Timedelta(days=30)])
    new_90   = len(df_etf[df_etf["Auth_Date"] >= now - pd.Timedelta(days=90)])
    ytd      = len(df_etf[df_etf["Auth_Date"].dt.year == now.year])

    df["Auth_Date"] = df["Auth_Date"].dt.strftime("%Y-%m-%d").fillna("")
    df["ManCo"]      = df.get("ManCo", pd.Series([""] * len(df))).fillna("")
    df["Depositary"] = df.get("Depositary", pd.Series([""] * len(df))).fillna("")
    df["Umbrella"]   = df.get("Umbrella",   pd.Series([""] * len(df))).fillna("")

    records = df[["Fund Name", "ManCo", "Depositary", "Auth_Date", "is_etf"]].fillna("").to_dict(orient="records")
    data_js = json.dumps(records, separators=(",", ":"))

    # ─── AIF register (ICAV-form AIFs) ────────────────────────────────
    aif_df = aif_df.copy()
    if "Umbrella" not in aif_df.columns:
        aif_df["Umbrella"] = ""
    aif_df["Auth_Date"]  = pd.to_datetime(aif_df.get("Auth_Date", pd.Series([""] * len(aif_df))), errors="coerce")
    aif_total            = len(aif_df)
    aif_new_30           = int((aif_df["Auth_Date"] >= now - pd.Timedelta(days=30)).sum())
    aif_new_90           = int((aif_df["Auth_Date"] >= now - pd.Timedelta(days=90)).sum())
    aif_ytd              = int((aif_df["Auth_Date"].dt.year == now.year).sum())
    aif_df["Auth_Date"]  = aif_df["Auth_Date"].dt.strftime("%Y-%m-%d").fillna("")
    aif_df["ManCo"]      = aif_df.get("ManCo",      pd.Series([""] * len(aif_df))).fillna("")
    aif_df["Depositary"] = aif_df.get("Depositary", pd.Series([""] * len(aif_df))).fillna("")
    aif_df["Umbrella"]   = aif_df["Umbrella"].fillna("")
    aif_records = aif_df[["Fund Name", "ManCo", "Depositary", "Auth_Date"]].fillna("").to_dict(orient="records")
    aif_data_js = json.dumps(aif_records, separators=(",", ":"))

    aif_manco_counts = aif_df[aif_df["ManCo"] != ""].groupby("ManCo").size().sort_values(ascending=False).head(8)
    aif_manco_labels = json.dumps(list(aif_manco_counts.index))
    aif_manco_values = json.dumps(list(aif_manco_counts.values.tolist()))
    aif_dep_counts   = aif_df[aif_df["Depositary"] != ""].groupby("Depositary").size().sort_values(ascending=False).head(6)
    aif_dep_labels   = json.dumps(list(aif_dep_counts.index))
    aif_dep_values   = json.dumps(list(aif_dep_counts.values.tolist()))

    # ─── ICAV register ────────────────────────────────────────────────
    # Match ICAVs to umbrellas across BOTH the UCITS and AIF registers
    # (case-insensitive, exact). An ICAV with no UCITS sub-funds but with
    # AIF sub-funds is therefore not flagged as "no sub-funds yet".
    def _umbrella_counts(frame):
        if "Umbrella" not in frame.columns or frame.empty:
            return {}
        s = frame["Umbrella"].fillna("").astype(str)
        sub = frame[s.str.strip() != ""].copy()
        if sub.empty:
            return {}
        sub["_key"] = sub["Umbrella"].astype(str).str.upper().str.strip()
        return sub.groupby("_key").size().to_dict()

    ucits_counts = _umbrella_counts(df)
    aif_counts   = _umbrella_counts(aif_df)
    subfund_counts = {}
    for k, v in ucits_counts.items():
        subfund_counts[k] = subfund_counts.get(k, 0) + v
    for k, v in aif_counts.items():
        subfund_counts[k] = subfund_counts.get(k, 0) + v

    icav_df = icav_df.copy()
    icav_df["ICAV Name"] = icav_df["ICAV Name"].fillna("").astype(str)
    icav_df["Reg Date"]  = pd.to_datetime(icav_df["Reg Date"], errors="coerce")
    icav_df = icav_df.sort_values("Reg Date", ascending=False, na_position="last")
    icav_df["Reg Date"]  = icav_df["Reg Date"].dt.strftime("%Y-%m-%d").fillna("")
    icav_df["Reg Number"]      = icav_df.get("Reg Number",     pd.Series([""] * len(icav_df))).fillna("")
    icav_df["In Liquidation"]  = icav_df.get("In Liquidation", pd.Series([""] * len(icav_df))).fillna("")
    icav_df["ETF Related"]     = icav_df.get("ETF Related",    pd.Series([""] * len(icav_df))).fillna("")

    icav_records = []
    for _, row in icav_df.iterrows():
        name = row["ICAV Name"].strip()
        # Strip trailing "(in Liquidation)" for the match key only — display keeps it
        match_key = re.sub(r"\s*\(in Liquidation\)\s*$", "", name, flags=re.I).upper().strip()
        icav_records.append({
            "name":        name,
            "reg_date":    row["Reg Date"],
            "reg_number":  row["Reg Number"],
            "in_liq":      str(row["In Liquidation"]).strip().lower() == "yes",
            "etf":         str(row["ETF Related"]).strip().lower() == "yes",
            "sub_count":   int(subfund_counts.get(match_key, 0)),
        })

    icav_total       = len(icav_records)
    icav_no_subs     = sum(1 for r in icav_records if r["sub_count"] == 0 and not r["in_liq"])
    icav_etf_related = sum(1 for r in icav_records if r["etf"])
    icav_in_liq      = sum(1 for r in icav_records if r["in_liq"])
    icav_data_js     = json.dumps(icav_records, separators=(",", ":"))

    # Top ManCos by ETF count
    manco_counts = df[df["ManCo"] != ""].groupby("ManCo").size().sort_values(ascending=False).head(8)
    manco_labels = json.dumps(list(manco_counts.index))
    manco_values = json.dumps(list(manco_counts.values.tolist()))

    # Top depositaries (all funds, not ETF-only)
    dep_counts = df[df["Depositary"] != ""].groupby("Depositary").size().sort_values(ascending=False).head(6)
    dep_labels = json.dumps(list(dep_counts.index))
    dep_values = json.dumps(list(dep_counts.values.tolist()))

    # Authorisations by year, split ETF vs non-ETF, for the stacked bar chart.
    yr_series = df["Auth_Date"].astype(str).str.slice(0, 4)
    by_year = df.assign(_yr=yr_series)
    by_year = by_year[by_year["_yr"].str.fullmatch(r"\d{4}", na=False)]
    by_year["_yr"] = by_year["_yr"].astype(int)
    yr_grouped = by_year.groupby("_yr")["is_etf"].agg(["sum", "count"])
    yr_grouped["non_etf"] = yr_grouped["count"] - yr_grouped["sum"]
    yr_grouped = yr_grouped.sort_index()
    year_labels  = json.dumps([int(y) for y in yr_grouped.index])
    year_etf     = json.dumps([int(v) for v in yr_grouped["sum"].values])
    year_non_etf = json.dumps([int(v) for v in yr_grouped["non_etf"].values])

    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ETF Intelligence — CBI Fund &amp; ICAV Registers</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Mono:wght@400;500&family=DM+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
:root{--bg:#0d1117;--surface:#161b22;--surface2:#1c2330;--border:#30363d;--accent:#f0b429;--green:#3fb950;--text:#e6edf3;--muted:#8b949e}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:'DM Sans',sans-serif;font-size:14px;min-height:100vh}
.header{background:var(--surface);border-bottom:1px solid var(--border);padding:0 32px;display:flex;align-items:center;justify-content:space-between;height:60px;position:sticky;top:0;z-index:100}
.logo{font-family:'DM Serif Display',serif;font-size:20px;display:flex;align-items:center;gap:10px}
.logo-dot{width:8px;height:8px;background:var(--accent);border-radius:50%}
.logo span{color:var(--accent)}
.header-meta{font-size:12px;color:var(--muted)}
.tabs{display:flex;border-bottom:1px solid var(--border);background:var(--surface);padding:0 32px}
.tab{padding:14px 20px;cursor:pointer;font-size:13px;font-weight:500;color:var(--muted);border-bottom:2px solid transparent;transition:.2s}
.tab.active{color:var(--accent);border-bottom-color:var(--accent)}
.tab-content{display:none}.tab-content.active{display:block}
.sub-tabs{display:flex;gap:4px;margin-bottom:16px;border-bottom:1px solid var(--border)}
.sub-tab{padding:8px 16px;cursor:pointer;font-size:12px;font-weight:500;color:var(--muted);border-bottom:2px solid transparent;transition:.15s;margin-bottom:-1px}
.sub-tab:hover{color:var(--text)}
.sub-tab.active{color:var(--accent);border-bottom-color:var(--accent)}
.sub-tab-content{display:none}
.sub-tab-content.active{display:block}
.layout{display:grid;grid-template-columns:260px 1fr;min-height:calc(100vh - 120px)}
.sidebar{background:var(--surface);border-right:1px solid var(--border);padding:20px;display:flex;flex-direction:column;gap:16px}
.sidebar h3{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin-bottom:4px}
.filter-group{display:flex;flex-direction:column;gap:6px}
.filter-btn,.icav-filter-btn,.aif-filter-btn{background:var(--surface2);border:1px solid var(--border);color:var(--text);padding:7px 12px;border-radius:6px;cursor:pointer;font-size:12px;text-align:left;transition:.15s;width:100%}
.filter-btn:hover,.filter-btn.active,.icav-filter-btn:hover,.icav-filter-btn.active,.aif-filter-btn:hover,.aif-filter-btn.active{border-color:var(--accent);color:var(--accent)}
.icav-badge{display:inline-block;font-size:10px;padding:2px 8px;border-radius:10px;font-weight:600;letter-spacing:.02em}
.icav-badge.has-subs{background:#3fb95022;color:var(--green);border:1px solid #3fb95044}
.icav-badge.no-subs{background:#f0b42922;color:var(--accent);border:1px solid #f0b42944}
.icav-badge.in-liq{background:#e05c2c22;color:#e05c2c;border:1px solid #e05c2c44}
tr.icav-no-subs td:first-child{border-left:2px solid var(--accent)}
select,input[type=date],input[type=text]{background:var(--surface2);border:1px solid var(--border);color:var(--text);padding:7px 10px;border-radius:6px;font-size:12px;width:100%;outline:none}
select:focus,input:focus{border-color:var(--accent)}
.main{padding:24px;overflow:auto}
.stats-row{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:24px}
.stat{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:14px;text-align:center}
.stat-val{font-size:22px;font-weight:600;color:var(--accent);font-family:'DM Mono',monospace}
.stat-lbl{font-size:11px;color:var(--muted);margin-top:4px}
.charts-row{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:24px}
.chart-card{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:16px}
.chart-card h3{font-size:13px;font-weight:600;margin-bottom:14px}
.bar-row{display:flex;align-items:center;gap:10px;margin-bottom:7px}
.bar-label{font-size:11px;color:var(--muted);width:200px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex-shrink:0}
.bar-track{flex:1;background:var(--surface2);border-radius:3px;height:8px;display:flex;overflow:hidden}
.bar-fill{height:8px;border-radius:0;transition:.4s}
.bar-count{font-size:11px;color:var(--muted);font-family:'DM Mono',monospace;width:60px;text-align:right;white-space:nowrap}
.year-legend{display:flex;gap:14px;margin-bottom:10px;font-size:11px;color:var(--muted)}
.year-legend .swatch{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:-1px}
.mono-date{font-family:'DM Mono',monospace;font-size:12px}
.table-wrap{background:var(--surface);border:1px solid var(--border);border-radius:8px;overflow:hidden}
.table-header{padding:14px 16px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--border)}
.table-header h2{font-size:14px;font-weight:600}
.export-btn{background:var(--accent);color:#000;border:none;padding:6px 14px;border-radius:5px;cursor:pointer;font-size:12px;font-weight:600}
table{width:100%;border-collapse:collapse}
th{background:var(--surface2);padding:10px 14px;text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
td{padding:9px 14px;border-bottom:1px solid var(--border);font-size:13px;vertical-align:middle}
tr:last-child td{border-bottom:none}
tr:hover td{background:var(--surface2)}
.etf-badge{background:#f0b42922;border:1px solid #f0b42966;color:var(--accent);font-size:10px;padding:2px 7px;border-radius:10px;font-weight:600;white-space:nowrap}
.pagination{display:flex;align-items:center;gap:8px;padding:12px 16px;border-top:1px solid var(--border)}
.page-btn{background:var(--surface2);border:1px solid var(--border);color:var(--text);padding:5px 10px;border-radius:5px;cursor:pointer;font-size:12px}
.page-btn:hover{border-color:var(--accent)}
.page-info{font-size:12px;color:var(--muted)}
.lei-wrap{padding:32px}
.search-row{display:flex;gap:10px;margin-bottom:16px}
.search-input{flex:1;background:var(--surface);border:1px solid var(--border);color:var(--text);padding:10px 14px;border-radius:8px;font-size:14px;outline:none}
.search-input:focus{border-color:var(--accent)}
.search-btn{background:var(--accent);color:#000;border:none;padding:10px 20px;border-radius:8px;cursor:pointer;font-weight:600;font-size:14px}
.quick-btns{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:20px;align-items:center}
.quick-btn{background:var(--surface2);border:1px solid var(--border);color:var(--muted);padding:5px 12px;border-radius:20px;cursor:pointer;font-size:12px}
.quick-btn:hover{border-color:var(--accent);color:var(--accent)}
.spinner{width:14px;height:14px;border:2px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:spin .7s linear infinite;flex-shrink:0}
@keyframes spin{to{transform:rotate(360deg)}}
.lei-card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:18px 20px;margin-bottom:12px;transition:.15s}
.lei-card:hover{border-color:var(--accent)}
.lei-card-header{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:14px}
.lei-card-title{font-weight:700;font-size:16px;line-height:1.3;color:var(--text)}
.lei-card-sub{font-size:12px;color:var(--muted);margin-top:3px}
.lei-status-badge{font-size:10px;padding:3px 10px;border-radius:10px;font-weight:700;white-space:nowrap;flex-shrink:0}
.issued{background:#3fb95022;color:var(--green);border:1px solid #3fb95044}
.lapsed{background:#e05c2c22;color:#e05c2c;border:1px solid #e05c2c44}
.pending{background:#f0b42922;color:var(--accent);border:1px solid #f0b42944}
.other-status{background:#88888822;color:var(--muted);border:1px solid #88888844}
.lei-card-body{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:14px}
.lei-field label{font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);display:block;margin-bottom:3px}
.lei-field span{font-size:12px;color:var(--text)}
.lei-field .mono{font-family:'DM Mono',monospace;font-size:11px;color:var(--accent)}
.lei-card-footer{display:flex;align-items:center;gap:20px;padding-top:12px;border-top:1px solid var(--border)}
.lei-footer-item{font-size:11px;color:var(--muted)}
.lei-footer-item strong{color:var(--text);font-weight:500}
.lei-cbi-match{background:#f0b42911;border:1px solid #f0b42933;border-radius:6px;padding:8px 12px;margin-top:10px;font-size:12px}
.lei-cbi-match-label{font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:var(--accent);margin-bottom:4px}
.lei-grid{display:flex;flex-direction:column;gap:2px}
.lei-cbi-row{display:flex;justify-content:space-between;color:var(--muted);margin-top:2px}
.lei-cbi-row span:last-child{color:var(--text)}
</style>
</head>
<body>
<header class="header">
  <div class="logo"><div class="logo-dot"></div>ETF <span>Intelligence</span></div>
  <div class="header-meta">CBI Fund &amp; ICAV Registers &middot; Updated """ + TODAY + """</div>
</header>
<div class="tabs">
  <div class="tab active" onclick="switchTab('cbi')">CBI Fund Register</div>
  <div class="tab" onclick="switchTab('aif')">CBI AIF Register</div>
  <div class="tab" onclick="switchTab('icav')">CBI ICAV Register</div>
  <div class="tab" onclick="switchTab('lei')">LEI Lookup</div>
</div>

<div id="tab-cbi" class="tab-content active">
<div class="layout">
  <aside class="sidebar">
    <div class="filter-group">
      <h3>Fund Type</h3>
      <button class="filter-btn active" onclick="setFilter('all',this)">All Funds</button>
      <button class="filter-btn" onclick="setFilter('etf',this)">ETFs Only</button>
      <button class="filter-btn" onclick="setFilter('new30',this)">New (30d)</button>
      <button class="filter-btn" onclick="setFilter('new90',this)">New (90d)</button>
    </div>
    <div class="filter-group">
      <h3>Auth Date From</h3>
      <input type="date" id="dFrom" onchange="applyFilters()">
    </div>
    <div class="filter-group">
      <h3>Auth Date To</h3>
      <input type="date" id="dTo" onchange="applyFilters()">
    </div>
    <div class="filter-group">
      <h3>Management Co.</h3>
      <select id="selManco" onchange="applyFilters()"><option value="">All ManCos</option></select>
    </div>
    <div class="filter-group">
      <h3>Depositary</h3>
      <select id="selDep" onchange="applyFilters()"><option value="">All Depositaries</option></select>
    </div>
    <div class="filter-group">
      <h3>Search</h3>
      <input type="text" id="searchBox" placeholder="Fund name&hellip;" oninput="applyFilters()">
    </div>
  </aside>
  <main class="main">
    <div class="sub-tabs">
      <div class="sub-tab" data-sub="cbi-stats" onclick="switchSubTab('cbi','stats')">Stats</div>
      <div class="sub-tab active" data-sub="cbi-results" onclick="switchSubTab('cbi','results')">Results</div>
    </div>
    <div id="cbi-sub-stats" class="sub-tab-content">
      <div class="stats-row">
        <div class="stat"><div class="stat-val">""" + str(total) + """</div><div class="stat-lbl">Total Funds</div></div>
        <div class="stat"><div class="stat-val">""" + str(total_etf) + """</div><div class="stat-lbl">ETFs</div></div>
        <div class="stat"><div class="stat-val">""" + str(new_30) + """</div><div class="stat-lbl">New ETFs (30d)</div></div>
        <div class="stat"><div class="stat-val">""" + str(new_90) + """</div><div class="stat-lbl">New ETFs (90d)</div></div>
        <div class="stat"><div class="stat-val">""" + str(ytd) + """</div><div class="stat-lbl">ETFs YTD """ + str(now.year) + """</div></div>
      </div>
      <div class="charts-row">
        <div class="chart-card"><h3>Top Management Companies</h3><div id="mancoChart"></div></div>
        <div class="chart-card"><h3>Depositary Market Share</h3><div id="depChart"></div></div>
      </div>
      <div class="charts-row" style="grid-template-columns:1fr">
        <div class="chart-card"><h3>Authorisations by Year (ETF vs non-ETF)</h3><div id="yearChart"></div></div>
      </div>
    </div>
    <div id="cbi-sub-results" class="sub-tab-content active">
      <div class="table-wrap">
        <div class="table-header">
          <h2>Fund Register <span id="rowCount" style="color:var(--muted);font-weight:400;font-size:12px"></span></h2>
          <button class="export-btn" onclick="exportCSV()">Export CSV</button>
        </div>
        <div style="overflow-x:auto">
          <table>
            <thead><tr>
              <th>Fund Name</th><th>Management Co.</th><th>Depositary</th><th>Auth Date</th>
            </tr></thead>
            <tbody id="tableBody"></tbody>
          </table>
        </div>
        <div class="pagination">
          <button class="page-btn" onclick="changePage(-1)">&larr; Prev</button>
          <span class="page-info" id="pageInfo"></span>
          <button class="page-btn" onclick="changePage(1)">Next &rarr;</button>
        </div>
      </div>
    </div>
  </main>
</div>
</div>

<div id="tab-aif" class="tab-content">
<div class="layout">
  <aside class="sidebar">
    <div class="filter-group">
      <h3>View</h3>
      <button class="aif-filter-btn active" onclick="setAifFilter('all',this)">All AIFs</button>
      <button class="aif-filter-btn" onclick="setAifFilter('new30',this)">New (30d)</button>
      <button class="aif-filter-btn" onclick="setAifFilter('new90',this)">New (90d)</button>
    </div>
    <div class="filter-group">
      <h3>Auth Date From</h3>
      <input type="date" id="aifDFrom" onchange="applyAifFilters()">
    </div>
    <div class="filter-group">
      <h3>Auth Date To</h3>
      <input type="date" id="aifDTo" onchange="applyAifFilters()">
    </div>
    <div class="filter-group">
      <h3>Management Co.</h3>
      <select id="aifSelManco" onchange="applyAifFilters()"><option value="">All ManCos</option></select>
    </div>
    <div class="filter-group">
      <h3>Depositary</h3>
      <select id="aifSelDep" onchange="applyAifFilters()"><option value="">All Depositaries</option></select>
    </div>
    <div class="filter-group">
      <h3>Search</h3>
      <input type="text" id="aifSearchBox" placeholder="Fund name&hellip;" oninput="applyAifFilters()">
    </div>
  </aside>
  <main class="main">
    <div class="sub-tabs">
      <div class="sub-tab" data-sub="aif-stats" onclick="switchSubTab('aif','stats')">Stats</div>
      <div class="sub-tab active" data-sub="aif-results" onclick="switchSubTab('aif','results')">Results</div>
    </div>
    <div id="aif-sub-stats" class="sub-tab-content">
      <div class="stats-row">
        <div class="stat"><div class="stat-val">""" + str(aif_total) + """</div><div class="stat-lbl">Total AIFs (ICAV-form)</div></div>
        <div class="stat"><div class="stat-val">""" + str(aif_new_30) + """</div><div class="stat-lbl">New (30d)</div></div>
        <div class="stat"><div class="stat-val">""" + str(aif_new_90) + """</div><div class="stat-lbl">New (90d)</div></div>
        <div class="stat"><div class="stat-val">""" + str(aif_ytd) + """</div><div class="stat-lbl">YTD """ + str(now.year) + """</div></div>
      </div>
      <div class="charts-row">
        <div class="chart-card"><h3>Top Management Companies</h3><div id="aifMancoChart"></div></div>
        <div class="chart-card"><h3>Depositary Market Share</h3><div id="aifDepChart"></div></div>
      </div>
    </div>
    <div id="aif-sub-results" class="sub-tab-content active">
      <div class="table-wrap">
        <div class="table-header">
          <h2>AIF Register <span style="color:var(--muted);font-weight:400;font-size:11px;margin-left:4px">ICAV-form, ICAV Act 2015</span> <span id="aifRowCount" style="color:var(--muted);font-weight:400;font-size:12px"></span></h2>
          <button class="export-btn" onclick="exportAifCSV()">Export CSV</button>
        </div>
        <div style="overflow-x:auto">
          <table>
            <thead><tr>
              <th>Fund Name</th><th>Management Co.</th><th>Depositary</th><th>Auth Date</th>
            </tr></thead>
            <tbody id="aifTableBody"></tbody>
        </table>
      </div>
        <div class="pagination">
          <button class="page-btn" onclick="changeAifPage(-1)">&larr; Prev</button>
          <span class="page-info" id="aifPageInfo"></span>
          <button class="page-btn" onclick="changeAifPage(1)">Next &rarr;</button>
        </div>
      </div>
    </div>
  </main>
</div>
</div>

<div id="tab-icav" class="tab-content">
<div class="layout">
  <aside class="sidebar">
    <div class="filter-group">
      <h3>Status</h3>
      <button class="icav-filter-btn active" onclick="setIcavFilter('all',this)">All ICAVs</button>
      <button class="icav-filter-btn" onclick="setIcavFilter('nosubs',this)">No Sub-funds Yet</button>
      <button class="icav-filter-btn" onclick="setIcavFilter('etf',this)">ETF-Related</button>
      <button class="icav-filter-btn" onclick="setIcavFilter('liq',this)">In Liquidation</button>
    </div>
    <div class="filter-group">
      <h3>Reg Date From</h3>
      <input type="date" id="icavDFrom" onchange="applyIcavFilters()">
    </div>
    <div class="filter-group">
      <h3>Reg Date To</h3>
      <input type="date" id="icavDTo" onchange="applyIcavFilters()">
    </div>
    <div class="filter-group">
      <h3>Search</h3>
      <input type="text" id="icavSearch" placeholder="ICAV name&hellip;" oninput="applyIcavFilters()">
    </div>
  </aside>
  <main class="main">
    <div class="stats-row">
      <div class="stat"><div class="stat-val">""" + str(icav_total) + """</div><div class="stat-lbl">Total ICAVs</div></div>
      <div class="stat"><div class="stat-val">""" + str(icav_no_subs) + """</div><div class="stat-lbl">No Sub-funds Yet</div></div>
      <div class="stat"><div class="stat-val">""" + str(icav_etf_related) + """</div><div class="stat-lbl">ETF-Related</div></div>
      <div class="stat"><div class="stat-val">""" + str(icav_in_liq) + """</div><div class="stat-lbl">In Liquidation</div></div>
    </div>
    <div class="table-wrap">
      <div class="table-header">
        <h2>ICAV Register <span id="icavRowCount" style="color:var(--muted);font-weight:400;font-size:12px"></span></h2>
        <button class="export-btn" onclick="exportIcavCSV()">Export CSV</button>
      </div>
      <div style="overflow-x:auto">
        <table>
          <thead><tr>
            <th>ICAV Name</th><th>Reg Date</th><th>Reg #</th><th style="text-align:right">Sub-funds</th><th>Status</th>
          </tr></thead>
          <tbody id="icavTableBody"></tbody>
        </table>
      </div>
      <div class="pagination">
        <button class="page-btn" onclick="changeIcavPage(-1)">&larr; Prev</button>
        <span class="page-info" id="icavPageInfo"></span>
        <button class="page-btn" onclick="changeIcavPage(1)">Next &rarr;</button>
      </div>
    </div>
  </main>
</div>
</div>

<div id="tab-lei" class="tab-content">
<div class="lei-wrap">
  <div style="margin-bottom:20px">
    <h2 style="font-size:16px;font-weight:600;margin-bottom:4px">LEI Lookup</h2>
    <p style="font-size:12px;color:var(--muted)">Live data from the GLEIF database. Page loads with the most recently registered UCITS ETF LEIs across the EU/EEA (any registration status). Paginate through history using the controls below.</p>
  </div>
  <div class="search-row">
    <input class="search-input" id="leiQuery" placeholder="Fund name, ManCo, or paste a 20-character LEI code directly&hellip;" />
    <button class="search-btn" onclick="fetchLEI()">Search</button>
  </div>
  <div class="quick-btns">
    <span style="font-size:12px;color:var(--muted);align-self:center;margin-right:4px">Quick:</span>
    <button class="quick-btn" onclick="quickLEI('BlackRock Asset Management Ireland')">BlackRock IE</button>
    <button class="quick-btn" onclick="quickLEI('Invesco Investment Management Limited')">Invesco IE</button>
    <button class="quick-btn" onclick="quickLEI('Amundi Asset Management')">Amundi FR</button>
    <button class="quick-btn" onclick="quickLEI('WisdomTree Management Limited')">WisdomTree IE</button>
    <button class="quick-btn" onclick="quickLEI('VanEck Asset Management')">VanEck NL</button>
    <button class="quick-btn" onclick="quickLEI('Franklin Templeton International Services')">Franklin Templeton LU</button>
    <button class="quick-btn" onclick="quickLEI('State Street Global Advisors Europe')">State Street IE</button>
    <button class="quick-btn" onclick="quickLEI('DWS Investment')">DWS DE</button>
    <button class="quick-btn" onclick="quickLEI('JPMorgan Asset Management Europe')">JPMorgan LU</button>
    <button class="quick-btn" onclick="quickLEI('PIMCO Europe')">PIMCO IE</button>
    <button class="quick-btn" onclick="quickLEI('Fidelity Investment Management Ireland')">Fidelity IE</button>
    <button class="quick-btn" onclick="quickLEI('HANetf Limited')">HANetf IE</button>
  </div>
  <div id="leiLoading" style="display:none;padding:20px 0">
    <div style="display:flex;align-items:center;gap:10px;color:var(--muted);font-size:13px">
      <div class="spinner"></div> Querying GLEIF database&hellip;
    </div>
  </div>
  <div id="leiSection">
    <div style="font-size:12px;color:var(--muted);margin-bottom:12px" id="leiSectionLabel">10 most recently authorised ETFs</div>
    <div id="leiResults"></div>
    <div id="leiPager" style="display:none;justify-content:center;align-items:center;gap:14px;padding:18px 0;font-size:12px;color:var(--muted)"></div>
  </div>
</div>
</div>

<script>
const ALL_DATA = """ + data_js + """;
const MANCO_LABELS = """ + manco_labels + """;
const MANCO_VALUES = """ + manco_values + """;
const DEP_LABELS   = """ + dep_labels + """;
const DEP_VALUES   = """ + dep_values + """;
const YEAR_LABELS  = """ + year_labels + """;
const YEAR_ETF     = """ + year_etf + """;
const YEAR_NON_ETF = """ + year_non_etf + """;
const PER_PAGE = 50;
let filtered = [...ALL_DATA];
let page = 1;
let activeFilter = 'all';
const today = new Date('""" + TODAY + """');

function init() {
  const mancos = [...new Set(ALL_DATA.map(r=>r.ManCo).filter(Boolean))].sort();
  const deps   = [...new Set(ALL_DATA.map(r=>r.Depositary).filter(Boolean))].sort();
  const mSel = document.getElementById('selManco');
  const dSel = document.getElementById('selDep');
  mancos.forEach(m => { const o=document.createElement('option'); o.value=o.textContent=m; mSel.appendChild(o); });
  deps.forEach(d => { const o=document.createElement('option'); o.value=o.textContent=d; dSel.appendChild(o); });
  applyFilters();
  buildCharts();
}

function setFilter(val, btn) {
  document.querySelectorAll('.filter-btn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  activeFilter = val;
  page = 1;
  applyFilters();
}

function applyFilters() {
  const dFrom  = document.getElementById('dFrom').value;
  const dTo    = document.getElementById('dTo').value;
  const manco  = document.getElementById('selManco').value;
  const dep    = document.getElementById('selDep').value;
  const search = document.getElementById('searchBox').value.toLowerCase();
  filtered = ALL_DATA.filter(r => {
    if (activeFilter==='etf'   && !r.is_etf) return false;
    if (activeFilter==='new30' && (!r.is_etf||!r.Auth_Date||new Date(r.Auth_Date)<new Date(today-30*864e5))) return false;
    if (activeFilter==='new90' && (!r.is_etf||!r.Auth_Date||new Date(r.Auth_Date)<new Date(today-90*864e5))) return false;
    if (dFrom && r.Auth_Date && r.Auth_Date<dFrom) return false;
    if (dTo   && r.Auth_Date && r.Auth_Date>dTo)   return false;
    if (manco && r.ManCo !== manco) return false;
    if (dep   && r.Depositary !== dep) return false;
    if (search && !r['Fund Name'].toLowerCase().includes(search)) return false;
    return true;
  });
  renderTable();
}

function renderTable() {
  const start = (page-1)*PER_PAGE;
  const rows  = filtered.slice(start, start+PER_PAGE);
  document.getElementById('rowCount').textContent = '(' + filtered.length.toLocaleString() + ' funds)';
  document.getElementById('pageInfo').textContent  = 'Page ' + page + ' of ' + (Math.ceil(filtered.length/PER_PAGE)||1);
  document.getElementById('tableBody').innerHTML = rows.map(r =>
    '<tr><td>' + r['Fund Name'] + (r.is_etf?' <span class="etf-badge">ETF</span>':'') + '</td>' +
    '<td>' + (r.ManCo||'') + '</td>' +
    '<td>' + (r.Depositary||'') + '</td>' +
    '<td class="mono-date">' + (r.Auth_Date||'') + '</td></tr>'
  ).join('');
}

function changePage(d) {
  const max = Math.ceil(filtered.length/PER_PAGE)||1;
  page = Math.max(1,Math.min(max,page+d));
  renderTable();
}

function exportCSV() {
  const cols = ['Fund Name','ManCo','Depositary','Auth_Date'];
  const rows = [cols.join(','), ...filtered.map(r =>
    cols.map(c => '"' + (r[c]||'').replace(/"/g,'""') + '"').join(',')
  )];
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([rows.join('\\n')], {type:'text/csv'}));
  a.download = 'cbi_register_""" + TODAY + """.csv';
  a.click();
}

function buildCharts() {
  const maxM = Math.max(...MANCO_VALUES);
  document.getElementById('mancoChart').innerHTML = MANCO_LABELS.map((label,i) =>
    '<div class="bar-row"><div class="bar-label" title="'+label+'">'+label+'</div>' +
    '<div class="bar-track"><div class="bar-fill" style="width:'+(MANCO_VALUES[i]/maxM*100).toFixed(1)+'%;background:var(--accent)"></div></div>' +
    '<div class="bar-count">'+MANCO_VALUES[i]+'</div></div>'
  ).join('');

  const maxD = Math.max(...DEP_VALUES);
  document.getElementById('depChart').innerHTML = DEP_LABELS.map((label,i) =>
    '<div class="bar-row"><div class="bar-label" title="'+label+'">'+label+'</div>' +
    '<div class="bar-track"><div class="bar-fill" style="width:'+(DEP_VALUES[i]/maxD*100).toFixed(1)+'%;background:var(--green)"></div></div>' +
    '<div class="bar-count">'+DEP_VALUES[i]+'</div></div>'
  ).join('');

  // Authorisations by year — stacked ETF / non-ETF
  if (YEAR_LABELS.length) {
    const maxY = Math.max(...YEAR_LABELS.map((_, i) => YEAR_ETF[i] + YEAR_NON_ETF[i]));
    const legend =
      '<div class="year-legend">' +
        '<span><span class="swatch" style="background:var(--accent)"></span>ETFs</span>' +
        '<span><span class="swatch" style="background:var(--green)"></span>Non-ETFs</span>' +
      '</div>';
    const rows = YEAR_LABELS.map((label, i) => {
      const etf    = YEAR_ETF[i] || 0;
      const nonEtf = YEAR_NON_ETF[i] || 0;
      const total  = etf + nonEtf;
      const etfPct    = (etf    / maxY * 100).toFixed(2);
      const nonEtfPct = (nonEtf / maxY * 100).toFixed(2);
      return '<div class="bar-row">' +
        '<div class="bar-label" style="width:50px">' + label + '</div>' +
        '<div class="bar-track">' +
          (nonEtf ? '<div class="bar-fill" style="width:' + nonEtfPct + '%;background:var(--green)" title="' + nonEtf + ' non-ETFs"></div>' : '') +
          (etf    ? '<div class="bar-fill" style="width:' + etfPct + '%;background:var(--accent)" title="' + etf + ' ETFs"></div>'    : '') +
        '</div>' +
        '<div class="bar-count" title="' + etf + ' ETFs / ' + nonEtf + ' non-ETFs">' +
          total + (etf ? ' (' + etf + ' ETF)' : '') +
        '</div>' +
      '</div>';
    }).join('');
    document.getElementById('yearChart').innerHTML = legend + rows;
  }
}

// ─── AIF register tab (ICAV-form AIFs) ──────────────────────────────
const AIF_DATA   = """ + aif_data_js + """;
const AIF_MANCO_LABELS = """ + aif_manco_labels + """;
const AIF_MANCO_VALUES = """ + aif_manco_values + """;
const AIF_DEP_LABELS   = """ + aif_dep_labels   + """;
const AIF_DEP_VALUES   = """ + aif_dep_values   + """;
let aifFiltered = [...AIF_DATA];
let aifPage = 1;
let aifActiveFilter = 'all';
const AIF_PAGE_SIZE = 50;

function initAif() {
  const mancos = [...new Set(AIF_DATA.map(r=>r.ManCo).filter(Boolean))].sort();
  const deps   = [...new Set(AIF_DATA.map(r=>r.Depositary).filter(Boolean))].sort();
  const mSel = document.getElementById('aifSelManco');
  const dSel = document.getElementById('aifSelDep');
  mancos.forEach(m => { const o=document.createElement('option'); o.value=o.textContent=m; mSel.appendChild(o); });
  deps.forEach(d => { const o=document.createElement('option'); o.value=o.textContent=d; dSel.appendChild(o); });
  applyAifFilters();
  buildAifCharts();
}

function setAifFilter(val, btn) {
  document.querySelectorAll('.aif-filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  aifActiveFilter = val;
  aifPage = 1;
  applyAifFilters();
}

function applyAifFilters() {
  const dFrom  = document.getElementById('aifDFrom').value;
  const dTo    = document.getElementById('aifDTo').value;
  const manco  = document.getElementById('aifSelManco').value;
  const dep    = document.getElementById('aifSelDep').value;
  const search = document.getElementById('aifSearchBox').value.toLowerCase();
  aifFiltered = AIF_DATA.filter(r => {
    if (aifActiveFilter==='new30' && (!r.Auth_Date||new Date(r.Auth_Date)<new Date(today-30*864e5))) return false;
    if (aifActiveFilter==='new90' && (!r.Auth_Date||new Date(r.Auth_Date)<new Date(today-90*864e5))) return false;
    if (dFrom && r.Auth_Date && r.Auth_Date<dFrom) return false;
    if (dTo   && r.Auth_Date && r.Auth_Date>dTo)   return false;
    if (manco && r.ManCo !== manco) return false;
    if (dep   && r.Depositary !== dep) return false;
    if (search && !r['Fund Name'].toLowerCase().includes(search)) return false;
    return true;
  });
  renderAifTable();
}

function renderAifTable() {
  const start = (aifPage - 1) * AIF_PAGE_SIZE;
  const rows  = aifFiltered.slice(start, start + AIF_PAGE_SIZE);
  document.getElementById('aifRowCount').textContent = '(' + aifFiltered.length.toLocaleString() + ' AIFs)';
  document.getElementById('aifPageInfo').textContent  = 'Page ' + aifPage + ' of ' + (Math.ceil(aifFiltered.length / AIF_PAGE_SIZE) || 1);
  document.getElementById('aifTableBody').innerHTML = rows.map(r =>
    '<tr><td>' + r['Fund Name'] + '</td>' +
    '<td>' + (r.ManCo||'') + '</td>' +
    '<td>' + (r.Depositary||'') + '</td>' +
    '<td class="mono-date">' + (r.Auth_Date||'') + '</td></tr>'
  ).join('');
}

function changeAifPage(d) {
  const max = Math.ceil(aifFiltered.length / AIF_PAGE_SIZE) || 1;
  aifPage = Math.max(1, Math.min(max, aifPage + d));
  renderAifTable();
}

function exportAifCSV() {
  const cols = ['Fund Name','ManCo','Depositary','Auth_Date'];
  const rows = [cols.join(','), ...aifFiltered.map(r =>
    cols.map(c => '"' + (r[c]||'').replace(/"/g,'""') + '"').join(',')
  )];
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([rows.join('\\n')], {type:'text/csv'}));
  a.download = 'cbi_aif_register_""" + TODAY + """.csv';
  a.click();
}

function buildAifCharts() {
  if (AIF_MANCO_VALUES.length) {
    const maxM = Math.max(...AIF_MANCO_VALUES);
    document.getElementById('aifMancoChart').innerHTML = AIF_MANCO_LABELS.map((label,i) =>
      '<div class="bar-row"><div class="bar-label" title="'+label+'">'+label+'</div>' +
      '<div class="bar-track"><div class="bar-fill" style="width:'+(AIF_MANCO_VALUES[i]/maxM*100).toFixed(1)+'%;background:var(--accent)"></div></div>' +
      '<div class="bar-count">'+AIF_MANCO_VALUES[i]+'</div></div>'
    ).join('');
  }
  if (AIF_DEP_VALUES.length) {
    const maxD = Math.max(...AIF_DEP_VALUES);
    document.getElementById('aifDepChart').innerHTML = AIF_DEP_LABELS.map((label,i) =>
      '<div class="bar-row"><div class="bar-label" title="'+label+'">'+label+'</div>' +
      '<div class="bar-track"><div class="bar-fill" style="width:'+(AIF_DEP_VALUES[i]/maxD*100).toFixed(1)+'%;background:var(--green)"></div></div>' +
      '<div class="bar-count">'+AIF_DEP_VALUES[i]+'</div></div>'
    ).join('');
  }
}

initAif();

// ─── ICAV register tab ──────────────────────────────────────────────
const ICAV_DATA = """ + icav_data_js + """;
const ICAV_PAGE_SIZE = 50;
let icavFilter   = 'all';
let icavFiltered = ICAV_DATA;
let icavPage     = 1;

function setIcavFilter(val, btn) {
  document.querySelectorAll('.icav-filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  icavFilter = val;
  icavPage = 1;
  applyIcavFilters();
}

function applyIcavFilters() {
  const dFrom  = document.getElementById('icavDFrom').value;
  const dTo    = document.getElementById('icavDTo').value;
  const search = document.getElementById('icavSearch').value.toLowerCase();
  icavFiltered = ICAV_DATA.filter(r => {
    if (icavFilter === 'nosubs' && (r.sub_count > 0 || r.in_liq)) return false;
    if (icavFilter === 'etf'    && !r.etf)    return false;
    if (icavFilter === 'liq'    && !r.in_liq) return false;
    if (dFrom && r.reg_date && r.reg_date < dFrom) return false;
    if (dTo   && r.reg_date && r.reg_date > dTo)   return false;
    if (search && !r.name.toLowerCase().includes(search)) return false;
    return true;
  });
  renderIcavTable();
}

function renderIcavTable() {
  const start = (icavPage - 1) * ICAV_PAGE_SIZE;
  const rows  = icavFiltered.slice(start, start + ICAV_PAGE_SIZE);
  document.getElementById('icavRowCount').textContent = '(' + icavFiltered.length.toLocaleString() + ' ICAVs)';
  document.getElementById('icavPageInfo').textContent  = 'Page ' + icavPage + ' of ' + (Math.ceil(icavFiltered.length / ICAV_PAGE_SIZE) || 1);
  document.getElementById('icavTableBody').innerHTML = rows.map(r => {
    let badgeClass, badgeText;
    if (r.in_liq)             { badgeClass = 'in-liq';   badgeText = 'In Liquidation'; }
    else if (r.sub_count > 0) { badgeClass = 'has-subs'; badgeText = r.sub_count + ' sub-fund' + (r.sub_count === 1 ? '' : 's'); }
    else                      { badgeClass = 'no-subs';  badgeText = 'No sub-funds yet'; }
    const rowClass = (!r.in_liq && r.sub_count === 0) ? ' class="icav-no-subs"' : '';
    return '<tr' + rowClass + '><td>' + r.name + (r.etf ? ' <span class="etf-badge">ETF</span>' : '') + '</td>' +
      '<td class="mono-date">' + (r.reg_date || '') + '</td>' +
      '<td class="mono-date">' + (r.reg_number || '') + '</td>' +
      '<td style="text-align:right;font-family:\\'DM Mono\\',monospace">' + r.sub_count + '</td>' +
      '<td><span class="icav-badge ' + badgeClass + '">' + badgeText + '</span></td></tr>';
  }).join('');
}

function changeIcavPage(d) {
  const max = Math.ceil(icavFiltered.length / ICAV_PAGE_SIZE) || 1;
  icavPage = Math.max(1, Math.min(max, icavPage + d));
  renderIcavTable();
}

function exportIcavCSV() {
  const cols = ['name','reg_date','reg_number','sub_count','in_liq','etf'];
  const headers = ['ICAV Name','Reg Date','Reg Number','Sub-fund Count','In Liquidation','ETF Related'];
  const rows = [headers.join(','), ...icavFiltered.map(r =>
    cols.map(c => '"' + String(r[c] ?? '').replace(/"/g,'""') + '"').join(',')
  )];
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([rows.join('\\n')], {type:'text/csv'}));
  a.download = 'cbi_icav_register_""" + TODAY + """.csv';
  a.click();
}

renderIcavTable();

const EU_EEA = new Set(['IE','LU','DE','FR','NL','SE','DK','AT','BE','FI','IT','ES','PT',
  'PL','CZ','HU','SK','RO','BG','HR','SI','EE','LV','LT','CY','MT','GR','NO','IS','LI','CH']);

const LEI_REGEX = /^[A-Z0-9]{18}[0-9]{2}$/;

async function fetchLEI() {
  const q = document.getElementById('leiQuery').value.trim();
  if (!q) return;
  document.getElementById('leiPager').style.display = 'none';
  setLeiLoading(true);
  document.getElementById('leiSectionLabel').textContent = 'Search results for "' + q + '"';
  try {
    let records = [];

    if (LEI_REGEX.test(q.toUpperCase())) {
      // Direct LEI code lookup — exact match, no name search needed
      const url = 'https://api.gleif.org/api/v1/lei-records/' + q.toUpperCase();
      const data = await (await fetch(url)).json();
      if (data.data) records = [data.data];
    } else {
      // Name search — try exact match first, then fuzzy
      const exactUrl = 'https://api.gleif.org/api/v1/lei-records?filter[entity.legalName]=' + encodeURIComponent(q) + '&page[size]=50';
      const exactData = await (await fetch(exactUrl)).json();
      records = exactData.data || [];

      // If fewer than 3 results, also try fuzzy search
      if (records.length < 3) {
        const fuzzyUrl = 'https://api.gleif.org/api/v1/fuzzycompletions?field=entity.legalName&q=' + encodeURIComponent(q);
        const fuzzyData = await (await fetch(fuzzyUrl)).json();
        const suggestions = (fuzzyData.data || []).slice(0, 5).map(s => s.relationships?.lei?.data?.id).filter(Boolean);
        for (const lei of suggestions) {
          if (!records.find(r => r.id === lei)) {
            try {
              const r = await (await fetch('https://api.gleif.org/api/v1/lei-records/' + lei)).json();
              if (r.data) records.push(r.data);
            } catch(e) {}
          }
        }
      }

      // Filter to EU/EEA
      records = records.filter(r => EU_EEA.has(r.attributes?.entity?.legalAddress?.country || ''));
    }

    renderLEI(records, records.length);
  } catch(e) {
    document.getElementById('leiResults').innerHTML = '<p style="color:#e05c2c">Error: ' + e.message + '</p>';
  } finally {
    setLeiLoading(false);
  }
}

// GLEIF doesn't expose a reliable "name contains" filter on /lei-records,
// so we fetch FUND-category LEIs sorted by registration date and filter
// client-side to those whose legal name reads as a UCITS ETF. Filtered
// records accumulate in leiCache so paging back doesn't refetch.
const LEI_PAGE_SIZE        = 10;
const LEI_SERVER_PAGE_SIZE = 100;
const UCITS_ETF_RX = /\\bUCITS\\b[\\s\\S]*\\bETF\\b|\\bETF\\b[\\s\\S]*\\bUCITS\\b/i;

let leiCache           = [];
let leiServerCursor    = 1;
let leiServerExhausted = false;
let currentLEIPage     = 1;

async function fillLEICache(targetCount) {
  while (!leiServerExhausted && leiCache.length < targetCount) {
    const url = 'https://api.gleif.org/api/v1/lei-records' +
      '?filter[entity.category]=FUND' +
      '&sort=-registration.initialRegistrationDate' +
      '&page[size]=' + LEI_SERVER_PAGE_SIZE +
      '&page[number]=' + leiServerCursor;
    const resp = await fetch(url);
    if (!resp.ok) throw new Error('GLEIF HTTP ' + resp.status);
    const data = await resp.json();
    if (data.errors && data.errors.length) throw new Error(data.errors[0]?.title || 'GLEIF error');
    const records = data.data || [];

    for (const rec of records) {
      const ln = rec.attributes?.entity?.legalName;
      const nm = (typeof ln === 'string' ? ln : (ln?.name || ln?.value || '')) || '';
      if (UCITS_ETF_RX.test(nm)) leiCache.push(rec);
    }

    const lastPage = data.meta?.pagination?.lastPage;
    leiServerCursor++;
    if (records.length === 0 || (lastPage && leiServerCursor > lastPage)) {
      leiServerExhausted = true;
    }
  }
}

async function autoLoadRecentLEIs(page) {
  page = Math.max(1, page || 1);
  setLeiLoading(true);
  document.getElementById('leiPager').style.display = 'none';
  document.getElementById('leiSectionLabel').textContent = 'Loading UCITS ETF LEIs (page ' + page + ')…';

  try {
    // Want one extra record so we can tell whether a "next page" exists.
    await fillLEICache(page * LEI_PAGE_SIZE + 1);

    const start = (page - 1) * LEI_PAGE_SIZE;
    const slice = leiCache.slice(start, start + LEI_PAGE_SIZE);

    // Safety-net sort by registration date desc (in case GLEIF ignores `sort=`)
    slice.sort((a, b) => {
      const ad = a.attributes?.registration?.initialRegistrationDate || '';
      const bd = b.attributes?.registration?.initialRegistrationDate || '';
      return bd.localeCompare(ad);
    });

    // Cross-reference each LEI with the CBI register by exact fund name
    const cbiByName = {};
    for (const f of ALL_DATA) {
      if (f['Fund Name']) cbiByName[f['Fund Name'].toUpperCase()] = f;
    }
    for (const rec of slice) {
      const ln = rec.attributes?.entity?.legalName;
      const nm = (typeof ln === 'string' ? ln : (ln?.name || ln?.value || '')) || '';
      const match = nm ? cbiByName[nm.toUpperCase()] : null;
      if (match) rec._cbi = match;
    }

    currentLEIPage = page;
    const hasMore = leiCache.length > start + LEI_PAGE_SIZE || !leiServerExhausted;
    const totalKnown = leiServerExhausted ? leiCache.length : null;

    document.getElementById('leiSectionLabel').textContent =
      'UCITS ETF LEIs by registration date — page ' + currentLEIPage +
      (totalKnown !== null
        ? ' of ' + Math.max(1, Math.ceil(totalKnown / LEI_PAGE_SIZE)) + ' (' + totalKnown.toLocaleString() + ' total)'
        : '');
    renderLEI(slice, slice.length);
    renderLEIPager(hasMore);
  } catch(e) {
    document.getElementById('leiResults').innerHTML = '<p style="color:#e05c2c">Error loading recent LEIs: ' + e.message + '</p>';
  } finally {
    setLeiLoading(false);
  }
}

function renderLEIPager(hasMore) {
  const pager = document.getElementById('leiPager');
  if (!pager) return;
  pager.style.display = 'flex';
  const prevDisabled = currentLEIPage <= 1;
  const nextDisabled = !hasMore;
  pager.innerHTML =
    '<button class="quick-btn"' +
      (prevDisabled
        ? ' disabled style="opacity:0.4;cursor:not-allowed"'
        : ' onclick="autoLoadRecentLEIs(' + (currentLEIPage - 1) + ')"') +
      '>&larr; Newer</button>' +
    '<span>Page ' + currentLEIPage + '</span>' +
    '<button class="quick-btn"' +
      (nextDisabled
        ? ' disabled style="opacity:0.4;cursor:not-allowed"'
        : ' onclick="autoLoadRecentLEIs(' + (currentLEIPage + 1) + ')"') +
      '>Older &rarr;</button>';
}

function setLeiLoading(on) {
  document.getElementById('leiLoading').style.display = on ? 'block' : 'none';
  document.getElementById('leiSection').style.display = on ? 'none' : 'block';
}

function renderLEI(records, total) {
  if (!records.length) {
    document.getElementById('leiResults').innerHTML = '<p style="color:var(--muted);padding:20px 0">No EU/EEA results found.</p>';
    return;
  }
  document.getElementById('leiSectionLabel').textContent = (total || records.length) + ' EU/EEA result(s)';
  document.getElementById('leiResults').innerHTML = records.map(r => {
    const attr   = r.attributes || {};
    const entity = attr.entity || {};
    const reg    = attr.registration || {};
    const laddr  = entity.legalAddress || {};
    const raddr  = entity.registeredAddress || {};

    // Name: GLEIF returns legalName as {name, language} object OR plain string
    const legalNameRaw = entity.legalName;
    const name = (typeof legalNameRaw === 'string')
      ? legalNameRaw
      : (legalNameRaw?.name || legalNameRaw?.value || r.id || 'Unknown');
    const otherNames  = (entity.otherNames || []).map(n => n?.name || n?.value || n).filter(s => typeof s === 'string' && s);
    const lei         = r.id || '';
    const country     = laddr.country || '';
    const city        = laddr.city || '';
    const addrLine    = [laddr.addressLines?.[0], laddr.postalCode, city, country].filter(Boolean).join(', ');
    const legalForm   = entity.legalForm?.id || '';
    const category    = entity.entityCategory || '';
    const subCategory = entity.entitySubCategory || '';
    const rawStatus   = (reg.status || '').toUpperCase();
    const statusLabel = rawStatus.replace(/_/g, ' ') || 'UNKNOWN';
    const statusClass = rawStatus === 'ISSUED' ? 'issued'
      : rawStatus === 'LAPSED' ? 'lapsed'
      : rawStatus.startsWith('PENDING') ? 'pending'
      : 'other-status';
    const registered  = (reg.initialRegistrationDate || '').substring(0, 10);
    const lastUpdate  = (reg.lastUpdateDate || '').substring(0, 10);
    const nextRenewal = (reg.nextRenewalDate || '').substring(0, 10);
    const managingOU  = attr.managingOU?.name || attr.managingOU?.id || '';
    const jurisdiction= entity.jurisdiction || '';

    // Country flag emoji
    const flag = country.length === 2
      ? String.fromCodePoint(...[...country.toUpperCase()].map(c => c.charCodeAt(0) + 127397))
      : '';

    // CBI register cross-reference
    const cbi = r._cbi || null;
    const cbiHtml = cbi ? (
      '<div class="lei-cbi-match">' +
      '<div class="lei-cbi-match-label">&#x2713; CBI Register Match</div>' +
      '<div class="lei-grid">' +
      '<div class="lei-cbi-row"><span>Fund Name</span><span>' + cbi['Fund Name'] + '</span></div>' +
      (cbi.ManCo ? '<div class="lei-cbi-row"><span>ManCo</span><span>' + cbi.ManCo + '</span></div>' : '') +
      (cbi.Depositary ? '<div class="lei-cbi-row"><span>Depositary</span><span>' + cbi.Depositary + '</span></div>' : '') +
      (cbi.Auth_Date ? '<div class="lei-cbi-row"><span>Auth Date</span><span>' + cbi.Auth_Date + '</span></div>' : '') +
      '</div></div>'
    ) : '';

    // For synthetic (CBI-only) records, show a simplified card
    if (r._synthetic) {
      const cbi = r._cbi;
      return '<div class="lei-card" style="opacity:0.85">' +
        '<div class="lei-card-header">' +
          '<div style="flex:1;min-width:0">' +
            '<div class="lei-card-title">🇮🇪 ' + cbi['Fund Name'] + '</div>' +
            '<div class="lei-card-sub">CBI register only &nbsp;&middot;&nbsp; No GLEIF match found</div>' +
          '</div>' +
          '<span class="lei-status-badge issued">ISSUED</span>' +
        '</div>' +
        '<div class="lei-cbi-match" style="margin-top:8px">' +
          '<div class="lei-cbi-match-label">CBI Register</div>' +
          '<div class="lei-grid">' +
          (cbi.ManCo ? '<div class="lei-cbi-row"><span>ManCo</span><span>' + cbi.ManCo + '</span></div>' : '') +
          (cbi.Depositary ? '<div class="lei-cbi-row"><span>Depositary</span><span>' + cbi.Depositary + '</span></div>' : '') +
          (cbi.Auth_Date ? '<div class="lei-cbi-row"><span>Auth Date</span><span>' + cbi.Auth_Date + '</span></div>' : '') +
          '</div>' +
        '</div>' +
      '</div>';
    }

    return '<div class="lei-card">' +
      // Header: name + status
      '<div class="lei-card-header">' +
        '<div style="flex:1;min-width:0">' +
          '<div class="lei-card-title">' + flag + ' ' + name + '</div>' +
          (otherNames.length ? '<div style="font-size:11px;color:var(--muted);margin-top:2px">Also known as: ' + otherNames.slice(0,2).join(', ') + '</div>' : '') +
          '<div class="lei-card-sub">' + (addrLine || [city,country].filter(Boolean).join(', ')) +
            (category ? ' &nbsp;&middot;&nbsp; ' + category : '') +
            (subCategory ? ' / ' + subCategory : '') +
          '</div>' +
        '</div>' +
        '<span class="lei-status-badge ' + statusClass + '">' + statusLabel + '</span>' +
      '</div>' +
      // Body: key fields in grid
      '<div class="lei-card-body">' +
        '<div class="lei-field" style="grid-column:1/-1"><label>LEI Code</label><span class="mono" style="font-size:13px;letter-spacing:.04em">' + lei + '</span></div>' +
        '<div class="lei-field"><label>Jurisdiction</label><span>' + (jurisdiction || country || '—') + '</span></div>' +
        '<div class="lei-field"><label>Legal Form</label><span>' + (legalForm || '—') + '</span></div>' +
        '<div class="lei-field"><label>Entity Category</label><span>' + (category || '—') + '</span></div>' +
        '<div class="lei-field"><label>Managing OU</label><span>' + (managingOU || '—') + '</span></div>' +
        '<div class="lei-field"><label>Registered Address</label><span style="font-size:11px">' + ([raddr.addressLines?.[0], raddr.city, raddr.country].filter(Boolean).join(', ') || addrLine || '—') + '</span></div>' +
      '</div>' +
      // Footer: dates + GLEIF link
      '<div class="lei-card-footer">' +
        '<div class="lei-footer-item">Registered <strong>' + (registered || '—') + '</strong></div>' +
        '<div class="lei-footer-item">Last updated <strong>' + (lastUpdate || '—') + '</strong></div>' +
        '<div class="lei-footer-item">Next renewal <strong>' + (nextRenewal || '—') + '</strong></div>' +
        '<div class="lei-footer-item" style="margin-left:auto">' +
          '<a href="https://search.gleif.org/#/record/' + lei + '" target="_blank" style="color:var(--accent);font-size:11px">View on GLEIF &rarr;</a>' +
        '</div>' +
      '</div>' +
      cbiHtml +
    '</div>';
  }).join('');
}

function quickLEI(q) {
  document.getElementById('leiQuery').value = q;
  fetchLEI();
}
document.getElementById('leiQuery').addEventListener('keydown', e => { if(e.key==='Enter') fetchLEI(); });

let leiLoaded = false;

function switchTab(t) {
  const order = ['cbi','aif','icav','lei'];
  document.querySelectorAll('.tab').forEach((el,i) => el.classList.toggle('active', order[i] === t));
  order.forEach(id => {
    document.getElementById('tab-' + id).classList.toggle('active', t === id);
  });
  if (t === 'lei' && !leiLoaded) {
    leiLoaded = true;
    autoLoadRecentLEIs();
  }
}

function switchSubTab(tabId, sub) {
  const subs = ['stats','results'];
  document.querySelectorAll('#tab-' + tabId + ' .sub-tab').forEach(el => {
    el.classList.toggle('active', el.dataset.sub === tabId + '-' + sub);
  });
  subs.forEach(s => {
    const el = document.getElementById(tabId + '-sub-' + s);
    if (el) el.classList.toggle('active', s === sub);
  });
}

init();
</script>
</body>
</html>"""

def main():
    os.makedirs(os.path.dirname(HTML_OUT), exist_ok=True)

    if not os.path.exists(CSV_PATH):
        print("WARNING: fund CSV not found — writing placeholder dashboard")
        df = pd.DataFrame(columns=["Fund Name", "Umbrella", "ManCo", "Depositary", "Auth_Date"])
    else:
        df = pd.read_csv(CSV_PATH)

    if not os.path.exists(AIF_CSV_PATH):
        print("WARNING: AIF CSV not found — AIF tab will be empty")
        aif_df = pd.DataFrame(columns=["Fund Name", "Umbrella", "ManCo", "Depositary", "Auth_Date"])
    else:
        aif_df = pd.read_csv(AIF_CSV_PATH)

    if not os.path.exists(ICAV_CSV_PATH):
        print("WARNING: ICAV CSV not found — ICAV tab will be empty")
        icav_df = pd.DataFrame(columns=["ICAV Name", "Reg Date", "Reg Number", "In Liquidation", "ETF Related"])
    else:
        icav_df = pd.read_csv(ICAV_CSV_PATH)

    html = build_html(df, aif_df, icav_df)
    with open(HTML_OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print("Dashboard written to", HTML_OUT, "(" + str(os.path.getsize(HTML_OUT)//1024) + " KB)")

if __name__ == "__main__":
    main()
