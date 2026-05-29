"""Shared HTTP/PDF/FX helpers for issuer AUM scrapers.

Each issuer scraper lives in scripts/aum/<issuer>.py and exports a top-level
`fetch()` function that returns a list of records shaped like:

    [
        {
            "issuer":      "HANetf",
            "fund_name":   "Sprott Uranium Miners UCITS ETF",
            "isin":        "IE0005YK6564",
            "ticker":      "URNM",
            "aum_native":  123_456_789.0,
            "currency":    "USD",
            "as_of":       "2025-11-30",   # YYYY-MM-DD
            "source_url":  "https://etp.hanetf.com/...",
        },
        ...
    ]

aum_sync.py drives them, applies FX (native -> EUR via ECB reference rates),
and writes the combined output to data/aum_db.csv.
"""

from __future__ import annotations

import io
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime
from typing import Iterable

import requests
import pdfplumber

log = logging.getLogger(__name__)

# Browser-like UA — issuer sites tend to 403 the default Python/requests UA.
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.6 Safari/605.1.15 "
        "etf-intelligence/0.1 (+https://github.com/daveirl/etf-intelligence)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}

# Polite minimum delay between requests to the same host (seconds).
MIN_DELAY = 1.0


def build_session(extra_headers: dict | None = None) -> requests.Session:
    s = requests.Session()
    s.headers.update(DEFAULT_HEADERS)
    if extra_headers:
        s.headers.update(extra_headers)
    return s


def polite_get(session: requests.Session, url: str, **kwargs) -> requests.Response:
    """GET with a min-delay throttle and 60s timeout."""
    time.sleep(MIN_DELAY)
    return session.get(url, timeout=60, **kwargs)


# ─── PDF helpers ────────────────────────────────────────────────────

# Match "EUR 123,456,789.12" / "$ 1.2 bn" / "£12.3m" / etc.
_AUM_PATTERNS = [
    re.compile(
        r"(?:fund\s+size|aum|net\s+assets|total\s+(?:net\s+)?assets|assets\s+under\s+management)"
        r"[^A-Za-z0-9]+([A-Z$£€¥]{1,3}[\s ]?)([\d,]+(?:\.\d+)?)\s*(bn|billion|m|mn|million|k|thousand)?",
        re.IGNORECASE,
    ),
]

_DATE_PATTERN = re.compile(
    r"(?:as\s+(?:at|of)|nav\s+date|valuation\s+date|date)[^\d]{0,20}"
    r"(\d{1,2}[./\s-]\d{1,2}[./\s-]\d{2,4}"
    r"|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{2,4})",
    re.IGNORECASE,
)

_CURRENCY_SYMBOL = {"$": "USD", "£": "GBP", "€": "EUR", "¥": "JPY"}

_MULTIPLIER = {
    "bn": 1_000_000_000, "billion": 1_000_000_000,
    "m":  1_000_000,     "mn": 1_000_000, "million":  1_000_000,
    "k":  1_000,         "thousand":  1_000,
}


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Pull all text out of a PDF, joining pages with a single newline."""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        return "\n".join((page.extract_text() or "") for page in pdf.pages)


def parse_aum(text: str) -> tuple[float | None, str | None]:
    """Best-effort scrape of an AUM number and its currency from a PDF text dump.

    Returns (amount_native, currency_iso) or (None, None) if nothing matched.
    """
    for rx in _AUM_PATTERNS:
        m = rx.search(text)
        if not m:
            continue
        sym_raw, num_raw, mult_raw = m.group(1), m.group(2), m.group(3)
        try:
            amount = float(num_raw.replace(",", ""))
        except ValueError:
            continue
        if mult_raw:
            amount *= _MULTIPLIER.get(mult_raw.lower(), 1)
        sym = sym_raw.strip()
        currency = _CURRENCY_SYMBOL.get(sym) or (sym.upper() if sym.isalpha() else None)
        return amount, currency
    return None, None


def parse_as_of(text: str) -> str | None:
    """Pull the NAV-date / as-of date from a PDF text dump as YYYY-MM-DD."""
    m = _DATE_PATTERN.search(text)
    if not m:
        return None
    raw = m.group(1).strip()
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%d/%m/%Y", "%d/%m/%y",
                "%d-%m-%Y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


# ─── FX (ECB daily reference rates) ─────────────────────────────────

ECB_DAILY = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"

# Cache to avoid hammering the ECB feed.
_FX_CACHE: dict[str, float] = {}


def load_fx_rates(session: requests.Session | None = None) -> dict[str, float]:
    """Return a dict mapping ISO currency codes to "1 EUR = X CCY" rates,
    based on the latest ECB daily reference rates. EUR maps to 1.0."""
    if _FX_CACHE:
        return _FX_CACHE
    s = session or build_session()
    try:
        r = s.get(ECB_DAILY, timeout=30)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        ns = {"e": "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"}
        # The "Cube[time=..]/Cube[currency=..]" structure carries the rates.
        for cube in root.iter("{http://www.ecb.int/vocabulary/2002-08-01/eurofxref}Cube"):
            ccy  = cube.attrib.get("currency")
            rate = cube.attrib.get("rate")
            if ccy and rate:
                _FX_CACHE[ccy] = float(rate)
        _FX_CACHE["EUR"] = 1.0
        log.info("Loaded %d FX rates from ECB", len(_FX_CACHE))
    except Exception as e:  # noqa: BLE001 — never fatal; just no FX
        log.warning("Could not load ECB FX rates: %s", e)
    return _FX_CACHE


def to_eur(amount: float, currency: str, rates: dict[str, float]) -> float | None:
    """Convert `amount` from `currency` to EUR using ECB reference rates."""
    if amount is None:
        return None
    if not currency:
        return None
    rate = rates.get(currency.upper())
    if not rate:
        return None
    return amount / rate
