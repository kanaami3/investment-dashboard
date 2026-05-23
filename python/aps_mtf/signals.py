"""Per-timeframe scoring, mirroring mt5/Include/APS_MTF/MTFSignals.mqh."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import indicators as ind


@dataclass
class TFConfig:
    rsi_period: int = 14
    stoch_period: int = 14
    smooth_k: int = 3
    smooth_d: int = 3
    rci_short: int = 9
    rci_long: int = 26
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9


def _score_srsi(k: pd.Series, d: pd.Series) -> pd.Series:
    k_prev, d_prev = k.shift(1), d.shift(1)
    bull_cross = (k_prev <= d_prev) & (k > d) & (k < 20) & (d < 20)
    bear_cross = (k_prev >= d_prev) & (k < d) & (k > 80) & (d > 80)
    up   = (k > d) & (k > k_prev)
    down = (k < d) & (k < k_prev)
    out = pd.Series(0.0, index=k.index)
    out[up]         =  1.0
    out[down]       = -1.0
    out[bull_cross] =  2.0
    out[bear_cross] = -2.0
    return out


def _score_rci(rs: pd.Series, rl: pd.Series) -> pd.Series:
    rs_prev = rs.shift(1)
    exit_low  = (rs_prev <= -80) & (rs > -80)
    exit_high = (rs_prev >=  80) & (rs <  80)
    same_pos = (rs > 0) & (rl > 0)
    same_neg = (rs < 0) & (rl < 0)
    out = pd.Series(0.0, index=rs.index)
    out[same_pos]  =  1.0
    out[same_neg]  = -1.0
    out[exit_low]  =  2.0
    out[exit_high] = -2.0
    return out


def _score_macd(line: pd.Series, sig: pd.Series, hist: pd.Series) -> pd.Series:
    hist_prev = hist.shift(1)
    flip_up   = (hist_prev <= 0) & (hist > 0) & (line < 0)
    flip_down = (hist_prev >= 0) & (hist < 0) & (line > 0)
    out = pd.Series(0.0, index=line.index)
    out[line > sig] =  1.0
    out[line < sig] = -1.0
    out[flip_up]    =  2.0
    out[flip_down]  = -2.0
    return out


def tf_scores(df: pd.DataFrame, cfg: TFConfig | None = None) -> pd.DataFrame:
    """Returns columns: srsi, rci, macd (each in [-2, +2])."""
    cfg = cfg or TFConfig()
    k, d = ind.stoch_rsi(df["close"], cfg.rsi_period, cfg.stoch_period,
                         cfg.smooth_k, cfg.smooth_d)
    rs = ind.rci(df["close"], cfg.rci_short)
    rl = ind.rci(df["close"], cfg.rci_long)
    m, s, h = ind.macd(df["close"], cfg.macd_fast, cfg.macd_slow, cfg.macd_signal)
    return pd.DataFrame({
        "srsi": _score_srsi(k, d),
        "rci":  _score_rci(rs, rl),
        "macd": _score_macd(m, s, h),
    })
