"""Bar-by-bar backtest engine mirroring the EA behaviour."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from . import indicators as ind
from .scoring import AggregatedSignals, ScoreWeights, aggregate
from .signals import TFConfig


@dataclass
class BacktestParams:
    long_threshold: float = 10.0
    short_threshold: float = -10.0
    opposite_exit_score: float = 8.0
    risk_pct: float = 1.0
    sl_atr_mult: float = 1.5
    tp_rr: float = 2.0
    trail_start_rr: float = 1.0
    atr_period: int = 14
    aps_lookback: int = 20
    aps_div_lookback: int = 30
    max_daily_loss_pct: float = 3.0
    max_consec_losses: int = 4
    initial_equity: float = 1_000_000.0
    fee_bps: float = 1.0           # per-side, basis points
    slippage_bps: float = 1.0      # per-side, basis points
    weights: ScoreWeights = field(default_factory=ScoreWeights)
    tf_cfg: TFConfig = field(default_factory=TFConfig)


@dataclass
class Trade:
    entry_time: pd.Timestamp
    entry_price: float
    side: str
    qty: float
    sl: float
    tp: float
    exit_time: Optional[pd.Timestamp] = None
    exit_price: Optional[float] = None
    pnl: float = 0.0
    reason: str = ""


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    trades: pd.DataFrame
    metrics: dict


def _metrics(equity: pd.Series, trades: pd.DataFrame, initial: float) -> dict:
    if equity.empty:
        return {"total_return_pct": 0.0, "sharpe": 0.0, "max_dd_pct": 0.0,
                "num_trades": 0, "win_rate": 0.0, "profit_factor": 0.0}
    rets = equity.pct_change().dropna()
    sharpe = 0.0
    if not rets.empty and rets.std() > 0:
        # Bars per year for M5 in Japanese stock session: ~5h/day * 12 bars * 245 days
        bars_per_year = 5 * 12 * 245
        sharpe = float(np.sqrt(bars_per_year) * rets.mean() / rets.std())
    peak = equity.cummax()
    dd = (equity / peak - 1.0).min()
    wins = trades[trades["pnl"] > 0]["pnl"].sum() if not trades.empty else 0.0
    losses = -trades[trades["pnl"] < 0]["pnl"].sum() if not trades.empty else 0.0
    pf = wins / losses if losses > 0 else float("inf") if wins > 0 else 0.0
    return {
        "total_return_pct": 100.0 * (equity.iloc[-1] / initial - 1.0),
        "sharpe": sharpe,
        "max_dd_pct": 100.0 * float(dd),
        "num_trades": int(len(trades)),
        "win_rate": float((trades["pnl"] > 0).mean()) if not trades.empty else 0.0,
        "profit_factor": float(pf),
    }


def run_backtest(
    m5: pd.DataFrame, h1: pd.DataFrame, d1: pd.DataFrame,
    params: BacktestParams | None = None,
    signals: AggregatedSignals | None = None,
) -> BacktestResult:
    p = params or BacktestParams()
    if signals is None:
        signals = aggregate(m5, h1, d1, p.weights, p.aps_lookback,
                            p.aps_div_lookback, p.tf_cfg)
    atr_series = ind.atr(m5, p.atr_period)

    equity = p.initial_equity
    curve = pd.Series(index=m5.index, dtype=float)

    trade: Optional[Trade] = None
    trades: list[Trade] = []
    consec_losses = 0
    locked_until: Optional[pd.Timestamp] = None
    day_start_equity = equity
    current_day: Optional[pd.Timestamp] = None

    fee_mult = (p.fee_bps + p.slippage_bps) / 10_000.0
    closes = m5["close"].values
    opens  = m5["open"].values
    highs  = m5["high"].values
    lows   = m5["low"].values
    times  = m5.index
    total  = signals.total.values
    bull   = signals.bull_total.values
    bear   = signals.bear_total.values
    atrv   = atr_series.values

    for i, t in enumerate(times):
        day = t.normalize()
        if current_day != day:
            current_day = day
            day_start_equity = equity

        # Manage open trade with intra-bar SL/TP check
        if trade is not None:
            hit_sl = (trade.side == "long"  and lows[i]  <= trade.sl) or \
                     (trade.side == "short" and highs[i] >= trade.sl)
            hit_tp = (trade.side == "long"  and highs[i] >= trade.tp) or \
                     (trade.side == "short" and lows[i]  <= trade.tp)
            opp_exit = (trade.side == "long"  and bear[i] >= p.opposite_exit_score) or \
                       (trade.side == "short" and bull[i] >= p.opposite_exit_score)

            exit_price = None
            reason = ""
            if hit_sl:
                exit_price = trade.sl
                reason = "SL"
            elif hit_tp:
                exit_price = trade.tp
                reason = "TP"
            elif opp_exit:
                exit_price = closes[i]
                reason = "OPP"

            if exit_price is not None:
                sign = 1 if trade.side == "long" else -1
                gross = sign * (exit_price - trade.entry_price) * trade.qty
                fees = fee_mult * (trade.entry_price + exit_price) * trade.qty
                trade.exit_time = t
                trade.exit_price = exit_price
                trade.pnl = gross - fees
                trade.reason = reason
                equity += trade.pnl
                trades.append(trade)
                if trade.pnl < 0:
                    consec_losses += 1
                    if consec_losses >= p.max_consec_losses:
                        locked_until = day + pd.Timedelta(days=1)
                else:
                    consec_losses = 0
                trade = None
            else:
                # Trailing
                sl_dist = abs(trade.entry_price - trade.sl)
                if sl_dist > 0:
                    if trade.side == "long":
                        rr = (closes[i] - trade.entry_price) / sl_dist
                        if rr >= p.trail_start_rr:
                            trade.sl = max(trade.sl, closes[i] - sl_dist,
                                           trade.entry_price)
                    else:
                        rr = (trade.entry_price - closes[i]) / sl_dist
                        if rr >= p.trail_start_rr:
                            new_sl = closes[i] + sl_dist
                            trade.sl = min(trade.sl, new_sl, trade.entry_price)

        # Equity snapshot using mark-to-market of open trade
        mtm = 0.0
        if trade is not None:
            sign = 1 if trade.side == "long" else -1
            mtm = sign * (closes[i] - trade.entry_price) * trade.qty
        curve.iloc[i] = equity + mtm

        # Entry gate
        if trade is not None:
            continue
        if locked_until is not None and day < locked_until:
            continue
        if day_start_equity > 0 and 100.0 * (day_start_equity - equity) / day_start_equity >= p.max_daily_loss_pct:
            continue
        if np.isnan(atrv[i]) or atrv[i] <= 0:
            continue

        sl_dist = atrv[i] * p.sl_atr_mult
        if sl_dist <= 0:
            continue
        risk_money = equity * (p.risk_pct / 100.0)
        qty = risk_money / sl_dist
        if qty <= 0:
            continue

        if total[i] >= p.long_threshold:
            entry = closes[i] * (1 + fee_mult)
            trade = Trade(entry_time=t, entry_price=entry, side="long", qty=qty,
                          sl=entry - sl_dist, tp=entry + sl_dist * p.tp_rr)
        elif total[i] <= p.short_threshold:
            entry = closes[i] * (1 - fee_mult)
            trade = Trade(entry_time=t, entry_price=entry, side="short", qty=qty,
                          sl=entry + sl_dist, tp=entry - sl_dist * p.tp_rr)

    curve = curve.ffill().fillna(p.initial_equity)
    trades_df = pd.DataFrame([{
        "entry_time": tr.entry_time, "exit_time": tr.exit_time,
        "side": tr.side, "qty": tr.qty,
        "entry": tr.entry_price, "exit": tr.exit_price,
        "sl": tr.sl, "tp": tr.tp, "pnl": tr.pnl, "reason": tr.reason,
    } for tr in trades])

    return BacktestResult(
        equity_curve=curve,
        trades=trades_df,
        metrics=_metrics(curve, trades_df, p.initial_equity),
    )
