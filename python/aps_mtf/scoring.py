"""Weighted aggregation mirroring mt5/Include/APS_MTF/Scoring.mqh."""

from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd

from . import indicators as ind
from .signals import TFConfig, tf_scores


@dataclass
class ScoreWeights:
    w_aps_pressure: float = 2.5
    w_aps_divergence: float = 3.0
    w_d1_srsi: float = 1.0
    w_d1_rci:  float = 1.0
    w_d1_macd: float = 1.5
    w_h1_srsi: float = 1.5
    w_h1_rci:  float = 1.5
    w_h1_macd: float = 2.0
    w_m5_srsi: float = 2.0
    w_m5_rci:  float = 2.0
    w_m5_macd: float = 1.0


def default_weights() -> ScoreWeights:
    return ScoreWeights()


@dataclass
class AggregatedSignals:
    """All columns aligned to the M5 (entry) index."""
    aps_pressure_raw: pd.Series
    aps_pressure_score: pd.Series
    aps_div_raw: pd.Series
    aps_div_score: pd.Series
    d1: pd.DataFrame  # srsi, rci, macd
    h1: pd.DataFrame
    m5: pd.DataFrame
    bull_total: pd.Series
    bear_total: pd.Series
    total: pd.Series


def _align_to(idx: pd.DatetimeIndex, src: pd.DataFrame | pd.Series) -> pd.DataFrame | pd.Series:
    """Forward-fill higher-TF series onto the lower-TF index, using only
    closed bars (shift by 1 on the source TF first)."""
    shifted = src.shift(1)
    return shifted.reindex(idx, method="ffill")


def aggregate(
    m5: pd.DataFrame,
    h1: pd.DataFrame,
    d1: pd.DataFrame,
    weights: ScoreWeights | None = None,
    aps_lookback: int = 20,
    aps_div_lookback: int = 30,
    tf_cfg: TFConfig | None = None,
) -> AggregatedSignals:
    weights = weights or ScoreWeights()
    tf_cfg = tf_cfg or TFConfig()

    pressure = ind.aps_pressure(m5, lookback=aps_lookback)
    press_score = ind.aps_pressure_score(pressure)
    div = ind.aps_divergence(m5, pressure, lookback=aps_div_lookback)
    div_score = 2.0 * div

    m5_s = tf_scores(m5, tf_cfg)
    h1_s = tf_scores(h1, tf_cfg)
    d1_s = tf_scores(d1, tf_cfg)

    # Use only closed bars; align HTFs to M5 index.
    m5_s_lag = m5_s.shift(1)
    h1_aligned = _align_to(m5.index, h1_s)
    d1_aligned = _align_to(m5.index, d1_s)

    pressure_lag = pressure.shift(1)
    press_score_lag = press_score.shift(1)
    div_lag = div.shift(1)
    div_score_lag = div_score.shift(1)

    contribs = {
        "aps_p": press_score_lag * weights.w_aps_pressure,
        "aps_d": div_score_lag   * weights.w_aps_divergence,
        "d1_srsi": d1_aligned["srsi"] * weights.w_d1_srsi,
        "d1_rci":  d1_aligned["rci"]  * weights.w_d1_rci,
        "d1_macd": d1_aligned["macd"] * weights.w_d1_macd,
        "h1_srsi": h1_aligned["srsi"] * weights.w_h1_srsi,
        "h1_rci":  h1_aligned["rci"]  * weights.w_h1_rci,
        "h1_macd": h1_aligned["macd"] * weights.w_h1_macd,
        "m5_srsi": m5_s_lag["srsi"] * weights.w_m5_srsi,
        "m5_rci":  m5_s_lag["rci"]  * weights.w_m5_rci,
        "m5_macd": m5_s_lag["macd"] * weights.w_m5_macd,
    }
    df = pd.DataFrame(contribs).fillna(0.0)
    bull = df.clip(lower=0.0).sum(axis=1)
    bear = (-df).clip(lower=0.0).sum(axis=1)
    total = df.sum(axis=1)

    return AggregatedSignals(
        aps_pressure_raw=pressure_lag.fillna(0.0),
        aps_pressure_score=press_score_lag.fillna(0.0),
        aps_div_raw=div_lag.fillna(0.0),
        aps_div_score=div_score_lag.fillna(0.0),
        d1=d1_aligned.fillna(0.0),
        h1=h1_aligned.fillna(0.0),
        m5=m5_s_lag.fillna(0.0),
        bull_total=bull,
        bear_total=bear,
        total=total,
    )


def weights_from_dict(d: dict) -> ScoreWeights:
    base = asdict(ScoreWeights())
    base.update({k: v for k, v in d.items() if k in base})
    return ScoreWeights(**base)
