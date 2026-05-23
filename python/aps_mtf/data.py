"""CSV data loading + timeframe resampling.

Supports two common MT5 export formats:

1. ``DATE,TIME,OPEN,HIGH,LOW,CLOSE,TICKVOL,VOL,SPREAD``
2. ``DATETIME,OPEN,HIGH,LOW,CLOSE,VOLUME`` (generic)

Returns a DataFrame indexed by UTC-naive timestamps with the columns
``open``, ``high``, ``low``, ``close``, ``volume``.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def load_csv(path: str | Path, use_real_volume: bool = False) -> pd.DataFrame:
    df = pd.read_csv(path, sep=None, engine="python")
    cols = {c.lower(): c for c in df.columns}

    if "date" in cols and "time" in cols:
        ts = pd.to_datetime(df[cols["date"]].astype(str) + " " + df[cols["time"]].astype(str),
                            format="mixed")
        out = pd.DataFrame({
            "open":  df[cols["open"]].astype(float),
            "high":  df[cols["high"]].astype(float),
            "low":   df[cols["low"]].astype(float),
            "close": df[cols["close"]].astype(float),
        }, index=ts)
        if use_real_volume and "vol" in cols:
            out["volume"] = df[cols["vol"]].astype(float)
        elif "tickvol" in cols:
            out["volume"] = df[cols["tickvol"]].astype(float)
        elif "vol" in cols:
            out["volume"] = df[cols["vol"]].astype(float)
        else:
            out["volume"] = 1.0
    else:
        ts_col = cols.get("datetime") or cols.get("timestamp") or cols.get("time")
        if ts_col is None:
            raise ValueError("No datetime column found")
        ts = pd.to_datetime(df[ts_col], format="mixed")
        vol_col = cols.get("volume") or cols.get("vol") or cols.get("tickvol")
        out = pd.DataFrame({
            "open":   df[cols["open"]].astype(float),
            "high":   df[cols["high"]].astype(float),
            "low":    df[cols["low"]].astype(float),
            "close":  df[cols["close"]].astype(float),
            "volume": df[vol_col].astype(float) if vol_col else 1.0,
        }, index=ts)

    out.index.name = "datetime"
    return out.sort_index()


def resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    agg = {"open": "first", "high": "max", "low": "min",
           "close": "last", "volume": "sum"}
    return df.resample(rule, label="right", closed="right").agg(agg).dropna()
