"""Live trading loop on top of the OANDA REST client.

Lifecycle per closed M5 bar (UTC):
    1. Sleep until next M5 boundary + buffer.
    2. Fetch latest M5/H1/D1 candles.
    3. Compute the score on the last closed bar (using existing aggregate()).
    4. Apply entry/exit rules; submit market orders with bracketed SL/TP.
    5. Log to CSV.

Safety:
    * --dry-run does everything except POST orders.
    * Daily-loss and consecutive-loss circuit breakers.
    * Position size hard cap (max_units_per_trade).
    * Refuses to start if env=live unless OANDA_ALLOW_LIVE=1 is set.
"""

from __future__ import annotations

import csv
import logging
import signal
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from ..indicators import atr
from ..scoring import aggregate
from .client import OandaClient, OandaError
from .config import OandaConfig
from .sizing import size_index_units


_LOG = logging.getLogger(__name__)

_GRAN_TO_MINUTES = {
    "S5": 5/60, "S10": 10/60, "S15": 15/60, "S30": 30/60,
    "M1": 1, "M2": 2, "M4": 4, "M5": 5, "M10": 10, "M15": 15, "M30": 30,
    "H1": 60, "H2": 120, "H3": 180, "H4": 240, "H6": 360, "H8": 480, "H12": 720,
    "D":  60*24, "D1": 60*24, "W": 60*24*7, "M": 60*24*30,
}


