"""Bridge from yfinance MTF data to ``aps_mtf.scoring.aggregate``.

For stocks we map the EA's three-TF model as:

| EA name | EA timeframe | Stocks (hourly check) |
|---------|--------------|-----------------------|
| ``m5``  | M5 entry     | 60m intraday          |
| ``h1``  | H1 mid       | 1d daily              |
| ``d1``  | D1 upper     | 1wk weekly            |

The scoring math is unchanged: we just feed different bar sizes.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from aps_mtf.scoring import aggregate, ScoreWeights, AggregatedSignals


@dataclass
class StockSignalConfig:
    long_threshold: float = 6.0
    short_threshold: float = -6.0
    opposite_exit_score: float = 4.0
    weights: ScoreWeights | None = None
    aps_lookback: int = 20
    aps_div_lookback: int = 30


@dataclass
class StockSignal:
    time: pd.Timestamp
    total: float
    bull_total: float
    bear_total: float
    decision: str  # 'LONG' | 'SHORT' | 'HOLD'
    components: dict[str, float]


def score_latest(
    entry: pd.DataFrame,
    mid: pd.DataFrame,
    upper: pd.DataFrame,
    cfg: StockSignalConfig | None = None,
) -> StockSignal | None:
    """Compute aggregated score for the most recent entry bar.

    Returns None if any required frame is empty.
    """
    cfg = cfg or StockSignalConfig()
    if entry.empty or mid.empty or upper.empty:
        return None

    agg: AggregatedSignals = aggregate(
        m5=entry,
        h1=mid,
        d1=upper,
        weights=cfg.weights,
        aps_lookback=cfg.aps_lookback,
        aps_div_lookback=cfg.aps_div_lookback,
    )
    t = entry.index[-1]
    total = float(agg.total.iloc[-1])
    bull = float(agg.bull_total.iloc[-1])
    bear = float(agg.bear_total.iloc[-1])

    if total >= cfg.long_threshold:
        decision = "LONG"
    elif total <= cfg.short_threshold:
        decision = "SHORT"
    else:
        decision = "HOLD"

    components = {
        "aps_pressure_score": float(agg.aps_pressure_score.iloc[-1]),
        "aps_div_score":      float(agg.aps_div_score.iloc[-1]),
        "d1_srsi": float(agg.d1["srsi"].iloc[-1]),
        "d1_rci":  float(agg.d1["rci"].iloc[-1]),
        "d1_macd": float(agg.d1["macd"].iloc[-1]),
        "h1_srsi": float(agg.h1["srsi"].iloc[-1]),
        "h1_rci":  float(agg.h1["rci"].iloc[-1]),
        "h1_macd": float(agg.h1["macd"].iloc[-1]),
        "m5_srsi": float(agg.m5["srsi"].iloc[-1]),
        "m5_rci":  float(agg.m5["rci"].iloc[-1]),
        "m5_macd": float(agg.m5["macd"].iloc[-1]),
    }
    return StockSignal(
        time=t,
        total=total,
        bull_total=bull,
        bear_total=bear,
        decision=decision,
        components=components,
    )
