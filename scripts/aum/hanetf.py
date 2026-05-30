"""HANetf AUM scraper.

Strategy:
1. Pull the canonical product list from
     https://hanetf.com/wp-content/assets/upload/productlist-all_all_en_all.pdf
   — one PDF containing every UCITS ETF on the platform with ticker + ISIN.
   (The HTML /product-list/ page is JS-rendered, so the server returns an
   SPA shell with no fund data in the initial response. The PDF is stable
   and structured.)
2. For each (ticker, ISIN) extracted from the registry PDF, fetch the
   always-current per-fund factsheet at
     https://etp.hanetf.com/Factsheet-<TICKER>-<ISIN>-en
   That URL returns a PDF with the current AUM, currency, and NAV date.
3. Return one record per fund in the shape aum_sync.py expects.

If the registry PDF endpoint moves or starts gating requests, falls back to
scraping the HTML product list as a best-effort secondary path.
"""

from __future__ import annotations

import logging
import re

from .base import build_session, polite_get, extract_pdf_text, parse_aum, parse_as_of

log = logging.getLogger(__name__)

ISSUER          = "HANetf"
PRODUCT_LIST_PDF = "https://hanetf.com/wp-content/assets/upload/productlist-all_all_en_all.pdf"
PRODUCT_LIST_HTML = "https://hanetf.com/product-list/"
FACTSHEET_FMT   = "https://etp.hanetf.com/Factsheet-{ticker}-{isin}-en"

_ISIN_RX     = re.compile(r"\b([A-Z]{2}[A-Z0-9]{9}\d)\b")
_TICKER_RX   = re.compile(r"\b([A-Z]{2,6})\b")
_FUND_URL_RX = re.compile(r"/fund/([A-Za-z0-9]{2,6})-[^/\"']+/?", re.IGNORECASE)


def _looks_like_pdf(content: bytes) -> bool:
    return content.startswith(b"%PDF")


def _diagnose_response(label: str, r) -> None:
    """Log enough metadata to debug a fetch that didn't return what we expected."""
    body = r.content[:500] if r is not None else b""
    snippets = {
        "Cloudflare":  b"cloudflare" in body.lower() or b"cf-mitigated" in body.lower(),
        "Just a moment": b"just a moment" in body.lower(),
        "HTML":        body.lstrip().startswith(b"<"),
        "PDF":         body.startswith(b"%PDF"),
        "URNM":        b"URNM" in r.content[:200_000],
        "IE000":       b"IE000" in r.content[:200_000],
        "/fund/":      b"/fund/" in r.content[:200_000],
    }
    hits = [k for k, v in snippets.items() if v]
    log.info("HANetf %s: %d bytes, content-type=%s, contains: %s",
             label, len(r.content), r.headers.get("Content-Type", "?"),
             ", ".join(hits) if hits else "none of the markers we look for")


def _parse_registry_pdf(pdf_bytes: bytes) -> list[dict]:
    """Walk the product-list PDF line by line, capturing every (ticker, ISIN)
    pair that appears on the same line. The product list is tabular and pdftotext
    preserves row order well enough that the ticker is co-located with its ISIN."""
    text = extract_pdf_text(pdf_bytes)
    seen: dict[str, dict] = {}
    for line in text.splitlines():
        isin_match = _ISIN_RX.search(line)
        if not isin_match:
            continue
        isin = isin_match.group(1)
        # Strip the ISIN out of the line before looking for a ticker, so the
        # ticker regex can't pick up the leading "IE"/"GB"/"XS" of the ISIN.
        leftover = (line[: isin_match.start()] + " " + line[isin_match.end():])
        ticker = None
        for tok in _TICKER_RX.findall(leftover):
            # Skip obvious noise: currency codes, common header words.
            if tok in {"USD", "EUR", "GBP", "JPY", "CHF", "ETF", "UCITS",
                       "ACC", "DIS", "DIST", "HDG", "ETC", "ETP",
                       "SEDOL", "BBG", "LSE", "XETRA", "BIT", "SIX",
                       "NAV", "TER", "OCF", "ID", "NA", "UK", "EU", "DE", "IT"}:
                continue
            if len(tok) >= 2:
                ticker = tok
                break
        if ticker and ticker not in seen:
            seen[ticker] = {
                "ticker": ticker,
                "isin":   isin,
                "name":   line.strip(),
            }
    return list(seen.values())


