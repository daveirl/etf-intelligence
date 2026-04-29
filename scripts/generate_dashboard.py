"""
generate_dashboard.py
─────────────────────
Reads data/cbi_shadow_db.csv and writes docs/index.html.
Run locally or via GitHub Actions after cbi_shadow_sync_v2.py.

Usage:
    python scripts/generate_dashboard.py
"""

import pandas as pd
import json
import os
from datetime import datetime, date

CSV_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'cbi_shadow_db.csv')
HTML_OUT = os.path.join(os.path.dirname(__file__), '..', 'docs', 'index.html')
TODAY    = date.today().isoformat()

PLATFORM_MAP = [
    (['iShares'],          'BlackRock UCITS ETF ICAV / iShares plc',        'BlackRock Asset Management Ireland Limited',          'State Street Custodial Services (Ireland) Limited'),
    (['Xtrackers'],        'Xtrackers (IE) plc / DWS Xtrackers ICAV',       'DWS Investment S.A.',                                 'State Street Bank International GmbH'),
    (['Invesco'],          'Invesco Markets plc / Invesco Markets II plc',   'Invesco Investment Management Limited',               'The Bank of New York Mellon SA/NV'),
    (['SPDR'],             'SPDR ETFs Ireland plc',                          'State Street Global Advisors Europe Limited',         'State Street Custodial Services (Ireland) Limited'),
    (['Amundi'],           'Amundi UCITS ETF ICAV / Amundi Index Solutions', 'Amundi Asset Management',                             'CACEIS Bank, Ireland Branch'),
    (['Vanguard'],         'Vanguard Funds plc',                             'Vanguard Group (Ireland) Limited',                    'Brown Brothers Harriman Trustee Services (Ireland) Limited'),
    (['WisdomTree'],       'WisdomTree UCITS ICAV',                          'WisdomTree Management Limited',                       'Citi Depositary Services Ireland DAC'),
    (['VanEck'],           'VanEck UCITS ETFs plc',                          'VanEck Asset Management B.V.',                        'State Street Custodial Services (Ireland) Limited'),
    (['Franklin'],         'Franklin Templeton ETF ICAV',                    'Franklin Templeton International Services S.à r.l.', 'The Bank of New York Mellon SA/NV'),
    (['Goldman Sachs'],    'Goldman Sachs ETF UCITS ICAV',                   'Goldman Sachs Asset Management International',        'State Street Custodial Services (Ireland) Limited'),
    (['JPMorgan', 'J.P.'], 'JPMorgan ETFs (Ireland) ICAV',                   'JPMorgan Asset Management (Europe) S.à r.l.',        'The Bank of New York Mellon SA/NV'),
    (['PIMCO'],            'PIMCO Fixed Income Source ETFs plc',             'PIMCO Europe GmbH',                                  'State Street Custodial Services (Ireland) Limited'),
    (['Fidelity'],         'Fidelity UCITS ICAV',                            'FIL Fund Management (Ireland) Limited',               'The Bank of New York Mellon SA/NV'),
    (['HANetf'],           'HANetf ICAV',                                    'HANetf Limited',                                     'The Bank of New York Mellon SA/NV'),
    (['L&G', 'Legal'],     'L&G UCITS ETF plc',                              'Legal & General UCITS ETF plc',                      'The Bank of New York Mellon SA/NV'),
    (['First Trust'],      'First Trust Global Funds plc',                   'First Trust Global Portfolios Limited',               'The Bank of New York Mellon SA/NV'),
    (['HSBC'],             'HSBC ETFs plc',                                  'HSBC Global Asset Management (UK) Limited',           'The Bank of New York Mellon SA/NV'),
    (['UBS'],              'UBS ETF plc / UBS ETFs plc',                     'UBS Asset Management (UK) Ltd',                      'State Street Custodial Services (Ireland) Limited'),
]


def enrich_row(row):
    name = str(row.get('Fund Name', ''))
    for keywords, platform, manco, dep in PLATFORM_MAP:
        if any(kw.lower() in name.lower() for kw in keywords):
            row['Platform']   = row.get('Platform') or platform
            row['ManCo']      = row.get('ManCo')    or manco
            row['Depositary'] = row.get('Depositary') or dep
            return row
    row['Platform']   = row.get('Platform')   or 'Other'
    row['ManCo']      = row.get('ManCo')       or 'Unknown'
    row['Depositary'] = row.get('Depositary')  or 'Unknown'
    return row


