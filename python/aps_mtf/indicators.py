"""Indicator math, mirroring mt5/Include/APS_MTF/*.mqh.

All functions take a DataFrame indexed by datetime with at least
``high``, ``low``, ``close`` and ``volume`` columns and return a Series
aligned to the same index. ``shift=1`` semantics from MQL5 corresponds
to ``.shift(1)`` here (i.e. use the previous closed bar).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# APS pressure / divergence
# ---------------------------------------------------------------------------

def aps_pressure(df: pd.DataFrame, lookback: int = 20) -> pd.Series:
    h, l, c, v = df["high"], df["low"], df["close"], df["volume"]
    rng = (h - l).replace(0.0, np.nan)
    mfm = ((c - l) - (h - c)) / rng
    mfv = (mfm * v).fillna(0.0)
    pos = mfv.clip(lower=0.0).rolling(lookback, min_periods=lookback).sum()
    neg = (-mfv).clip(lower=0.0).rolling(lookback, min_periods=lookback).sum()
    total = pos + neg
    return ((pos - neg) / total.where(total > 0)).fillna(0.0)


def aps_pressure_score(pressure: pd.Series) -> pd.Series:
    s = pd.Series(0.0, index=pressure.index)
    s = s.where(pressure < 0.6, 2.0)
    s = s.where(~((pressure >= 0.2) & (pressure < 0.6)), 1.0)
    s = s.where(pressure > -0.2, -1.0)
    s = s.where(pressure > -0.6, -2.0)
    return s


def aps_divergence(df: pd.DataFrame, pressure: pd.Series, lookback: int = 30) -> pd.Series:
    """Bullish +1 / bearish -1 / none 0 — same split-window method as MQL5."""
    half = lookback // 2
    h, l = df["high"], df["low"]
    # rolling extrema indices, evaluated at the right edge of the window
    rec_low_idx  = l.rolling(half).apply(lambda x: int(np.argmin(x)), raw=True)
    prev_low_idx = l.shift(half).rolling(half).apply(lambda x: int(np.argmin(x)), raw=True)
    rec_high_idx  = h.rolling(half).apply(lambda x: int(np.argmax(x)), raw=True)
    prev_high_idx = h.shift(half).rolling(half).apply(lambda x: int(np.argmax(x)), raw=True)

    def _value_at(series: pd.Series, rel_idx: pd.Series, offset: int) -> pd.Series:
        # absolute integer position of the extremum
        positions = np.arange(len(series))
        # for window ending at i with width=half, abs idx = i - (half-1) + rel
        # offset shifts the window earlier by `offset` bars.
        abs_pos = positions - (half - 1) + rel_idx.to_numpy() - offset
        abs_pos = np.where(np.isnan(abs_pos), -1, abs_pos).astype(int)
        out = np.full(len(series), np.nan)
        valid = (abs_pos >= 0) & (abs_pos < len(series))
        out[valid] = series.to_numpy()[abs_pos[valid]]
        return pd.Series(out, index=series.index)

    rec_low_price  = _value_at(l, rec_low_idx,  0)
    prev_low_price = _value_at(l, prev_low_idx, half)
    rec_low_aps    = _value_at(pressure, rec_low_idx,  0)
    prev_low_aps   = _value_at(pressure, prev_low_idx, half)

    rec_high_price  = _value_at(h, rec_high_idx,  0)
    prev_high_price = _value_at(h, prev_high_idx, half)
    rec_high_aps    = _value_at(pressure, rec_high_idx,  0)
    prev_high_aps   = _value_at(pressure, prev_high_idx, half)

    bull = (rec_low_price < prev_low_price) & (rec_low_aps > prev_low_aps)
    bear = (rec_high_price > prev_high_price) & (rec_high_aps < prev_high_aps)

    out = pd.Series(0.0, index=df.index)
    out[bull.fillna(False)] = 1.0
    out[bear.fillna(False)] = -1.0
    return out


# ---------------------------------------------------------------------------
# RCI
# ---------------------------------------------------------------------------

def rci(close: pd.Series, period: int) -> pd.Series:
    n = period
    denom = n * (n * n - 1)
    if denom <= 0:
        return pd.Series(np.nan, index=close.index)

    def _calc(window: np.ndarray) -> float:
        # window is oldest..newest; we want time_rank: newest=1 ... oldest=n
        # so reverse it so position 0 = newest.
        w = window[::-1]
        # price_rank: count strictly greater + 1 (ties resolved by earlier idx)
        sum_d2 = 0.0
        for i, vi in enumerate(w):
            higher = 0
            for j, vj in enumerate(w):
                if j == i:
                    continue
                if vj > vi or (vj == vi and j < i):
                    higher += 1
            d = (higher + 1) - (i + 1)
            sum_d2 += d * d
        return (1.0 - 6.0 * sum_d2 / denom) * 100.0

    return close.rolling(period).apply(_calc, raw=True)


# ---------------------------------------------------------------------------
# Stochastic RSI (Wilder's RSI inside)
# ---------------------------------------------------------------------------

def wilder_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    # Wilder smoothing == EMA with alpha = 1/period
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    return (100.0 - 100.0 / (1.0 + rs)).fillna(50.0)


def stoch_rsi(close: pd.Series, rsi_period: int = 14, stoch_period: int = 14,
              smooth_k: int = 3, smooth_d: int = 3) -> tuple[pd.Series, pd.Series]:
    r = wilder_rsi(close, rsi_period)
    lo = r.rolling(stoch_period).min()
    hi = r.rolling(stoch_period).max()
    rng = (hi - lo).replace(0.0, np.nan)
    raw = (100.0 * (r - lo) / rng).fillna(50.0)
    k = raw.rolling(smooth_k).mean()
    d = k.rolling(smooth_d).mean()
    return k, d


# ---------------------------------------------------------------------------
# MACD
# ---------------------------------------------------------------------------

def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
         ) -> tuple[pd.Series, pd.Series, pd.Series]:
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    line = ema_fast - ema_slow
    sig = line.ewm(span=signal, adjust=False).mean()
    return line, sig, line - sig


# ---------------------------------------------------------------------------
# ATR
# ---------------------------------------------------------------------------

def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    prev_c = c.shift(1)
    tr = pd.concat([h - l, (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