def _parse_registry_html(html: str) -> list[dict]:
    """Fallback path: try to extract /fund/<ticker>-...-/ links from the HTML
    product-list page. This rarely works on the live site (JS-rendered), but
    keeps the scraper alive if the PDF endpoint ever moves."""
    tickers = {m.group(1).upper() for m in _FUND_URL_RX.finditer(html)}
    out = []
    for ticker in tickers:
        # Look for an ISIN within 500 chars of the first occurrence of the ticker.
        idx = html.upper().find(ticker)
        window = html[max(0, idx - 500): idx + 500]
        isin_match = _ISIN_RX.search(window)
        if isin_match:
            out.append({"ticker": ticker, "isin": isin_match.group(1), "name": ""})
    return out


def _fetch_registry(session) -> list[dict]:
    log.info("HANetf: fetching product-list PDF")
    try:
        r = polite_get(session, PRODUCT_LIST_PDF)
        r.raise_for_status()
    except Exception as e:  # noqa: BLE001
        log.warning("HANetf product-list PDF fetch failed: %s", e)
        r = None
    if r is not None and _looks_like_pdf(r.content):
        try:
            registry = _parse_registry_pdf(r.content)
            log.info("HANetf: parsed %d (ticker, ISIN) pairs from registry PDF", len(registry))
            if registry:
                return registry
        except Exception as e:  # noqa: BLE001
            log.warning("HANetf registry PDF parse failed: %s", e)
    elif r is not None:
        _diagnose_response("registry PDF (not a PDF)", r)

    # Fallback to HTML scrape (rarely yields data on the live site).
    log.info("HANetf: registry PDF empty — falling back to HTML product list")
    try:
        r2 = polite_get(session, PRODUCT_LIST_HTML)
        r2.raise_for_status()
        _diagnose_response("HTML product list", r2)
        return _parse_registry_html(r2.text)
    except Exception as e:  # noqa: BLE001
        log.error("HANetf HTML product list fetch failed: %s", e)
        return []


def _scrape_factsheet(session, ticker: str, isin: str) -> dict | None:
    url = FACTSHEET_FMT.format(ticker=ticker, isin=isin)
    try:
        r = polite_get(session, url)
        r.raise_for_status()
    except Exception as e:  # noqa: BLE001
        log.warning("HANetf factsheet fetch failed for %s/%s: %s", ticker, isin, e)
        return None
    if not _looks_like_pdf(r.content):
        log.warning("HANetf factsheet for %s/%s was not a PDF (got %d bytes, starts %r)",
                    ticker, isin, len(r.content), r.content[:50])
        return None
    try:
        text = extract_pdf_text(r.content)
    except Exception as e:  # noqa: BLE001
        log.warning("HANetf factsheet parse failed for %s/%s: %s", ticker, isin, e)
        return None
    amount, currency = parse_aum(text)
    as_of            = parse_as_of(text)
    if amount is None:
        log.warning("HANetf factsheet %s/%s: no AUM line matched in PDF text", ticker, isin)
        return None
    return {
        "aum_native": amount,
        "currency":   currency or "USD",  # HANetf default to USD when symbol absent
        "as_of":      as_of,
        "source_url": url,
    }


def fetch() -> list[dict]:
    """Entry point used by aum_sync.py."""
    session  = build_session(extra_headers={"Referer": "https://hanetf.com/"})
    registry = _fetch_registry(session)
    log.info("HANetf: %d funds in registry", len(registry))

    records: list[dict] = []
    for entry in registry:
        factsheet = _scrape_factsheet(session, entry["ticker"], entry["isin"])
        if not factsheet:
            continue
        records.append({
            "issuer":     ISSUER,
            "fund_name":  entry.get("name") or "",
            "isin":       entry["isin"],
            "ticker":     entry["ticker"],
            **factsheet,
        })

    log.info("HANetf: %d AUM records captured", len(records))
    return records
