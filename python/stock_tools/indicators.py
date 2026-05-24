"""Classical technical indicators (MA / RSI / MACD / Bollinger).

Kept independent of ``aps_mtf.indicators`` so this module remains usable
standalone for the dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


def moving_averages(close: pd.Series, windows: tuple[int, ...] = (5, 25, 75, 200)) -> pd.DataFrame:
    """SMA for each window. Columns are ``ma{w}``."""
    return pd.DataFrame({f"ma{w}": close.rolling(w, min_periods=w).mean() for w in windows})


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    return (100 - (100 / (1 + rs))).rename("rsi")


@dataclass
class MACDResult:
    macd: pd.Series
    signal: pd.Series
    hist: pd.Series


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> MACDResult:
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = (ema_fast - ema_slow).rename("macd")
    sig_line = macd_line.ewm(span=signal, adjust=False).mean().rename("macd_signal")
    hist = (macd_line - sig_line).rename("macd_hist")
    return MACDResult(macd=macd_line, signal=sig_line, hist=hist)


@dataclass
class BollingerResult:
    middle: pd.Series
    upper: pd.Series
    lower: pd.Series
    bandwidth: pd.Series
    percent_b: pd.Series


def bollinger_bands(close: pd.Series, period: int = 20, std_mult: float = 2.0) -> BollingerResult:
    mid = close.rolling(period, min_periods=period).mean()
    std = close.rolling(period, min_periods=period).std(ddof=0)
    upper = mid + std_mult * std
    lower = mid - std_mult * std
    bandwidth = (upper - lower) / mid
    percent_b = (close - lower) / (upper - lower)
    return BollingerResult(
        middle=mid.rename("bb_mid"),
        upper=upper.rename("bb_upper"),
        lower=lower.rename("bb_lower"),
        bandwidth=bandwidth.rename("bb_bandwidth"),
        percent_b=percent_b.rename("bb_percent_b"),
    )
