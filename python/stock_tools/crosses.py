"""Golden / dead cross detection over arbitrary MA pairs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd


CrossKind = Literal["golden", "dead"]


@dataclass
class CrossEvent:
    time: pd.Timestamp
    kind: CrossKind
    short_window: int
    long_window: int
    short_value: float
    long_value: float


def detect_crosses(short_ma: pd.Series, long_ma: pd.Series) -> pd.Series:
    """Return a Series indexed like the inputs with values: 'golden', 'dead', or ''."""
    s, l = short_ma.align(long_ma, join="inner")
    prev = (s.shift(1) - l.shift(1))
    curr = (s - l)
    golden = (prev <= 0) & (curr > 0)
    dead = (prev >= 0) & (curr < 0)
    out = pd.Series("", index=s.index, dtype="object")
    out[golden] = "golden"
    out[dead] = "dead"
    return out


def golden_dead_crosses(
    ma_df: pd.DataFrame,
    pairs: tuple[tuple[int, int], ...] = ((5, 25), (25, 75), (75, 200)),
) -> list[CrossEvent]:
    """Detect cross events across multiple MA pairs.

    ``ma_df`` must contain columns named ``ma{window}`` (as produced by
    :func:`stock_tools.indicators.moving_averages`).
    """
    events: list[CrossEvent] = []
    for short_w, long_w in pairs:
        sc = f"ma{short_w}"
        lc = f"ma{long_w}"
        if sc not in ma_df.columns or lc not in ma_df.columns:
            continue
        flags = detect_crosses(ma_df[sc], ma_df[lc])
        hits = flags[flags != ""]
        for t, kind in hits.items():
            events.append(CrossEvent(
                time=t,
                kind=kind,
                short_window=short_w,
                long_window=long_w,
                short_value=float(ma_df[sc].loc[t]),
                long_value=float(ma_df[lc].loc[t]),
            ))
    events.sort(key=lambda e: e.time)
    return events


def latest_cross(events: list[CrossEvent], pair: tuple[int, int]) -> CrossEvent | None:
    short_w, long_w = pair
    matches = [e for e in events if e.short_window == short_w and e.long_window == long_w]
    return matches[-1] if matches else None
