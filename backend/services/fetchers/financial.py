"""Gokdogan financial market fetcher.

Provides a single normalized quote model across:
- major global equities / defence / technology
- crypto assets
- FX pairs, with TRY pairs prioritized for the Turkish default profile
- precious/base metals futures
- energy futures
- major equity indices

The fetcher remains opt-in for generic upstream builds.  The customized Gokdogan
launchers set ``GOKDOGAN_LIVE_DATA=true`` so the one-click desktop profile starts
with public market data enabled.  ``FINNHUB_API_KEY`` can optionally enrich the
stock/crypto path; Yahoo Finance (via yfinance) is the broad fallback source.
"""

from __future__ import annotations

import logging
import math
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Dict, Iterable, Tuple

logger = logging.getLogger(__name__)

from services.fetchers._store import latest_data, _data_lock, _mark_fresh


TICKERS_STOCKS: Dict[str, str] = {
    # Defence / aerospace
    "RTX": "RTX",
    "LMT": "LMT",
    "NOC": "NOC",
    "GD": "GD",
    "BA": "BA",
    "PLTR": "PLTR",
    # Global technology / strategic manufacturing
    "NVDA": "NVDA",
    "AMD": "AMD",
    "TSM": "TSM",
    "INTC": "INTC",
    "GOOGL": "GOOGL",
    "AMZN": "AMZN",
    "MSFT": "MSFT",
    "AAPL": "AAPL",
    "TSLA": "TSLA",
    "META": "META",
    "ASML": "ASML",
}

TICKERS_CRYPTO: Dict[str, Tuple[str, str]] = {
    "BTC": ("BINANCE:BTCUSDT", "BTC-USD"),
    "ETH": ("BINANCE:ETHUSDT", "ETH-USD"),
    "SOL": ("BINANCE:SOLUSDT", "SOL-USD"),
    "XRP": ("BINANCE:XRPUSDT", "XRP-USD"),
    "ADA": ("BINANCE:ADAUSDT", "ADA-USD"),
    "BNB": ("BINANCE:BNBUSDT", "BNB-USD"),
    "DOGE": ("BINANCE:DOGEUSDT", "DOGE-USD"),
}

TICKERS_FX: Dict[str, str] = {
    "USD/TRY": "TRY=X",
    "EUR/TRY": "EURTRY=X",
    "GBP/TRY": "GBPTRY=X",
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/JPY": "JPY=X",
    "USD/CHF": "CHF=X",
    "AUD/USD": "AUDUSD=X",
    "USD/CAD": "CAD=X",
    "USD/CNY": "CNY=X",
}

TICKERS_METALS: Dict[str, str] = {
    "ALTIN": "GC=F",
    "GÜMÜŞ": "SI=F",
    "PLATİN": "PL=F",
    "PALADYUM": "PA=F",
    "BAKIR": "HG=F",
}

TICKERS_ENERGY: Dict[str, str] = {
    "BRENT": "BZ=F",
    "WTI": "CL=F",
    "DOĞAL GAZ": "NG=F",
}

TICKERS_INDICES: Dict[str, str] = {
    "BIST 100": "XU100.IS",
    "S&P 500": "^GSPC",
    "NASDAQ": "^IXIC",
    "DOW JONES": "^DJI",
    "DAX": "^GDAXI",
    "FTSE 100": "^FTSE",
    "NIKKEI 225": "^N225",
    "VIX": "^VIX",
}

_last_fetch_time = 0.0
_last_snapshot: dict = {}
_executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix="gokdogan-fin")
_fetch_lock = threading.Lock()