def next_bar_close(now: datetime, granularity: str) -> datetime:
    """Next UTC boundary at which a candle of ``granularity`` would close."""
    minutes = _GRAN_TO_MINUTES.get(granularity)
    if minutes is None or minutes < 1:
        raise ValueError(f"unsupported granularity: {granularity}")
    if granularity.startswith("M"):
        m = int(minutes)
        bucket = (now.minute // m + 1) * m
        if bucket >= 60:
            base = (now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
        else:
            base = now.replace(minute=bucket, second=0, microsecond=0)
        return base
    if granularity.startswith("H"):
        h = int(minutes // 60)
        bucket = (now.hour // h + 1) * h
        if bucket >= 24:
            base = (now.replace(hour=0, minute=0, second=0, microsecond=0)
                    + timedelta(days=1))
        else:
            base = now.replace(hour=bucket, minute=0, second=0, microsecond=0)
        return base
    # D / W / M: just next midnight UTC.
    return (now.replace(hour=0, minute=0, second=0, microsecond=0)
            + timedelta(days=1))


class LiveRunner:
    def __init__(self, cfg: OandaConfig, client: OandaClient | None = None) -> None:
        self.cfg = cfg
        self.client = client or OandaClient(cfg.token, cfg.account_id, cfg.env)
        self._stop = False
        self._consec_losses = 0
        self._day_anchor_nav: float | None = None
        self._day_anchor_date: datetime | None = None
        self._csv_initialized = False

    # ---- lifecycle -----------------------------------------------------

    def request_stop(self, *_args) -> None:
        _LOG.info("shutdown requested")
        self._stop = True

    def run(self) -> None:
        if self.cfg.env == "live" and not _live_allowed():
            raise RuntimeError(
                "Refusing to start in live mode without OANDA_ALLOW_LIVE=1")
        signal.signal(signal.SIGINT,  self.request_stop)
        signal.signal(signal.SIGTERM, self.request_stop)

        acct = self.client.get_account_summary()
        _LOG.info("connected env=%s account=%s NAV=%s %s instrument=%s dry_run=%s",
                  self.cfg.env, self.cfg.account_id, acct.get("NAV"),
                  acct.get("currency"), self.cfg.instrument, self.cfg.dry_run)

        while not self._stop:
            try:
                nxt = next_bar_close(datetime.now(timezone.utc),
                                     self.cfg.granularity_entry)
                self._sleep_until(nxt + timedelta(seconds=self.cfg.poll_buffer_sec))
                if self._stop:
                    break
                self._tick()
            except OandaError as e:
                _LOG.error("oanda error: %s", e)
                time.sleep(15)
            except Exception:
                _LOG.exception("unexpected error in runner loop")
                time.sleep(30)
        _LOG.info("runner stopped")

    def _sleep_until(self, t: datetime) -> None:
        while not self._stop:
            remaining = (t - datetime.now(timezone.utc)).total_seconds()
            if remaining <= 0:
                return
            time.sleep(min(remaining, 5.0))

    # ---- main step -----------------------------------------------------

    def _tick(self) -> None:
        cfg = self.cfg
        m5 = self.client.get_candles(cfg.instrument, cfg.granularity_entry,
                                     count=cfg.candle_lookback)
        h1 = self.client.get_candles(cfg.instrument, cfg.granularity_mid,
                                     count=cfg.candle_lookback)
        d1 = self.client.get_candles(cfg.instrument, cfg.granularity_upper,
                                     count=cfg.candle_lookback)
        if m5.empty or h1.empty or d1.empty:
            _LOG.warning("empty candles (m5=%d h1=%d d1=%d) — skipping",
                         len(m5), len(h1), len(d1))
            return

        sig = aggregate(m5, h1, d1, cfg.weights,
                        cfg.aps_lookback, cfg.aps_div_lookback, cfg.tf_cfg)
        atr_series = atr(m5, cfg.atr_period)

        last_t = m5.index[-1]
        total  = float(sig.total.iloc[-1])
        bull   = float(sig.bull_total.iloc[-1])
        bear   = float(sig.bear_total.iloc[-1])
        atr_v  = float(atr_series.iloc[-1]) if not pd.isna(atr_series.iloc[-1]) else 0.0
        price  = float(m5["close"].iloc[-1])

        # ----- daily loss / consec loss tracking ------------------------
        acct = self.client.get_account_summary()
        nav  = float(acct.get("NAV", 0.0))
        today = datetime.now(timezone.utc).date()
        if self._day_anchor_date != today:
            self._day_anchor_date = today
            self._day_anchor_nav  = nav

        daily_loss_pct = 0.0
        if self._day_anchor_nav and self._day_anchor_nav > 0:
            daily_loss_pct = 100.0 * (self._day_anchor_nav - nav) / self._day_anchor_nav

        pos = self.client.get_open_position(cfg.instrument)
        action = "HOLD"

        # ----- manage open position -------------------------------------
        if pos is not None:
            long_units  = float(pos.get("long",  {}).get("units", 0) or 0)
            short_units = float(pos.get("short", {}).get("units", 0) or 0)
            if long_units > 0 and bear >= cfg.opposite_exit_score:
                action = self._close(cfg.instrument, long=True, short=False,
                                     reason="opposite-bear")
            elif short_units < 0 and bull >= cfg.opposite_exit_score:
                action = self._close(cfg.instrument, long=False, short=True,
                                     reason="opposite-bull")
            else:
                action = "IN_POSITION"
            self._log_row(last_t, sig, total, bull, bear, atr_v, price,
                          action, nav)
            return

        # ----- gates ----------------------------------------------------
        if daily_loss_pct >= cfg.max_daily_loss_pct:
            self._log_row(last_t, sig, total, bull, bear, atr_v, price,
                          f"BLOCKED_DAILY_LOSS_{daily_loss_pct:.2f}%", nav)
            return
        if self._consec_losses >= cfg.max_consec_losses:
            self._log_row(last_t, sig, total, bull, bear, atr_v, price,
                          "BLOCKED_CONSEC_LOSS", nav)
            return
        if atr_v <= 0:
            self._log_row(last_t, sig, total, bull, bear, atr_v, price,
                          "BLOCKED_ATR_NA", nav)
            return

        # ----- entry decision ------------------------------------------
        side = None
        if total >= cfg.long_threshold:
            side = "long"
        elif total <= cfg.short_threshold:
            side = "short"

        if side is None:
            self._log_row(last_t, sig, total, bull, bear, atr_v, price,
                          "HOLD", nav)
            return

        sizing = size_index_units(nav=nav, risk_pct=cfg.risk_pct,
                                  atr_value=atr_v, sl_atr_mult=cfg.sl_atr_mult,
                                  max_units=cfg.max_units_per_trade)
        if sizing.units <= 0:
            self._log_row(last_t, sig, total, bull, bear, atr_v, price,
                          "BLOCKED_ZERO_UNITS", nav)
            return

        if side == "long":
            sl = price - sizing.sl_distance
            tp = price + sizing.sl_distance * cfg.tp_rr
            units = sizing.units
        else:
            sl = price + sizing.sl_distance
            tp = price - sizing.sl_distance * cfg.tp_rr
            units = -sizing.units

        tag = f"apsmtf-{int(time.time())}"
        if cfg.dry_run:
            _LOG.info("[DRY] %s %d %s sl=%.3f tp=%.3f score=%.2f capped=%s",
                      side.upper(), units, cfg.instrument, sl, tp, total, sizing.capped)
            action = f"DRY_OPEN_{side.upper()}"
        else:
            try:
                resp = self.client.place_market_order(cfg.instrument, units,
                                                     sl_price=sl, tp_price=tp,
                                                     client_tag=tag)
                fill = resp.get("orderFillTransaction") or {}
                _LOG.info("OPEN %s %d filled price=%s tag=%s",
                          side.upper(), units, fill.get("price"), tag)
                action = f"OPEN_{side.upper()}"
            except OandaError as e:
                _LOG.error("order rejected: %s", e)
                action = "REJECT"

        self._log_row(last_t, sig, total, bull, bear, atr_v, price, action, nav)

    def _close(self, instrument: str, long: bool, short: bool, reason: str) -> str:
        if self.cfg.dry_run:
            _LOG.info("[DRY] CLOSE %s long=%s short=%s reason=%s",
                      instrument, long, short, reason)
            return f"DRY_CLOSE_{reason}"
        try:
            resp = self.client.close_position(instrument, long=long, short=short)
            pnl_keys = ("longOrderFillTransaction", "shortOrderFillTransaction")
            for k in pnl_keys:
                fx = resp.get(k) or {}
                pl = fx.get("pl")
                if pl is not None:
                    pl_f = float(pl)
                    if pl_f < 0:
                        self._consec_losses += 1
                    else:
                        self._consec_losses = 0
                    _LOG.info("CLOSE %s pl=%s reason=%s", instrument, pl, reason)
            return f"CLOSE_{reason}"
        except OandaError as e:
            _LOG.error("close rejected: %s", e)
            return "REJECT_CLOSE"

    # ---- CSV log -------------------------------------------------------

    def _log_row(self, t, sig, total, bull, bear, atr_v, price, action, nav) -> None:
        path = self.cfg.log_csv_path
        if not path:
            return
        p = Path(path)
        header = ["time", "instrument", "tf", "score_total",
                  "bull_total", "bear_total",
                  "aps_pressure_score", "aps_div_score",
                  "d1_srsi", "d1_rci", "d1_macd",
                  "h1_srsi", "h1_rci", "h1_macd",
                  "m5_srsi", "m5_rci", "m5_macd",
                  "atr", "price", "nav", "action"]
        is_new = not p.exists()
        with p.open("a", newline="") as f:
            w = csv.writer(f)
            if is_new and not self._csv_initialized:
                w.writerow(header)
            self._csv_initialized = True
            w.writerow([
                str(t), self.cfg.instrument, self.cfg.granularity_entry,
                f"{total:.3f}", f"{bull:.3f}", f"{bear:.3f}",
                f"{float(sig.aps_pressure_score.iloc[-1]):.2f}",
                f"{float(sig.aps_div_score.iloc[-1]):.2f}",
                f"{float(sig.d1['srsi'].iloc[-1]):.2f}",
                f"{float(sig.d1['rci'].iloc[-1]):.2f}",
                f"{float(sig.d1['macd'].iloc[-1]):.2f}",
                f"{float(sig.h1['srsi'].iloc[-1]):.2f}",
                f"{float(sig.h1['rci'].iloc[-1]):.2f}",
                f"{float(sig.h1['macd'].iloc[-1]):.2f}",
                f"{float(sig.m5['srsi'].iloc[-1]):.2f}",
                f"{float(sig.m5['rci'].iloc[-1]):.2f}",
                f"{float(sig.m5['macd'].iloc[-1]):.2f}",
                f"{atr_v:.4f}", f"{price:.3f}", f"{nav:.2f}", action,
            ])


def _live_allowed() -> bool:
    import os
    return os.environ.get("OANDA_ALLOW_LIVE", "").lower() in ("1", "true", "yes")
