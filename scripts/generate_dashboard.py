"""
generate_dashboard.py
─────────────────────
Reads data/cbi_shadow_db.csv and writes docs/index.html.
No guessing — uses ManCo and Depositary exactly as parsed from the CBI PDF.
"""

import pandas as pd
import json
import os
from datetime import date

CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "cbi_shadow_db.csv")
HTML_OUT = os.path.join(os.path.dirname(__file__), "..", "docs", "index.html")
TODAY    = date.today().isoformat()

def build_html(df):
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

    records = df[["Fund Name", "ManCo", "Depositary", "Auth_Date", "is_etf"]].fillna("").to_dict(orient="records")
    data_js = json.dumps(records, separators=(",", ":"))

    # Top ManCos by ETF count
    manco_counts = df_etf[df_etf["ManCo"] != ""].groupby("ManCo").size().sort_values(ascending=False).head(8)
    manco_labels = json.dumps(list(manco_counts.index))
    manco_values = json.dumps(list(manco_counts.values.tolist()))

    # Top depositaries
    dep_counts = df_etf[df_etf["Depositary"] != ""].groupby("Depositary").size().sort_values(ascending=False).head(6)
    dep_labels = json.dumps(list(dep_counts.index))
    dep_values = json.dumps(list(dep_counts.values.tolist()))

    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ETF Intelligence — CBI Register</title>
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
.layout{display:grid;grid-template-columns:260px 1fr;min-height:calc(100vh - 120px)}
.sidebar{background:var(--surface);border-right:1px solid var(--border);padding:20px;display:flex;flex-direction:column;gap:16px}
.sidebar h3{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin-bottom:4px}
.filter-group{display:flex;flex-direction:column;gap:6px}
.filter-btn{background:var(--surface2);border:1px solid var(--border);color:var(--text);padding:7px 12px;border-radius:6px;cursor:pointer;font-size:12px;text-align:left;transition:.15s}
.filter-btn:hover,.filter-btn.active{border-color:var(--accent);color:var(--accent)}
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
.bar-track{flex:1;background:var(--surface2);border-radius:3px;height:8px}
.bar-fill{height:8px;border-radius:3px;transition:.4s}
.bar-count{font-size:11px;color:var(--muted);font-family:'DM Mono',monospace;width:30px;text-align:right}
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
.quick-btns{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:20px}
.quick-btn{background:var(--surface2);border:1px solid var(--border);color:var(--muted);padding:5px 12px;border-radius:20px;cursor:pointer;font-size:12px}
.quick-btn:hover{border-color:var(--accent);color:var(--accent)}
#leiLoading{display:none;color:var(--muted);padding:20px 0;font-size:13px}
.lei-card{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:12px 14px;display:grid;grid-template-columns:1fr auto auto auto;gap:12px;align-items:center;margin-bottom:8px}
.lei-name{font-weight:500;font-size:13px}
.lei-sub{font-size:11px;color:var(--muted);margin-top:2px}
.lei-code{font-family:'DM Mono',monospace;font-size:11px;color:var(--muted)}
.lei-date{font-size:11px;color:var(--muted)}
.lei-status-badge{font-size:10px;padding:3px 8px;border-radius:10px;font-weight:600}
.issued{background:#3fb95022;color:var(--green)}
.lapsed{background:#e05c2c22;color:#e05c2c}
</style>
</head>
<body>
<header class="header">
  <div class="logo"><div class="logo-dot"></div>ETF <span>Intelligence</span></div>
  <div class="header-meta">CBI Register &middot; Updated """ + TODAY + """</div>
</header>
<div class="tabs">
  <div class="tab active" onclick="switchTab('cbi')">CBI Register</div>
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
    <div class="stats-row">
      <div class="stat"><div class="stat-val">""" + str(total) + """</div><div class="stat-lbl">Total Funds</div></div>
      <div class="stat"><div class="stat-val">""" + str(total_etf) + """</div><div class="stat-lbl">ETFs</div></div>
      <div class="stat"><div class="stat-val">""" + str(new_30) + """</div><div class="stat-lbl">New ETFs (30d)</div></div>
      <div class="stat"><div class="stat-val">""" + str(new_90) + """</div><div class="stat-lbl">New ETFs (90d)</div></div>
      <div class="stat"><div class="stat-val">""" + str(ytd) + """</div><div class="stat-lbl">ETFs YTD """ + str(now.year) + """</div></div>
    </div>
    <div class="charts-row">
      <div class="chart-card"><h3>Top Management Companies (ETFs)</h3><div id="mancoChart"></div></div>
      <div class="chart-card"><h3>Depositary Market Share (ETFs)</h3><div id="depChart"></div></div>
    </div>
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
  </main>
</div>
</div>

<div id="tab-lei" class="tab-content">
<div class="lei-wrap">
  <div class="search-row">
    <input class="search-input" id="leiQuery" placeholder="Search by name or LEI code&hellip;" />
    <button class="search-btn" onclick="fetchLEI()">Search LEI</button>
  </div>
  <div class="quick-btns">
    <span style="font-size:12px;color:var(--muted);align-self:center;margin-right:4px">Quick:</span>
    <button class="quick-btn" onclick="quickLEI('BlackRock Asset Management Ireland')">BlackRock</button>
    <button class="quick-btn" onclick="quickLEI('iShares')">iShares</button>
    <button class="quick-btn" onclick="quickLEI('Invesco')">Invesco</button>
    <button class="quick-btn" onclick="quickLEI('Amundi')">Amundi</button>
    <button class="quick-btn" onclick="quickLEI('WisdomTree')">WisdomTree</button>
    <button class="quick-btn" onclick="quickLEI('VanEck')">VanEck</button>
    <button class="quick-btn" onclick="quickLEI('Franklin Templeton')">Franklin Templeton</button>
    <button class="quick-btn" onclick="quickLEI('State Street')">State Street / SPDR</button>
    <button class="quick-btn" onclick="quickLEI('DWS')">Xtrackers / DWS</button>
  </div>
  <div id="leiLoading">Searching GLEIF database&hellip;</div>
  <div id="leiResults"></div>
</div>
</div>

<script>
const ALL_DATA = """ + data_js + """;
const MANCO_LABELS = """ + manco_labels + """;
const MANCO_VALUES = """ + manco_values + """;
const DEP_LABELS   = """ + dep_labels + """;
const DEP_VALUES   = """ + dep_values + """;
const PER_PAGE = 50;
let filtered = [...ALL_DATA];
let page = 1;
let activeFilter = 'all';
const today = new Date('""" + TODAY + """');

function switchTab(t) {
  document.querySelectorAll('.tab').forEach((el,i) => el.classList.toggle('active',(i===0&&t==='cbi')||(i===1&&t==='lei')));
  document.getElementById('tab-cbi').classList.toggle('active',t==='cbi');
  document.getElementById('tab-lei').classList.toggle('active',t==='lei');
}

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
    '<td style="font-family:\'DM Mono\',monospace;font-size:12px">' + (r.Auth_Date||'') + '</td></tr>'
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
}

async function fetchLEI() {
  const q = document.getElementById('leiQuery').value.trim();
  if (!q) return;
  document.getElementById('leiLoading').style.display = 'block';
  document.getElementById('leiResults').innerHTML = '';
  try {
    const url = 'https://api.gleif.org/api/v1/lei-records?filter[entity.legalName]=' + encodeURIComponent(q) + '&page[size]=20';
    const data = await (await fetch(url)).json();
    renderLEI(data.data || []);
  } catch(e) {
    document.getElementById('leiResults').innerHTML = '<p style="color:#e05c2c">Error: '+e.message+'</p>';
  } finally {
    document.getElementById('leiLoading').style.display = 'none';
  }
}

function renderLEI(records) {
  if (!records.length) { document.getElementById('leiResults').innerHTML = '<p style="color:var(--muted);padding:20px 0">No results found.</p>'; return; }
  document.getElementById('leiResults').innerHTML =
    '<div style="font-size:12px;color:var(--muted);margin-bottom:12px">'+records.length+' result(s)</div>' +
    records.map(r => {
      const attr=r.attributes||{},entity=attr.entity||{},reg=attr.registration||{};
      const name=entity.legalName?.value||r.id,country=entity.legalAddress?.country||'';
      const lei=r.id||'',date=(reg.initialRegistrationDate||'').substring(0,10);
      const status=reg.status?.toLowerCase()==='issued'?'issued':'lapsed';
      return '<div class="lei-card"><div><div class="lei-name">'+name+'</div><div class="lei-sub">'+country+'</div></div>' +
             '<div class="lei-code">'+lei+'</div><div class="lei-date">'+date+'</div>' +
             '<div><span class="lei-status-badge '+status+'">'+status.toUpperCase()+'</span></div></div>';
    }).join('');
}

function quickLEI(q) { document.getElementById('leiQuery').value=q; fetchLEI(); }
document.getElementById('leiQuery').addEventListener('keydown',e=>{ if(e.key==='Enter') fetchLEI(); });
init();
</script>
</body>
</html>"""

def main():
    os.makedirs(os.path.dirname(HTML_OUT), exist_ok=True)

    if not os.path.exists(CSV_PATH):
        print("WARNING: CSV not found — writing placeholder dashboard")
        df = pd.DataFrame(columns=["Fund Name", "ManCo", "Depositary", "Auth_Date"])
    else:
        df = pd.read_csv(CSV_PATH)

    html = build_html(df)
    with open(HTML_OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print("Dashboard written to", HTML_OUT, "(" + str(os.path.getsize(HTML_OUT)//1024) + " KB)")

if __name__ == "__main__":
    main()
