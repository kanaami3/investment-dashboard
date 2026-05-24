"""Streamlit dashboard for stock technical analysis.

Run:
    streamlit run python/stock_tools/dashboard.py

Sidebar inputs:
- Symbol (yfinance ticker, e.g. 7203.T / AAPL / ^N225)
- Interval (1d / 1h / 60m ...)
- Period
- MA windows
- Score thresholds

Tabs:
- Chart (price + MA + Bollinger, RSI subplot, MACD subplot)
- APS+MTF score (the EA timing)
- Cross history (golden / dead events table)
- Raw data
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from stock_tools.crosses import golden_dead_crosses
from stock_tools.data import fetch_history, fetch_mtf
from stock_tools.indicators import bollinger_bands, macd, moving_averages, rsi
from stock_tools.signal import StockSignalConfig, score_latest


st.set_page_config(page_title="Stock TA Dashboard", layout="wide")


@st.cache_data(ttl=300, show_spinner=False)
def _cached_history(symbol: str, interval: str, period: str) -> pd.DataFrame:
    return fetch_history(symbol, interval=interval, period=period)


@st.cache_data(ttl=300, show_spinner=False)
def _cached_mtf(symbol: str, entry: str, mid: str, upper: str):
    return fetch_mtf(symbol, entry=entry, mid=mid, upper=upper)


def _price_figure(df: pd.DataFrame, mas: pd.DataFrame, bb, ma_windows: list[int]) -> go.Figure:
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.03,
        row_heights=[0.6, 0.2, 0.2],
        subplot_titles=("Price + MA + Bollinger", "RSI(14)", "MACD"),
    )
    fig.add_trace(go.Candlestick(
        x=df.index, open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        name="OHLC", showlegend=False,
    ), row=1, col=1)
    fig.add_trace(go.Scatter(x=bb.upper.index, y=bb.upper, name="BB upper",
                              line=dict(color="rgba(120,120,120,0.6)", width=1)), row=1, col=1)
    fig.add_trace(go.Scatter(x=bb.lower.index, y=bb.lower, name="BB lower",
                              line=dict(color="rgba(120,120,120,0.6)", width=1),
                              fill="tonexty", fillcolor="rgba(120,120,120,0.08)"), row=1, col=1)
    colors = ["#e74c3c", "#f39c12", "#2ecc71", "#3498db"]
    for w, color in zip(ma_windows, colors):
        col = f"ma{w}"
        if col in mas.columns:
            fig.add_trace(go.Scatter(x=mas.index, y=mas[col], name=col.upper(),
                                      line=dict(color=color, width=1.3)), row=1, col=1)
    fig.update_layout(
        height=750,
        xaxis_rangeslider_visible=False,
        margin=dict(l=10, r=10, t=40, b=10),
        legend=dict(orientation="h", y=1.02, x=0),
    )
    return fig


def _add_rsi_macd(fig: go.Figure, rsi_s: pd.Series, macd_r) -> None:
    fig.add_trace(go.Scatter(x=rsi_s.index, y=rsi_s, name="RSI14",
                              line=dict(color="#9b59b6", width=1.2)), row=2, col=1)
    fig.add_hline(y=70, line=dict(color="rgba(255,0,0,0.4)", dash="dot"), row=2, col=1)
    fig.add_hline(y=30, line=dict(color="rgba(0,180,0,0.4)", dash="dot"), row=2, col=1)
    fig.update_yaxes(range=[0, 100], row=2, col=1)

    fig.add_trace(go.Scatter(x=macd_r.macd.index, y=macd_r.macd, name="MACD",
                              line=dict(color="#3498db", width=1.2)), row=3, col=1)
    fig.add_trace(go.Scatter(x=macd_r.signal.index, y=macd_r.signal, name="Signal",
                              line=dict(color="#e67e22", width=1.2)), row=3, col=1)
    hist_colors = ["#2ecc71" if v >= 0 else "#e74c3c" for v in macd_r.hist.fillna(0.0)]
    fig.add_trace(go.Bar(x=macd_r.hist.index, y=macd_r.hist, name="Hist",
                          marker_color=hist_colors, opacity=0.5), row=3, col=1)


def main() -> None:
    st.title("Stock TA Dashboard")

    with st.sidebar:
        st.header("Inputs")
        symbol = st.text_input("Symbol", value="7203.T", help="yfinance ticker")
        interval = st.selectbox("Interval", ["1d", "60m", "1h", "1wk", "1mo"], index=0)
        period_default = {"1d": "2y", "60m": "60d", "1h": "60d", "1wk": "5y", "1mo": "10y"}[interval]
        period = st.text_input("Period", value=period_default)

        st.markdown("---")
        st.header("MAs")
        windows_text = st.text_input("MA windows (comma)", value="5,25,75,200")
        try:
            ma_windows = [int(x.strip()) for x in windows_text.split(",") if x.strip()]
        except ValueError:
            st.error("MA windows must be integers")
            return

        st.markdown("---")
        st.header("APS+MTF score")
        long_thr = st.number_input("Long threshold", value=6.0, step=0.5)
        short_thr = st.number_input("Short threshold", value=-6.0, step=0.5)

    if not symbol:
        st.info("enter a symbol in the sidebar")
        return

    df = _cached_history(symbol, interval, period)
    if df.empty:
        st.error(f"no data for {symbol}")
        return

    mas = moving_averages(df["close"], windows=tuple(ma_windows))
    rsi_s = rsi(df["close"])
    macd_r = macd(df["close"])
    bb = bollinger_bands(df["close"])
    crosses = golden_dead_crosses(mas, pairs=tuple(zip(ma_windows[:-1], ma_windows[1:])))

    tab_chart, tab_score, tab_crosses, tab_raw = st.tabs(
        ["Chart", "APS+MTF Score", "Crosses", "Raw data"]
    )

    with tab_chart:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Close", f"{df['close'].iloc[-1]:,.2f}",
                  delta=f"{df['close'].iloc[-1] - df['close'].iloc[-2]:+.2f}")
        c2.metric("RSI(14)", f"{rsi_s.iloc[-1]:.1f}")
        c3.metric("MACD hist", f"{macd_r.hist.iloc[-1]:+.3f}")
        bb_pos = (df['close'].iloc[-1] - bb.lower.iloc[-1]) / (bb.upper.iloc[-1] - bb.lower.iloc[-1])
        c4.metric("%B", f"{bb_pos:.2f}")

        fig = _price_figure(df, mas, bb, ma_windows)
        _add_rsi_macd(fig, rsi_s, macd_r)
        st.plotly_chart(fig, use_container_width=True)

    with tab_score:
        st.subheader("APS+MTF latest score (EA-equivalent timing)")
        st.caption("Entry=60m / Mid=1d / Upper=1wk")
        entry, mid, upper = _cached_mtf(symbol, "60m", "1d", "1wk")
        if entry.empty or mid.empty or upper.empty:
            st.warning("one of the MTF frames is empty (try a different symbol or period)")
        else:
            sig = score_latest(entry, mid, upper, StockSignalConfig(
                long_threshold=long_thr, short_threshold=short_thr,
            ))
            if sig is None:
                st.warning("could not compute score")
            else:
                color = {"LONG": "🟢", "SHORT": "🔴", "HOLD": "⚪"}[sig.decision]
                st.markdown(f"### {color} {sig.decision}   |   total = {sig.total:+.2f}")
                c1, c2, c3 = st.columns(3)
                c1.metric("Total", f"{sig.total:+.2f}")
                c2.metric("Bull", f"{sig.bull_total:+.2f}")
                c3.metric("Bear", f"{sig.bear_total:+.2f}")
                comp_df = pd.DataFrame(
                    sorted(sig.components.items(), key=lambda kv: -abs(kv[1])),
                    columns=["component", "value"],
                )
                st.dataframe(comp_df, use_container_width=True, hide_index=True)

    with tab_crosses:
        st.subheader("Golden / Dead crosses")
        rows = [{
            "time": e.time,
            "kind": e.kind,
            "pair": f"ma{e.short_window}/ma{e.long_window}",
            "short": round(e.short_value, 2),
            "long": round(e.long_value, 2),
        } for e in crosses[::-1]]
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("no cross events in the loaded history")

    with tab_raw:
        st.dataframe(df.tail(200), use_container_width=True)


if __name__ == "__main__":
    main()