def _truthy_env(name: str) -> bool:
    return str(os.environ.get(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def financial_fetch_enabled() -> bool:
    """Return True when market-data outbound traffic has been enabled."""
    if os.getenv("FINNHUB_API_KEY", "").strip():
        return True
    return _truthy_env("FINANCIAL_ENABLED") or _truthy_env("GOKDOGAN_LIVE_DATA")


def _normalize_quote(price: float, prev_close: float | None, *, source: str, symbol: str) -> dict | None:
    if not math.isfinite(price):
        return None
    change_percent = 0.0
    if prev_close is not None and math.isfinite(prev_close) and prev_close != 0:
        change_percent = ((price - prev_close) / prev_close) * 100.0
    if not math.isfinite(change_percent):
        change_percent = 0.0
    return {
        "price": round(float(price), 6 if abs(price) < 10 else 2),
        "change_percent": round(float(change_percent), 2),
        "up": bool(change_percent >= 0),
        "source": source,
        "symbol": symbol,
    }


def _fetch_yfinance_single(symbol: str, period: str = "2d"):
    """Fetch one Yahoo Finance symbol through yfinance."""
    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period, auto_adjust=False)
        if hist is None or len(hist) < 1:
            return symbol, None
        current = float(hist["Close"].iloc[-1])
        previous = float(hist["Close"].iloc[-2]) if len(hist) > 1 else current
        return symbol, _normalize_quote(current, previous, source="yfinance", symbol=symbol)
    except Exception as exc:
        logger.debug("yfinance error for %s: %s", symbol, exc)
        return symbol, None


def _fetch_finnhub_quote(symbol: str, api_key: str):
    """Fetch a stock or crypto quote from Finnhub."""
    import json
    import urllib.request

    url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={api_key}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Gokdogan/0.11"})
        with urllib.request.urlopen(req, timeout=6) as response:
            payload = json.loads(response.read().decode("utf-8"))
        current = float(payload.get("c") or 0.0)
        previous = float(payload.get("pc") or current)
        if current <= 0:
            return symbol, None
        return symbol, _normalize_quote(current, previous, source="finnhub", symbol=symbol)
    except Exception as exc:
        logger.debug("Finnhub error for %s: %s", symbol, exc)
        return symbol, None


def _fetch_group(definitions: Dict[str, str]) -> Dict[str, dict]:
    futures = {
        _executor.submit(_fetch_yfinance_single, symbol): (label, symbol)
        for label, symbol in definitions.items()
    }
    out: Dict[str, dict] = {}
    for future in as_completed(futures):
        label, _symbol = futures[future]
        try:
            _returned_symbol, quote = future.result()
        except Exception as exc:
            logger.debug("market quote task failed for %s: %s", label, exc)
            continue
        if quote:
            out[label] = quote
    return out


def _fetch_crypto_yfinance() -> Dict[str, dict]:
    return _fetch_group({label: yahoo for label, (_finnhub, yahoo) in TICKERS_CRYPTO.items()})


def _overlay_finnhub(base_stocks: Dict[str, dict], base_crypto: Dict[str, dict], api_key: str) -> None:
    """Overlay higher-frequency Finnhub quotes without making it mandatory."""
    symbols: list[tuple[str, str, str]] = []
    for label, symbol in TICKERS_STOCKS.items():
        symbols.append(("stocks", label, symbol))
    for label, (symbol, _yahoo) in TICKERS_CRYPTO.items():
        symbols.append(("crypto", label, symbol))

    futures = {
        _executor.submit(_fetch_finnhub_quote, symbol, api_key): (group, label)
        for group, label, symbol in symbols
    }
    for future in as_completed(futures):
        group, label = futures[future]
        try:
            _symbol, quote = future.result()
        except Exception:
            continue
        if not quote:
            continue
        if group == "stocks":
            base_stocks[label] = quote
        else:
            base_crypto[label] = quote


def fetch_financial_markets():
    """Fetch and publish all Gokdogan market groups.

    The scheduler calls this relatively infrequently; this function adds its own
    five-minute guard so manual refreshes cannot accidentally hammer providers.
    """
    global _last_fetch_time, _last_snapshot

    if not financial_fetch_enabled():
        with _data_lock:
            latest_data["financial"] = {}
            latest_data["stocks"] = {}
            latest_data["crypto"] = {}
            latest_data["fx"] = {}
            latest_data["metals"] = {}
            latest_data["indices"] = {}
            latest_data["oil"] = {}
        _mark_fresh("financial")
        return

    with _fetch_lock:
        now = time.time()
        min_interval = float(os.environ.get("GOKDOGAN_FINANCIAL_MIN_INTERVAL_S", "300"))
        if _last_snapshot and now - _last_fetch_time < max(30.0, min_interval):
            return
        _last_fetch_time = now

        # Yahoo gives the broad cross-asset baseline.  A Finnhub key, when
        # present, overwrites stock/crypto quotes while leaving FX/metals/etc.
        # on Yahoo where the symbol coverage is simpler and consistent.
        stocks = _fetch_group(TICKERS_STOCKS)
        crypto = _fetch_crypto_yfinance()
        fx = _fetch_group(TICKERS_FX)
        metals = _fetch_group(TICKERS_METALS)
        energy = _fetch_group(TICKERS_ENERGY)
        indices = _fetch_group(TICKERS_INDICES)

        finnhub_key = os.getenv("FINNHUB_API_KEY", "").strip()
        if finnhub_key:
            _overlay_finnhub(stocks, crypto, finnhub_key)

        source = "finnhub+yfinance" if finnhub_key else "yfinance"
        updated_at = datetime.now(timezone.utc).isoformat()
        snapshot = {
            "stocks": stocks,
            "crypto": crypto,
            "fx": fx,
            "metals": metals,
            "oil": energy,
            "indices": indices,
            "financial_source": source,
            "financial_updated_at": updated_at,
            "financial": {
                "source": source,
                "updated_at": updated_at,
                "groups": {
                    "stocks": len(stocks),
                    "crypto": len(crypto),
                    "fx": len(fx),
                    "metals": len(metals),
                    "energy": len(energy),
                    "indices": len(indices),
                },
            },
        }
        _last_snapshot = snapshot

        with _data_lock:
            for key, value in snapshot.items():
                latest_data[key] = value

        for key in ("financial", "stocks", "crypto", "fx", "metals", "oil", "indices"):
            _mark_fresh(key)
