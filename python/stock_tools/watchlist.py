"""CSV-backed watchlist.

CSV schema (header row required):

    symbol,name,long_threshold,short_threshold,enabled

- ``symbol``: yfinance ticker (e.g. ``7203.T``, ``AAPL``, ``^N225``)
- ``name``: display name (free text)
- ``long_threshold`` / ``short_threshold``: per-symbol score gates
  (leave blank to use the dashboard / scheduler defaults)
- ``enabled``: ``true`` / ``false`` (default ``true``)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass
class WatchItem:
    symbol: str
    name: str
    long_threshold: float | None
    short_threshold: float | None
    enabled: bool


def _coerce_float(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, float) and pd.isna(v):
        return None
    s = str(v).strip()
    if not s or s.lower() == "nan":
        return None
    return float(s)


def _coerce_bool(v) -> bool:
    if v is None:
        return True
    s = str(v).strip().lower()
    if s in ("", "true", "1", "yes", "y", "on"):
        return True
    return False


def load_watchlist(path: str | Path) -> list[WatchItem]:
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    if "symbol" not in df.columns:
        raise ValueError(f"watchlist {path} missing required 'symbol' column")
    items: list[WatchItem] = []
    for _, row in df.iterrows():
        sym = str(row["symbol"]).strip()
        if not sym:
            continue
        items.append(WatchItem(
            symbol=sym,
            name=str(row.get("name", sym)).strip() or sym,
            long_threshold=_coerce_float(row.get("long_threshold")),
            short_threshold=_coerce_float(row.get("short_threshold")),
            enabled=_coerce_bool(row.get("enabled")),
        ))
    return [it for it in items if it.enabled]