def build_html(df: pd.DataFrame) -> str:
    df['is_etf'] = df['Fund Name'].str.contains('ETF', case=False, na=False)
    df['Auth_Date'] = pd.to_datetime(df['Auth_Date'], errors='coerce')
    now = pd.Timestamp(TODAY)
    df_etf = df[df['is_etf']]

    total        = len(df)
    total_etf    = len(df_etf)
    new_30       = len(df_etf[df_etf['Auth_Date'] >= now - pd.Timedelta(days=30)])
    new_90       = len(df_etf[df_etf['Auth_Date'] >= now - pd.Timedelta(days=90)])
    ytd_2025     = len(df_etf[df_etf['Auth_Date'].dt.year == 2025])
    ytd_2026     = len(df_etf[df_etf['Auth_Date'].dt.year == 2026])

    df['Auth_Date'] = df['Auth_Date'].dt.strftime('%Y-%m-%d').fillna('')
    records = df[['Fund Name','Platform','ManCo','Depositary','Auth_Date','is_etf']].fillna('').to_dict(orient='records')
    data_js = json.dumps(records, separators=(',',':'))

    # Top issuers chart data
    issuer_counts = (
        df_etf.groupby('Platform').size()
        .sort_values(ascending=False).head(8)
    )
    chart_labels = json.dumps(list(issuer_counts.index))
    chart_values = json.dumps(list(issuer_counts.values.tolist()))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ETF Intelligence — CBI Register</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Mono:wght@400;500&family=DM+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
