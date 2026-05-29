"""HANetf AUM scraper.

Strategy:
1. Scrape the product list at /product-list/ to extract (ticker, ISIN) for
   every UCITS ETF on the platform. The list is server-rendered HTML so we
   can read it without a headless browser.
2. For each (ticker, ISIN), fetch the always-current factsheet endpoint at
   etp.hanetf.com/Factsheet-<TICKER>-<ISIN>-en. That URL returns a PDF that
   contains the current AUM, currency, and NAV date.
3. Return a list of records in the shape aum_sync.py expects.
"""

from __future__ import annotations

import logging
import re

from .base import build_session, polite_get, extract_pdf_text, parse_aum, parse_as_of

log = logging.getLogger(__name__)

ISSUER       = "HANetf"
PRODUCT_LIST = "https://hanetf.com/product-list/"
FACTSHEET_FMT = "https://etp.hanetf.com/Factsheet-{ticker}-{isin}-en"

# /fund/<ticker-lowercase>-<slug>/ — capture the leading ticker token.
_FUND_URL_RX = re.compile(r"/fund/([A-Za-z0-9]{2,6})-[^/\"']+/?", re.IGNORECASE)
_ISIN_RX     = re.compile(r"\b([A-Z]{2}[A-Z0-9]{9}\d)\b")
_FUND_NAME_RX = re.compile(
    r"/fund/[A-Za-z0-9]+-[^\"']+/?[\"'][^>]*>([^<]{6,120})</a>",
    re.IGNORECASE,
)


def _extract_registry(html: str) -> list[dict]:
    """Pull (ticker, isin, name) tuples out of the HANetf product-list HTML.

    The product list links to /fund/<ticker>-<slug>/ for every product.
    ISINs are present inline near each link (or in a sibling element).
    """
    fund_links: dict[str, dict] = {}
    for m in _FUND_URL_RX.finditer(html):
        ticker = m.group(1).upper()
        # Best-effort: pull a window of HTML around the link and look for the
        # nearest ISIN and human-readable name.
        start = max(0, m.start() - 400)
        end   = min(len(html), m.end() + 400)
        window = html[start:end]
        isin_match = _ISIN_RX.search(window)
        name_match = _FUND_NAME_RX.search(window)
        fund_links[ticker] = {
            "ticker": ticker,
            "isin":   isin_match.group(1) if isin_match else None,
            "name":   (name_match.group(1).strip() if name_match else None),
        }
    return [v for v in fund_links.values() if v["isin"]]


def _scrape_factsheet(session, ticker: str, isin: str) -> dict | None:
    url = FACTSHEET_FMT.format(ticker=ticker, isin=isin)
    try:
        r = polite_get(session, url)
        r.raise_for_status()
    except Exception as e:  # noqa: BLE001
        log.warning("HANetf factsheet fetch failed for %s/%s: %s", ticker, isin, e)
        return None
    if not r.content.startswith(b"%PDF"):
        log.warning("HANetf factsheet for %s/%s was not a PDF (got %d bytes)",
                    ticker, isin, len(r.content))
        return None
    try:
        text = extract_pdf_text(r.content)
    except Exception as e:  # noqa: BLE001
        log.warning("HANetf factsheet parse failed for %s/%s: %s", ticker, isin, e)
        return None
    amount, currency = parse_aum(text)
    as_of            = parse_as_of(text)
    if amount is None:
        log.warning("HANetf factsheet %s/%s: no AUM line matched", ticker, isin)
        return None
    return {
        "aum_native": amount,
        "currency":   currency or "USD",  # HANetf factsheets default to USD when symbol absent
        "as_of":      as_of,
        "source_url": url,
    }


def fetch() -> list[dict]:
    """Top-level entry point used by aum_sync.py."""
    session = build_session(extra_headers={"Referer": "https://hanetf.com/"})

    log.info("HANetf: fetching product list")
    try:
        r = polite_get(session, PRODUCT_LIST)
        r.raise_for_status()
    except Exception as e:  # noqa: BLE001
        log.error("HANetf: product list fetch failed: %s", e)
        return []
    registry = _extract_registry(r.text)
    log.info("HANetf: %d funds identified on product list", len(registry))

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
