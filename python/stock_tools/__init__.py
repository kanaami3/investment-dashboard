"""Stock technical analysis + APS+MTF alerting toolkit.

Public modules:

- ``data``        — yfinance fetch helpers
- ``indicators``  — MA / RSI / MACD / Bollinger
- ``crosses``     — golden / dead cross detection
- ``signal``      — bridge to aps_mtf.scoring for entry/exit timing
- ``watchlist``   — CSV-based symbol list
- ``notifier``    — LINE Messaging API push
- ``scheduler``   — hourly polling loop
- ``dashboard``   — Streamlit UI (run with ``streamlit run -m stock_tools.dashboard``)
"""

from .data import fetch_history
from .indicators import (
    moving_averages,
    rsi,
    macd,
    bollinger_bands,
)
from .crosses import golden_dead_crosses

__all__ = [
    "fetch_history",
    "moving_averages",
    "rsi",
    "macd",
    "bollinger_bands",
    "golden_dead_crosses",
]
