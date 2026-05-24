"""yfinance fetch helpers.

Returns DataFrames with the column convention used by ``aps_mtf``:
``open / high / low / close / volume``, indexed by UTC-naive timestamps.
"""

from __future__ import annotations

from typing import Literal

import pandas as pd
import yfinance as yf


Interval = Literal["1m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo", "3mo"]


_MAX_PERIOD_BY_INTERVAL = {
    "1m": "7d",
    "5m": "60d",
    "15m": "60d",
    "30m": "60d",
    "60m": "730d",
    "90m": "60d",
    "1h": "730d",
    "1d": "max",
    "5d": "max",
    "1wk": "max",
    "1mo": "max",
    "3mo": "max",
}


def fetch_history(
    symbol: str,
    interval: Interval = "1d",
    period: str | None = None,
    auto_adjust: bool = True,
) -> pd.DataFrame:
    """Fetch OHLCV for a symbol via yfinance.

    Returns columns ``open, high, low, close, volume`` with a tz-naive index.
    When ``period`` is None we pick the maximum yfinance allows for the interval.
    """
    period = period or _MAX_PERIOD_BY_INTERVAL.get(interval, "1y")
    df = yf.download(
        symbol,
        interval=interval,
        period=period,
        auto_adjust=auto_adjust,
        progress=False,
        threads=False,
    )
    if df is None or df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.rename(columns=str.lower)
    out = pd.DataFrame({
        "open":   df["open"].astype(float),
        "high":   df["high"].astype(float),
        "low":    df["low"].astype(float),
        "close":  df["close"].astype(float),
        "volume": df.get("volume", pd.Series(1.0, index=df.index)).astype(float).fillna(0.0),
    }, index=df.index)

    if out.index.tz is not None:
        out.index = out.index.tz_convert("UTC").tz_localize(None)
    out.index.name = "time"
    return out.dropna(subset=["close"])


def fetch_mtf(
    symbol: str,
    entry: Interval = "60m",
    mid: Interval = "1d",
    upper: Interval = "1wk",
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Convenience: fetch three timeframes for ``aps_mtf.scoring.aggregate``.

    Defaults are tuned for hourly-checked swing trading on stocks:
    entry=60m, mid=1d, upper=1wk.
    """
    e = fetch_history(symbol, interval=entry)
    m = fetch_history(symbol, interval=mid)
    u = fetch_history(symbol, interval=upper)
    return e, m, u