:root{{--bg:#0d1117;--surface:#161b22;--surface2:#1c2330;--border:#30363d;--accent:#f0b429;--green:#3fb950;--text:#e6edf3;--muted:#8b949e}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);font-family:'DM Sans',sans-serif;font-size:14px;min-height:100vh}}
.header{{background:var(--surface);border-bottom:1px solid var(--border);padding:0 32px;display:flex;align-items:center;justify-content:space-between;height:60px;position:sticky;top:0;z-index:100}}
.logo{{font-family:'DM Serif Display',serif;font-size:20px;display:flex;align-items:center;gap:10px}}
.logo-dot{{width:8px;height:8px;background:var(--accent);border-radius:50%}}
.logo span{{color:var(--accent)}}
.header-meta{{font-size:12px;color:var(--muted)}}
.tabs{{display:flex;gap:0;border-bottom:1px solid var(--border);background:var(--surface);padding:0 32px}}
.tab{{padding:14px 20px;cursor:pointer;font-size:13px;font-weight:500;color:var(--muted);border-bottom:2px solid transparent;transition:.2s}}
.tab.active{{color:var(--accent);border-bottom-color:var(--accent)}}
.tab-content{{display:none}}.tab-content.active{{display:block}}
.layout{{display:grid;grid-template-columns:260px 1fr;gap:0;min-height:calc(100vh - 120px)}}
.sidebar{{background:var(--surface);border-right:1px solid var(--border);padding:20px;display:flex;flex-direction:column;gap:16px}}
.sidebar h3{{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin-bottom:4px}}
.filter-group{{display:flex;flex-direction:column;gap:6px}}
.filter-btn{{background:var(--surface2);border:1px solid var(--border);color:var(--text);padding:7px 12px;border-radius:6px;cursor:pointer;font-size:12px;text-align:left;transition:.15s}}
.filter-btn:hover,.filter-btn.active{{border-color:var(--accent);color:var(--accent)}}
select,input[type=date],input[type=text]{{background:var(--surface2);border:1px solid var(--border);color:var(--text);padding:7px 10px;border-radius:6px;font-size:12px;width:100%;outline:none}}
select:focus,input:focus{{border-color:var(--accent)}}
.main{{padding:24px;overflow:auto}}
.stats-row{{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin-bottom:24px}}
.stat{{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:14px;text-align:center}}
.stat-val{{font-size:22px;font-weight:600;color:var(--accent);font-family:'DM Mono',monospace}}
.stat-lbl{{font-size:11px;color:var(--muted);margin-top:4px}}
.table-wrap{{background:var(--surface);border:1px solid var(--border);border-radius:8px;overflow:hidden}}
.table-header{{padding:14px 16px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--border)}}
.table-header h2{{font-size:14px;font-weight:600}}
.export-btn{{background:var(--accent);color:#000;border:none;padding:6px 14px;border-radius:5px;cursor:pointer;font-size:12px;font-weight:600}}
table{{width:100%;border-collapse:collapse}}
th{{background:var(--surface2);padding:10px 14px;text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);position:sticky;top:0}}
td{{padding:9px 14px;border-bottom:1px solid var(--border);font-size:13px;vertical-align:middle}}
tr:last-child td{{border-bottom:none}}
tr:hover td{{background:var(--surface2)}}
.etf-badge{{background:#f0b42922;border:1px solid #f0b42966;color:var(--accent);font-size:10px;padding:2px 7px;border-radius:10px;font-weight:600;white-space:nowrap}}
.pagination{{display:flex;align-items:center;gap:8px;padding:12px 16px;border-top:1px solid var(--border)}}
.page-btn{{background:var(--surface2);border:1px solid var(--border);color:var(--text);padding:5px 10px;border-radius:5px;cursor:pointer;font-size:12px}}
.page-btn:hover{{border-color:var(--accent)}}
.page-info{{font-size:12px;color:var(--muted)}}
.charts-row{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:24px}}
.chart-card{{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:16px}}
.chart-card h3{{font-size:13px;font-weight:600;margin-bottom:14px}}
.bar-row{{display:flex;align-items:center;gap:10px;margin-bottom:7px}}
.bar-label{{font-size:11px;color:var(--muted);width:160px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex-shrink:0}}
.bar-track{{flex:1;background:var(--surface2);border-radius:3px;height:8px}}
.bar-fill{{background:var(--accent);height:8px;border-radius:3px;transition:.4s}}
.bar-count{{font-size:11px;color:var(--muted);font-family:'DM Mono',monospace;width:30px;text-align:right}}
/* LEI tab */
.lei-wrap{{padding:32px}}
.search-row{{display:flex;gap:10px;margin-bottom:16px}}
.search-input{{flex:1;background:var(--surface);border:1px solid var(--border);color:var(--text);padding:10px 14px;border-radius:8px;font-size:14px;outline:none}}
.search-input:focus{{border-color:var(--accent)}}
.search-btn{{background:var(--accent);color:#000;border:none;padding:10px 20px;border-radius:8px;cursor:pointer;font-weight:600;font-size:14px}}
.quick-btns{{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:20px}}
.quick-btn{{background:var(--surface2);border:1px solid var(--border);color:var(--muted);padding:5px 12px;border-radius:20px;cursor:pointer;font-size:12px}}
.quick-btn:hover{{border-color:var(--accent);color:var(--accent)}}
.lei-stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px}}
.lei-card{{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:12px 14px;display:grid;grid-template-columns:1fr auto auto auto;gap:12px;align-items:center;margin-bottom:8px}}
.lei-name{{font-weight:500;font-size:13px}}
.lei-sub{{font-size:11px;color:var(--muted);margin-top:2px}}
.lei-code{{font-family:'DM Mono',monospace;font-size:11px;color:var(--muted)}}
.lei-date{{font-size:11px;color:var(--muted)}}
.lei-status-badge{{font-size:10px;padding:3px 8px;border-radius:10px;font-weight:600}}
.issued{{background:#3fb95022;color:var(--green)}}
.lapsed{{background:#e05c2c22;color:#e05c2c}}
#leiLoading{{display:none;color:var(--muted);padding:20px 0;font-size:13px}}
</style>
</head>
<body>
<header class="header">
  <div class="logo"><div class="logo-dot"></div>ETF <span>Intelligence</span></div>
  <div class="header-meta">CBI Register · Updated {TODAY}</div>
</header>
<div class="tabs">
  <div class="tab active" onclick="switchTab('cbi')">CBI Register</div>
  <div class="tab" onclick="switchTab('lei')">LEI Lookup</div>
</div>

<!-- CBI TAB -->
<div id="tab-cbi" class="tab-content active">
<div class="layout">
  <aside class="sidebar">
    <div class="filter-group">
      <h3>Fund Type</h3>
      <button class="filter-btn active" onclick="setFilter('type','all',this)">All Funds</button>
      <button class="filter-btn" onclick="setFilter('type','etf',this)">ETFs Only</button>
      <button class="filter-btn" onclick="setFilter('type','new30',this)">New (30d)</button>
      <button class="filter-btn" onclick="setFilter('type','new90',this)">New (90d)</button>
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
      <h3>Platform</h3>
      <select id="selPlatform" onchange="applyFilters()"><option value="">All Platforms</option></select>
    </div>
    <div class="filter-group">
      <h3>Management Co.</h3>
      <select id="selManco" onchange="applyFilters()"><option value="">All ManCos</option></select>
    </div>
    <div class="filter-group">
      <h3>Search</h3>
      <input type="text" id="searchBox" placeholder="Fund name…" oninput="applyFilters()">
    </div>
  </aside>
  <main class="main">
    <div class="stats-row">
      <div class="stat"><div class="stat-val" id="s-total">{total}</div><div class="stat-lbl">Total Funds</div></div>
      <div class="stat"><div class="stat-val" id="s-etf">{total_etf}</div><div class="stat-lbl">ETFs</div></div>
      <div class="stat"><div class="stat-val" id="s-30">{new_30}</div><div class="stat-lbl">New ETFs (30d)</div></div>
      <div class="stat"><div class="stat-val" id="s-90">{new_90}</div><div class="stat-lbl">New ETFs (90d)</div></div>
      <div class="stat"><div class="stat-val" id="s-2025">{ytd_2025}</div><div class="stat-lbl">2025 ETFs</div></div>
      <div class="stat"><div class="stat-val" id="s-2026">{ytd_2026}</div><div class="stat-lbl">2026 ETFs</div></div>
    </div>
    <div class="charts-row">
      <div class="chart-card"><h3>Top Issuers by ETF Count</h3><div id="issuerChart"></div></div>
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
            <th>Fund Name</th><th>Platform / ICAV</th><th>Management Co.</th>
            <th>Depositary</th><th>Auth Date</th>
          </tr></thead>
          <tbody id="tableBody"></tbody>
        </table>
      </div>
      <div class="pagination">
        <button class="page-btn" onclick="changePage(-1)">← Prev</button>
        <span class="page-info" id="pageInfo"></span>
        <button class="page-btn" onclick="changePage(1)">Next →</button>
      </div>
    </div>
  </main>
</div>
</div>

<!-- LEI TAB -->
<div id="tab-lei" class="tab-content">
<div class="lei-wrap">
  <div class="search-row">
    <input class="search-input" id="leiQuery" placeholder="Search by name, LEI code, or keyword…" />
    <button class="search-btn" onclick="fetchLEI()">Search LEI</button>
  </div>
  <div class="quick-btns">
    <span style="font-size:12px;color:var(--muted);align-self:center;margin-right:4px">Quick search:</span>
    <button class="quick-btn" onclick="quickLEI('BlackRock Asset Management Ireland')">BlackRock</button>
    <button class="quick-btn" onclick="quickLEI('iShares')">iShares</button>
    <button class="quick-btn" onclick="quickLEI('Invesco')">Invesco</button>
    <button class="quick-btn" onclick="quickLEI('Amundi')">Amundi</button>
    <button class="quick-btn" onclick="quickLEI('WisdomTree')">WisdomTree</button>
    <button class="quick-btn" onclick="quickLEI('VanEck')">VanEck</button>
    <button class="quick-btn" onclick="quickLEI('Franklin Templeton')">Franklin Templeton</button>
    <button class="quick-btn" onclick="quickLEI('SPDR State Street')">SPDR / State Street</button>
    <button class="quick-btn" onclick="quickLEI('Xtrackers DWS')">Xtrackers / DWS</button>
  </div>
  <div id="leiLoading">Searching GLEIF database…</div>
  <div id="leiResults"></div>
</div>
</div>

<script>
const ALL_DATA = {data_js};
const PER_PAGE = 50;
let filtered = [...ALL_DATA];
let page = 1;
let activeTypeFilter = 'all';
const today = new Date('{TODAY}');

function switchTab(t) {{
  document.querySelectorAll('.tab').forEach((el,i) => el.classList.toggle('active', (i===0&&t==='cbi')||(i===1&&t==='lei')));
  document.getElementById('tab-cbi').classList.toggle('active', t==='cbi');
  document.getElementById('tab-lei').classList.toggle('active', t==='lei');
}}

function init() {{
  const platforms = [...new Set(ALL_DATA.map(r=>r.Platform).filter(Boolean))].sort();
  const mancos    = [...new Set(ALL_DATA.map(r=>r.ManCo).filter(Boolean))].sort();
  const pSel = document.getElementById('selPlatform');
  const mSel = document.getElementById('selManco');
  platforms.forEach(p => {{ const o=document.createElement('option'); o.value=o.textContent=p; pSel.appendChild(o); }});
  mancos.forEach(m => {{ const o=document.createElement('option'); o.value=o.textContent=m; mSel.appendChild(o); }});
  applyFilters();
  buildCharts();
}}

function setFilter(type, val, btn) {{
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  activeTypeFilter = val;
  page = 1;
  applyFilters();
}}

function applyFilters() {{
  const dFrom   = document.getElementById('dFrom').value;
  const dTo     = document.getElementById('dTo').value;
  const platform= document.getElementById('selPlatform').value;
  const manco   = document.getElementById('selManco').value;
  const search  = document.getElementById('searchBox').value.toLowerCase();
  filtered = ALL_DATA.filter(r => {{
    if (activeTypeFilter==='etf'   && !r.is_etf) return false;
    if (activeTypeFilter==='new30' && (!r.is_etf || !r.Auth_Date || new Date(r.Auth_Date) < new Date(today - 30*864e5))) return false;
    if (activeTypeFilter==='new90' && (!r.is_etf || !r.Auth_Date || new Date(r.Auth_Date) < new Date(today - 90*864e5))) return false;
    if (dFrom && r.Auth_Date && r.Auth_Date < dFrom) return false;
    if (dTo   && r.Auth_Date && r.Auth_Date > dTo)   return false;
    if (platform && r.Platform !== platform) return false;
    if (manco    && r.ManCo    !== manco)    return false;
    if (search && !r['Fund Name'].toLowerCase().includes(search)) return false;
    return true;
  }});
  renderTable();
}}

function renderTable() {{
  const start = (page-1)*PER_PAGE;
  const rows  = filtered.slice(start, start+PER_PAGE);
  document.getElementById('rowCount').textContent = `(${{filtered.length.toLocaleString()}} funds)`;
  document.getElementById('pageInfo').textContent  = `Page ${{page}} of ${{Math.ceil(filtered.length/PER_PAGE)||1}}`;
  document.getElementById('tableBody').innerHTML = rows.map(r =>
    `<tr>
      <td>${{r['Fund Name']}}${{r.is_etf?' <span class="etf-badge">ETF</span>':''}}</td>
      <td>${{r.Platform||''}}</td>
      <td>${{r.ManCo||''}}</td>
      <td>${{r.Depositary||''}}</td>
      <td style="font-family:'DM Mono',monospace;font-size:12px">${{r.Auth_Date||''}}</td>
    </tr>`
  ).join('');
}}

function changePage(d) {{
  const max = Math.ceil(filtered.length/PER_PAGE)||1;
  page = Math.max(1,Math.min(max, page+d));
  renderTable();
}}

function exportCSV() {{
  const cols = ['Fund Name','Platform','ManCo','Depositary','Auth_Date'];
  const rows = [cols.join(','), ...filtered.map(r =>
    cols.map(c => `"${{(r[c]||'').replace(/"/g,'""')}}"`).join(',')
  )];
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([rows.join('\\n')], {{type:'text/csv'}}));
  a.download = `cbi_register_${{'{TODAY}'}}.csv`;
  a.click();
}}

function buildCharts() {{
  // Issuer chart
  const issuerData = {chart_labels}.map((label, i) => ({{label, val: {chart_values}[i]}}));
  const maxIssuer  = Math.max(...issuerData.map(d => d.val));
  document.getElementById('issuerChart').innerHTML = issuerData.map(d =>
    `<div class="bar-row">
      <div class="bar-label" title="${{d.label}}">${{d.label}}</div>
      <div class="bar-track"><div class="bar-fill" style="width:${{(d.val/maxIssuer*100).toFixed(1)}}%"></div></div>
      <div class="bar-count">${{d.val}}</div>
    </div>`
  ).join('');

  // Depositary chart
  const etfs = ALL_DATA.filter(r => r.is_etf);
  const depCounts = {{}};
  etfs.forEach(r => {{ if(r.Depositary) depCounts[r.Depositary] = (depCounts[r.Depositary]||0)+1; }});
  const depData = Object.entries(depCounts).sort((a,b)=>b[1]-a[1]).slice(0,6);
  const maxDep  = Math.max(...depData.map(d=>d[1]));
  document.getElementById('depChart').innerHTML = depData.map(([label,val]) =>
    `<div class="bar-row">
      <div class="bar-label" title="${{label}}">${{label}}</div>
      <div class="bar-track"><div class="bar-fill" style="width:${{(val/maxDep*100).toFixed(1)}}%;background:#3fb950"></div></div>
      <div class="bar-count">${{val}}</div>
    </div>`
  ).join('');
}}

// ── LEI ───────────────────────────────────────────────────────────────────────
async function fetchLEI() {{
  const q = document.getElementById('leiQuery').value.trim();
  if (!q) return;
  document.getElementById('leiLoading').style.display = 'block';
  document.getElementById('leiResults').innerHTML = '';
  try {{
    const url = `https://api.gleif.org/api/v1/lei-records?filter[entity.legalName]=${{encodeURIComponent(q)}}&page[size]=20`;
    const res  = await fetch(url);
    const data = await res.json();
    renderLEI(data.data || []);
  }} catch(e) {{
    document.getElementById('leiResults').innerHTML = `<p style="color:#e05c2c">Error: ${{e.message}}</p>`;
  }} finally {{
    document.getElementById('leiLoading').style.display = 'none';
  }}
}}

function renderLEI(records) {{
  if (!records.length) {{
    document.getElementById('leiResults').innerHTML = '<p style="color:var(--muted);padding:20px 0">No results found.</p>';
    return;
  }}
  const header = `<div style="font-size:12px;color:var(--muted);margin-bottom:12px">${{records.length}} result(s)</div>`;
  const rows = records.map(r => {{
    const attr   = r.attributes || {{}};
    const entity = attr.entity || {{}};
    const reg    = attr.registration || {{}};
    const name   = entity.legalName?.value || r.id;
    const country= entity.legalAddress?.country || '';
    const lei    = r.id || '';
    const date   = (reg.initialRegistrationDate||'').substring(0,10);
    const status = reg.status?.toLowerCase() === 'issued' ? 'issued' : 'lapsed';
    const sc     = status === 'issued' ? 'issued' : 'lapsed';
    return `<div class="lei-card">
      <div><div class="lei-name">${{name}}</div><div class="lei-sub">${{country}}</div></div>
      <div class="lei-code">${{lei}}</div>
      <div class="lei-date">${{date}}</div>
      <div><span class="lei-status-badge ${{sc}}">${{status.toUpperCase()}}</span></div>
    </div>`;
  }}).join('');
  document.getElementById('leiResults').innerHTML = header + rows;
}}

function quickLEI(q) {{
  document.getElementById('leiQuery').value = q;
  fetchLEI();
}}

document.getElementById('leiQuery').addEventListener('keydown', e => {{ if(e.key==='Enter') fetchLEI(); }});
init();
</script>
</body>
</html>"""


def main():
    os.makedirs(os.path.dirname(HTML_OUT), exist_ok=True)

    if not os.path.exists(CSV_PATH):
        print(f"WARNING: {CSV_PATH} not found — writing placeholder dashboard")
        df = pd.DataFrame(columns=['Fund Name','Platform','ManCo','Depositary','Auth_Date','First_Seen'])
    else:
        df = pd.read_csv(CSV_PATH)
        df = pd.DataFrame([enrich_row(r) for r in df.to_dict(orient='records')])

    html = build_html(df)
    with open(HTML_OUT, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"Dashboard written → {HTML_OUT}  ({os.path.getsize(HTML_OUT)//1024} KB)")


if __name__ == '__main__':
    main()
