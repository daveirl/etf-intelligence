"""
generate_dashboard.py
─────────────────────
Reads data/cbi_shadow_db.csv + data/icav_db.csv and writes docs/index.html.
Run locally or via GitHub Actions after cbi_shadow_sync_v2.py and icav_sync.py.
"""

import pandas as pd
import json
import os
from datetime import datetime

SCRIPT_DIR = os.path.dirname(__file__)
CSV_PATH   = os.path.join(SCRIPT_DIR, '..', 'data', 'cbi_shadow_db.csv')
ICAV_PATH  = os.path.join(SCRIPT_DIR, '..', 'data', 'icav_db.csv')
HTML_OUT   = os.path.join(SCRIPT_DIR, '..', 'docs', 'index.html')

EU_EEA = {'IE','LU','DE','FR','NL','SE','DK','AT','BE','FI','IT','ES','PT',
           'PL','CZ','HU','SK','RO','BG','HR','SI','EE','LV','LT','CY','MT','GR','NO','IS','LI','CH'}


def build_html(df, icav_df):
    records      = df.fillna('').to_dict(orient='records')
    icav_records = icav_df.fillna('').to_dict(orient='records')
    data_json    = json.dumps(records,      separators=(',', ':'))
    icav_json    = json.dumps(icav_records, separators=(',', ':'))

    generated_at = datetime.now().strftime('%Y-%m-%d %H:%M UTC')
    total        = len(df)
    etf_count    = int(df['Fund Name'].str.contains('ETF', case=False, na=False).sum())
    icav_total   = len(icav_df)
    icav_etf     = int(icav_df['ETF Related'].eq('Yes').sum()) if 'ETF Related' in icav_df.columns else 0
    icav_liq     = int(icav_df['In Liquidation'].eq('Yes').sum()) if 'In Liquidation' in icav_df.columns else 0

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ETF Intelligence</title>
<style>
:root {{
  --bg:#09090b; --s1:#111113; --s2:#18181b; --s3:#27272a;
  --border:#3f3f46; --accent:#eab308; --blue:#3b82f6;
  --green:#22c55e; --red:#ef4444; --text:#fafafa; --muted:#71717a;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);font-family:system-ui,sans-serif;font-size:13px;height:100vh;display:flex;flex-direction:column;overflow:hidden}}
.topbar{{background:var(--s1);border-bottom:1px solid var(--border);display:flex;align-items:center;padding:0 24px;height:52px;flex-shrink:0;gap:16px}}
.brand{{font-weight:800;font-size:16px;letter-spacing:-.5px;display:flex;align-items:center;gap:8px}}
.brand-dot{{width:7px;height:7px;background:var(--accent);border-radius:50%}}
.brand em{{color:var(--accent);font-style:normal}}
.tabs{{display:flex;gap:2px}}
.tab{{padding:6px 16px;border-radius:5px;cursor:pointer;font-weight:600;font-size:12px;color:var(--muted);border:1px solid transparent;background:none;transition:all .15s}}
.tab:hover{{color:var(--text);background:var(--s2)}}
.tab.active{{color:var(--accent);background:#eab30815;border-color:#eab30840}}
.meta{{margin-left:auto;font-size:11px;color:var(--muted)}}
.main{{display:flex;flex:1;overflow:hidden}}
/* ── CBI sidebar ── */
.sidebar{{width:280px;flex-shrink:0;background:var(--s1);border-right:1px solid var(--border);display:flex;flex-direction:column;padding:16px;gap:12px;overflow-y:auto}}
.content{{flex:1;overflow:hidden;display:flex;flex-direction:column}}
.search-box{{background:var(--s2);border:1px solid var(--border);border-radius:8px;padding:9px 12px;font-size:13px;color:var(--text);width:100%;outline:none}}
.search-box:focus{{border-color:var(--accent)}}
.filter-label{{font-size:11px;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.5px}}
select{{background:var(--s2);border:1px solid var(--border);border-radius:6px;color:var(--text);padding:7px 10px;font-size:12px;width:100%;outline:none;cursor:pointer}}
.stats-row{{display:flex;gap:8px}}
.stat-card{{flex:1;background:var(--s2);border:1px solid var(--border);border-radius:8px;padding:10px 12px}}
.stat-val{{font-size:20px;font-weight:700;color:var(--accent)}}
.stat-lbl{{font-size:10px;color:var(--muted);margin-top:2px}}
.table-wrap{{flex:1;overflow:auto}}
table{{width:100%;border-collapse:collapse}}
th{{background:var(--s1);border-bottom:1px solid var(--border);padding:9px 14px;text-align:left;font-size:11px;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.4px;cursor:pointer;white-space:nowrap;position:sticky;top:0;z-index:1}}
th:hover{{color:var(--text)}}
td{{padding:8px 14px;border-bottom:1px solid #27272a55;vertical-align:middle}}
tr:hover td{{background:var(--s2)}}
.badge{{display:inline-block;padding:2px 7px;border-radius:4px;font-size:10px;font-weight:700;letter-spacing:.3px}}
.badge-etf{{background:#eab30820;color:var(--accent);border:1px solid #eab30840}}
.badge-other{{background:#3f3f4620;color:var(--muted);border:1px solid #3f3f46}}
.badge-liq{{background:#ef444420;color:var(--red);border:1px solid #ef444440}}
.badge-new{{background:#22c55e20;color:var(--green);border:1px solid #22c55e40}}
.status-bar{{padding:8px 16px;background:var(--s1);border-top:1px solid var(--border);font-size:11px;color:var(--muted);flex-shrink:0}}
/* ── LEI tab ── */
#leiPane{{display:none;flex:1;overflow:hidden;flex-direction:column}}
.lei-toolbar{{display:flex;align-items:center;gap:10px;padding:16px;background:var(--s1);border-bottom:1px solid var(--border);flex-shrink:0;flex-wrap:wrap}}
.lei-search-box{{background:var(--s2);border:1px solid var(--border);border-radius:8px;padding:9px 12px;font-size:13px;color:var(--text);width:280px;outline:none}}
.lei-search-box:focus{{border-color:var(--accent)}}
.lei-btn{{background:var(--accent);color:#000;border:none;border-radius:6px;padding:8px 16px;font-weight:700;font-size:12px;cursor:pointer}}
.quick-btns{{display:flex;flex-wrap:wrap;gap:6px;align-items:center}}
.quick-btn{{background:var(--s2);border:1px solid var(--border);border-radius:5px;color:var(--muted);padding:5px 10px;font-size:11px;cursor:pointer;font-weight:600}}
.quick-btn:hover{{color:var(--text);border-color:var(--accent)}}
.lei-results{{flex:1;overflow:auto;padding:16px;display:flex;flex-direction:column;gap:12px}}
.lei-section-label{{font-size:11px;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px}}
.lei-card{{background:var(--s2);border:1px solid var(--border);border-radius:10px;overflow:hidden}}
.lei-card-header{{display:flex;align-items:center;justify-content:space-between;padding:14px 16px;gap:12px}}
.lei-card-title{{font-weight:700;font-size:15px;color:var(--text)}}
.lei-card-sub{{font-size:11px;color:var(--muted);margin-top:3px}}
.lei-status-badge{{padding:3px 10px;border-radius:20px;font-size:10px;font-weight:700;letter-spacing:.3px;white-space:nowrap}}
.lei-status-badge.issued{{background:#22c55e20;color:var(--green);border:1px solid #22c55e40}}
.lei-status-badge.lapsed{{background:#ef444420;color:#ef4444;border:1px solid #ef444440}}
.lei-card-body{{display:grid;grid-template-columns:repeat(3,1fr);gap:0;border-top:1px solid var(--border)}}
.lei-field{{padding:10px 16px;border-right:1px solid var(--border);border-bottom:1px solid var(--border)}}
.lei-field:nth-child(3n){{border-right:none}}
.lei-field label{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.4px;display:block;margin-bottom:3px}}
.lei-field span{{font-size:12px;color:var(--text)}}
.mono{{font-family:monospace;font-size:11px;letter-spacing:.5px}}
.lei-card-footer{{display:flex;gap:16px;padding:10px 16px;background:var(--s1);border-top:1px solid var(--border);flex-wrap:wrap}}
.lei-footer-item{{font-size:11px;color:var(--muted)}}
.lei-footer-item strong{{color:var(--text)}}
.lei-cbi-match{{background:#eab30810;border-top:1px solid #eab30830;padding:10px 16px}}
.lei-cbi-row{{display:flex;justify-content:space-between;font-size:11px;color:var(--muted)}}
/* ── ICAV tab ── */
#icavPane{{display:none;flex:1;overflow:hidden;flex-direction:column}}
.icav-layout{{display:flex;flex:1;overflow:hidden}}
.icav-sidebar{{width:280px;flex-shrink:0;background:var(--s1);border-right:1px solid var(--border);padding:16px;display:flex;flex-direction:column;gap:12px;overflow-y:auto}}
.icav-content{{flex:1;overflow:hidden;display:flex;flex-direction:column}}
.icav-stats{{display:flex;gap:8px;padding:12px 16px;background:var(--s1);border-bottom:1px solid var(--border);flex-shrink:0}}
.icav-stat{{flex:1;background:var(--s2);border:1px solid var(--border);border-radius:8px;padding:8px 12px;text-align:center}}
.icav-stat-val{{font-size:18px;font-weight:700;color:var(--accent)}}
.icav-stat-lbl{{font-size:10px;color:var(--muted);margin-top:1px}}
</style>
</head>
<body>

<div class="topbar">
  <div class="brand"><div class="brand-dot"></div><em>ETF</em> Intelligence</div>
  <div class="tabs">
    <button class="tab active" id="tabCbi"  onclick="switchTab('cbi')">CBI Register</button>
    <button class="tab"        id="tabLei"  onclick="switchTab('lei')">LEI Lookup</button>
    <button class="tab"        id="tabIcav" onclick="switchTab('icav')">ICAV Register</button>
  </div>
  <div class="meta">Generated {generated_at} &nbsp;·&nbsp; {total:,} UCITS funds &nbsp;·&nbsp; {etf_count:,} ETFs &nbsp;·&nbsp; {icav_total:,} ICAVs</div>
</div>

<div class="main">

  <!-- ════════════════ CBI PANE ════════════════ -->
  <div id="cbiPane" style="display:flex;flex:1;overflow:hidden">
    <div class="sidebar">
      <input class="search-box" id="searchBox" placeholder="Search funds…" oninput="applyFilters()">
      <div>
        <div class="filter-label" style="margin-bottom:6px">Type</div>
        <select id="filterType" onchange="applyFilters()">
          <option value="all">All funds</option>
          <option value="etf">ETFs only</option>
          <option value="other">Non-ETF only</option>
        </select>
      </div>
      <div>
        <div class="filter-label" style="margin-bottom:6px">ManCo</div>
        <select id="filterManco" onchange="applyFilters()"><option value="">All ManCos</option></select>
      </div>
      <div>
        <div class="filter-label" style="margin-bottom:6px">Depositary</div>
        <select id="filterDep" onchange="applyFilters()"><option value="">All Depositaries</option></select>
      </div>
      <div>
        <div class="filter-label" style="margin-bottom:6px">Year authorised</div>
        <select id="filterYear" onchange="applyFilters()"><option value="">All years</option></select>
      </div>
      <div class="stats-row">
        <div class="stat-card"><div class="stat-val" id="statVisible">—</div><div class="stat-lbl">Shown</div></div>
        <div class="stat-card"><div class="stat-val" id="statEtf">—</div><div class="stat-lbl">ETFs</div></div>
      </div>
    </div>
    <div class="content">
      <div class="table-wrap">
        <table id="mainTable">
          <thead>
            <tr>
              <th onclick="sortBy('Fund Name')">Fund Name ↕</th>
              <th onclick="sortBy('ManCo')">ManCo ↕</th>
              <th onclick="sortBy('Depositary')">Depositary ↕</th>
              <th onclick="sortBy('Auth_Date')">Auth Date ↕</th>
              <th onclick="sortBy('First_Seen')">First Seen ↕</th>
              <th>Type</th>
            </tr>
          </thead>
          <tbody id="tableBody"></tbody>
        </table>
      </div>
      <div class="status-bar" id="statusBar">Loading…</div>
    </div>
  </div>

  <!-- ════════════════ LEI PANE ════════════════ -->
  <div id="leiPane" style="display:none;flex:1;overflow:hidden;flex-direction:column">
    <div class="lei-toolbar">
      <input class="lei-search-box" id="leiQuery" placeholder="Search by entity name…">
      <button class="lei-btn" onclick="fetchLEI()">Search GLEIF</button>
      <div class="quick-btns">
        <span style="font-size:11px;color:var(--muted)">Quick:</span>
        <button class="quick-btn" onclick="quickLEI('BlackRock Asset Management Ireland')">BlackRock IE</button>
        <button class="quick-btn" onclick="quickLEI('Amundi Asset Management')">Amundi FR</button>
        <button class="quick-btn" onclick="quickLEI('DWS Investment')">DWS DE</button>
        <button class="quick-btn" onclick="quickLEI('Invesco Investment Management Limited')">Invesco IE</button>
        <button class="quick-btn" onclick="quickLEI('Vanguard Group Ireland')">Vanguard IE</button>
        <button class="quick-btn" onclick="quickLEI('State Street Global Advisors Europe')">SSGA IE</button>
        <button class="quick-btn" onclick="quickLEI('WisdomTree Management Limited')">WisdomTree IE</button>
        <button class="quick-btn" onclick="quickLEI('VanEck Asset Management')">VanEck NL</button>
        <button class="quick-btn" onclick="quickLEI('Franklin Templeton International Services')">Franklin LU</button>
      </div>
    </div>
    <div class="lei-results" id="leiResults">
      <div id="leiLoading" style="display:none;color:var(--muted);padding:20px 0">Searching GLEIF…</div>
      <div id="leiSectionLabel" class="lei-section-label"></div>
      <div id="leiCards"></div>
    </div>
  </div>

  <!-- ════════════════ ICAV PANE ════════════════ -->
  <div id="icavPane" style="display:none;flex:1;overflow:hidden;flex-direction:column">
    <div class="icav-stats">
      <div class="icav-stat"><div class="icav-stat-val" id="icavStatTotal">{icav_total:,}</div><div class="icav-stat-lbl">Total ICAVs</div></div>
      <div class="icav-stat"><div class="icav-stat-val" id="icavStatEtf">{icav_etf}</div><div class="icav-stat-lbl">ETF-Related</div></div>
      <div class="icav-stat"><div class="icav-stat-val" id="icavStatLiq">{icav_liq}</div><div class="icav-stat-lbl">In Liquidation</div></div>
      <div class="icav-stat"><div class="icav-stat-val" id="icavStatShown">—</div><div class="icav-stat-lbl">Showing</div></div>
    </div>
    <div class="icav-layout">
      <div class="icav-sidebar">
        <input class="search-box" id="icavSearch" placeholder="Search ICAVs…" oninput="applyIcavFilters()">
        <div>
          <div class="filter-label" style="margin-bottom:6px">Status</div>
          <select id="icavFilterStatus" onchange="applyIcavFilters()">
            <option value="all">All ICAVs</option>
            <option value="active">Active only</option>
            <option value="liq">In Liquidation</option>
            <option value="etf">ETF-Related</option>
          </select>
        </div>
        <div>
          <div class="filter-label" style="margin-bottom:6px">Year registered</div>
          <select id="icavFilterYear" onchange="applyIcavFilters()"><option value="">All years</option></select>
        </div>
      </div>
      <div class="icav-content">
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th onclick="icavSortBy('ICAV Name')">ICAV Name ↕</th>
                <th onclick="icavSortBy('Reg Number')">Reg Number ↕</th>
                <th onclick="icavSortBy('Reg Date')">Reg Date ↕</th>
                <th onclick="icavSortBy('First_Seen')">First Seen ↕</th>
                <th>Flags</th>
              </tr>
            </thead>
            <tbody id="icavTableBody"></tbody>
          </table>
        </div>
        <div class="status-bar" id="icavStatusBar">Loading…</div>
      </div>
    </div>
  </div>

</div><!-- .main -->

<script>
const ALL_DATA   = {data_json};
const ICAV_DATA  = {icav_json};

const EU_EEA = new Set(['IE','LU','DE','FR','NL','SE','DK','AT','BE','FI','IT','ES','PT',
  'PL','CZ','HU','SK','RO','BG','HR','SI','EE','LV','LT','CY','MT','GR','NO','IS','LI','CH']);

// ══════════════════════════════════════════════════════════════════════════════
// TAB SWITCHING
// ══════════════════════════════════════════════════════════════════════════════
function switchTab(tab) {{
  ['cbi','lei','icav'].forEach(t => {{
    document.getElementById(t + 'Pane').style.display = 'none';
    document.getElementById('tab' + t.charAt(0).toUpperCase() + t.slice(1)).classList.remove('active');
  }});
  document.getElementById(tab + 'Pane').style.display = 'flex';
  document.getElementById('tab' + tab.charAt(0).toUpperCase() + tab.slice(1)).classList.add('active');
  if (tab === 'icav') renderIcavTable();
}}

// ══════════════════════════════════════════════════════════════════════════════
// CBI TAB
// ══════════════════════════════════════════════════════════════════════════════
function uniqueSorted(arr) {{ return [...new Set(arr.filter(Boolean))].sort(); }}

function populateFilters() {{
  const mancos = uniqueSorted(ALL_DATA.map(r => r.ManCo));
  const deps   = uniqueSorted(ALL_DATA.map(r => r.Depositary));
  const years  = uniqueSorted(ALL_DATA.map(r => (r.Auth_Date||'').substring(0,4))).reverse();
  const selManco = document.getElementById('filterManco');
  mancos.forEach(m => {{ const o = new Option(m,m); selManco.add(o); }});
  const selDep = document.getElementById('filterDep');
  deps.forEach(d => {{ const o = new Option(d,d); selDep.add(o); }});
  const selYear = document.getElementById('filterYear');
  years.forEach(y => {{ const o = new Option(y,y); selYear.add(o); }});
}}

let sortCol = 'Auth_Date', sortDir = -1;
function sortBy(col) {{
  sortDir = (col === sortCol) ? -sortDir : -1;
  sortCol = col;
  renderTable();
}}

function applyFilters() {{
  const q     = document.getElementById('searchBox').value.toLowerCase();
  const type  = document.getElementById('filterType').value;
  const manco = document.getElementById('filterManco').value;
  const dep   = document.getElementById('filterDep').value;
  const year  = document.getElementById('filterYear').value;

  window.cbiFiltered = ALL_DATA.filter(r => {{
    if (q && !r['Fund Name'].toLowerCase().includes(q) &&
             !(r.ManCo||'').toLowerCase().includes(q) &&
             !(r.Depositary||'').toLowerCase().includes(q)) return false;
    if (type === 'etf'   && !r['Fund Name'].toLowerCase().includes('etf')) return false;
    if (type === 'other' &&  r['Fund Name'].toLowerCase().includes('etf')) return false;
    if (manco && r.ManCo !== manco) return false;
    if (dep   && r.Depositary !== dep) return false;
    if (year  && (r.Auth_Date||'').substring(0,4) !== year) return false;
    return true;
  }});
  renderTable();
}}

function renderTable() {{
  const data = (window.cbiFiltered || ALL_DATA).slice().sort((a,b) => {{
    const av = a[sortCol] || '', bv = b[sortCol] || '';
    return av < bv ? -sortDir : av > bv ? sortDir : 0;
  }});
  const etfCount = data.filter(r => r['Fund Name'].toLowerCase().includes('etf')).length;
  document.getElementById('statVisible').textContent = data.length.toLocaleString();
  document.getElementById('statEtf').textContent = etfCount.toLocaleString();
  document.getElementById('statusBar').textContent = `Showing ${{data.length.toLocaleString()}} of {total:,} funds`;
  document.getElementById('tableBody').innerHTML = data.map(r => {{
    const isEtf = r['Fund Name'].toLowerCase().includes('etf');
    return `<tr>
      <td style="max-width:320px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${{r['Fund Name']}}</td>
      <td style="color:var(--muted)">${{r.ManCo || '—'}}</td>
      <td style="color:var(--muted)">${{r.Depositary || '—'}}</td>
      <td style="font-family:monospace;font-size:11px">${{r.Auth_Date || '—'}}</td>
      <td style="font-family:monospace;font-size:11px;color:var(--accent)">${{r.First_Seen || '—'}}</td>
      <td><span class="badge ${{isEtf ? 'badge-etf' : 'badge-other'}}">${{isEtf ? 'ETF' : 'FUND'}}</span></td>
    </tr>`;
  }}).join('');
}}

// ══════════════════════════════════════════════════════════════════════════════
// LEI TAB
// ══════════════════════════════════════════════════════════════════════════════
async function fetchLEI() {{
  const q = document.getElementById('leiQuery').value.trim();
  if (!q) return;
  document.getElementById('leiLoading').style.display = 'block';
  document.getElementById('leiCards').innerHTML = '';
  document.getElementById('leiSectionLabel').textContent = '';
  try {{
    const url = 'https://api.gleif.org/api/v1/lei-records?filter[entity.legalName]=' + encodeURIComponent(q) + '&page[size]=50';
    const data = await (await fetch(url)).json();
    const euOnly = (data.data || []).filter(r => {{
      const country = r.attributes?.entity?.legalAddress?.country || '';
      return EU_EEA.has(country);
    }});
    document.getElementById('leiSectionLabel').textContent = euOnly.length + ' EU/EEA result(s) for "' + q + '"';
    renderLEI(euOnly);
  }} catch(e) {{
    document.getElementById('leiCards').innerHTML = '<p style="color:#ef4444">Error: ' + e.message + '</p>';
  }} finally {{
    document.getElementById('leiLoading').style.display = 'none';
  }}
}}

function renderLEI(records) {{
  if (!records.length) {{
    document.getElementById('leiCards').innerHTML = '<p style="color:var(--muted);padding:20px 0">No EU/EEA results found.</p>';
    return;
  }}
  document.getElementById('leiCards').innerHTML = records.map(r => {{
    const attr   = r.attributes || {{}};
    const entity = attr.entity || {{}};
    const reg    = attr.registration || {{}};
    const laddr  = entity.legalAddress || {{}};
    const raddr  = entity.registeredAddress || {{}};
    const rawName = entity.legalName || {{}};
    const name    = (typeof rawName === 'object' ? rawName.value : rawName) || r.id;
    const otherNames = (entity.otherNames || []).map(n => typeof n === 'object' ? n.value : n).filter(Boolean);
    const lei       = r.id || '';
    const country   = laddr.country || '';
    const city      = laddr.city || '';
    const addrLine  = [laddr.addressLines?.[0], city, country].filter(Boolean).join(', ');
    const status    = (reg.status || '').toLowerCase() === 'issued' ? 'issued' : 'lapsed';
    const registered  = (reg.initialRegistrationDate || '').substring(0,10);
    const lastUpdate  = (reg.lastUpdateDate || '').substring(0,10);
    const nextRenewal = (reg.nextRenewalDate || '').substring(0,10);
    const legalForm   = entity.legalForm?.id || '';
    const category    = entity.category || '';
    const jurisdiction= entity.jurisdiction || '';
    const managingOU  = reg.managingLou || '';
    const cbiMatches  = ALL_DATA.filter(d => {{
      const n = d.ManCo || '';
      return n.length > 4 && name.toLowerCase().includes(n.toLowerCase().substring(0,12));
    }}).slice(0,3);
    const cbiHtml = cbiMatches.length ? `
      <div class="lei-cbi-match">
        <div style="font-size:10px;color:var(--accent);font-weight:700;text-transform:uppercase;letter-spacing:.4px;margin-bottom:6px">Matched CBI Funds</div>
        ${{cbiMatches.map(d => `<div class="lei-cbi-row"><span>${{d['Fund Name']}}</span><span>${{d.Auth_Date}}</span></div>`).join('')}}
      </div>` : '';
    return `<div class="lei-card">
      <div class="lei-card-header">
        <div>
          <div class="lei-card-title">${{name}}</div>
          ${{otherNames.length ? '<div style="font-size:11px;color:var(--muted);margin-top:2px">Also: ' + otherNames.slice(0,2).join(', ') + '</div>' : ''}}
          <div class="lei-card-sub">${{addrLine}}${{category ? ' &middot; ' + category : ''}}</div>
        </div>
        <span class="lei-status-badge ${{status}}">${{status.toUpperCase()}}</span>
      </div>
      <div class="lei-card-body">
        <div class="lei-field"><label>LEI Code</label><span class="mono">${{lei}}</span></div>
        <div class="lei-field"><label>Jurisdiction</label><span>${{jurisdiction || country || '—'}}</span></div>
        <div class="lei-field"><label>Legal Form</label><span>${{legalForm || '—'}}</span></div>
        <div class="lei-field"><label>Category</label><span>${{category || '—'}}</span></div>
        <div class="lei-field"><label>Managing LOU</label><span>${{managingOU || '—'}}</span></div>
        <div class="lei-field"><label>Registered Address</label><span style="font-size:11px">${{[raddr.addressLines?.[0], raddr.city, raddr.country].filter(Boolean).join(', ') || '—'}}</span></div>
      </div>
      <div class="lei-card-footer">
        <div class="lei-footer-item">Registered <strong>${{registered || '—'}}</strong></div>
        <div class="lei-footer-item">Updated <strong>${{lastUpdate || '—'}}</strong></div>
        <div class="lei-footer-item">Renewal <strong>${{nextRenewal || '—'}}</strong></div>
        <div class="lei-footer-item" style="margin-left:auto">
          <a href="https://search.gleif.org/#/record/${{lei}}" target="_blank" style="color:var(--accent);font-size:11px">View on GLEIF &rarr;</a>
        </div>
      </div>
      ${{cbiHtml}}
    </div>`;
  }}).join('');
}}

function quickLEI(q) {{
  document.getElementById('leiQuery').value = q;
  fetchLEI();
}}
document.getElementById('leiQuery').addEventListener('keydown', e => {{ if(e.key==='Enter') fetchLEI(); }});

// ══════════════════════════════════════════════════════════════════════════════
// ICAV TAB
// ══════════════════════════════════════════════════════════════════════════════
let icavSortCol = 'Reg Date', icavSortDir = -1;

function icavSortBy(col) {{
  icavSortDir = (col === icavSortCol) ? -icavSortDir : -1;
  icavSortCol = col;
  renderIcavTable();
}}

(function populateIcavFilters() {{
  const years = [...new Set(ICAV_DATA.map(r => (r['Reg Date']||'').substring(0,4)).filter(Boolean))].sort().reverse();
  const sel = document.getElementById('icavFilterYear');
  years.forEach(y => sel.add(new Option(y, y)));
}})();

function applyIcavFilters() {{
  renderIcavTable();
}}

function renderIcavTable() {{
  const q      = (document.getElementById('icavSearch').value || '').toLowerCase();
  const status = document.getElementById('icavFilterStatus').value;
  const year   = document.getElementById('icavFilterYear').value;

  let data = ICAV_DATA.filter(r => {{
    const name = (r['ICAV Name'] || '').toLowerCase();
    if (q && !name.includes(q)) return false;
    if (status === 'active' && r['In Liquidation'] === 'Yes') return false;
    if (status === 'liq'    && r['In Liquidation'] !== 'Yes') return false;
    if (status === 'etf'    && r['ETF Related']    !== 'Yes') return false;
    if (year && (r['Reg Date']||'').substring(0,4) !== year) return false;
    return true;
  }});

  data = data.slice().sort((a,b) => {{
    const av = a[icavSortCol] || '', bv = b[icavSortCol] || '';
    return av < bv ? -icavSortDir : av > bv ? icavSortDir : 0;
  }});

  document.getElementById('icavStatShown').textContent = data.length.toLocaleString();
  document.getElementById('icavStatusBar').textContent = `Showing ${{data.length.toLocaleString()}} of {icav_total:,} ICAVs`;

  document.getElementById('icavTableBody').innerHTML = data.map(r => {{
    const inLiq = r['In Liquidation'] === 'Yes';
    const isEtf = r['ETF Related'] === 'Yes';
    const flags = [
      inLiq ? '<span class="badge badge-liq">IN LIQ</span>' : '',
      isEtf ? '<span class="badge badge-etf">ETF</span>'    : '',
    ].filter(Boolean).join(' ') || '<span style="color:var(--muted)">—</span>';
    return `<tr>
      <td style="max-width:400px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${{r['ICAV Name'] || '—'}}</td>
      <td style="font-family:monospace;font-size:11px">${{r['Reg Number'] || '—'}}</td>
      <td style="font-family:monospace;font-size:11px">${{r['Reg Date'] || '—'}}</td>
      <td style="font-family:monospace;font-size:11px;color:var(--accent)">${{r['First_Seen'] || '—'}}</td>
      <td>${{flags}}</td>
    </tr>`;
  }}).join('');
}}

// ══════════════════════════════════════════════════════════════════════════════
// INIT
// ══════════════════════════════════════════════════════════════════════════════
populateFilters();
applyFilters();
</script>
</body>
</html>"""


def main():
    os.makedirs(os.path.dirname(HTML_OUT), exist_ok=True)

    if not os.path.exists(CSV_PATH):
        print(f"WARNING: {CSV_PATH} not found — using empty CBI data")
        df = pd.DataFrame(columns=['Fund Name', 'ManCo', 'Depositary', 'Auth_Date', 'First_Seen'])
    else:
        df = pd.read_csv(CSV_PATH)

    if not os.path.exists(ICAV_PATH):
        print(f"WARNING: {ICAV_PATH} not found — using empty ICAV data")
        icav_df = pd.DataFrame(columns=['ICAV Name', 'Reg Date', 'Reg Number', 'In Liquidation', 'ETF Related', 'First_Seen'])
    else:
        icav_df = pd.read_csv(ICAV_PATH)

    html = build_html(df, icav_df)
    with open(HTML_OUT, 'w', encoding='utf-8') as f:
        f.write(html)

    nojekyll = os.path.join(os.path.dirname(HTML_OUT), '.nojekyll')
    open(nojekyll, 'a').close()

    print(f"Dashboard written → {HTML_OUT}  ({os.path.getsize(HTML_OUT)//1024} KB)")
    print(f"  CBI funds: {len(df):,}  |  ICAVs: {len(icav_df):,}")


if __name__ == '__main__':
    main()
