"""Config dataclass for the OANDA live runner."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path

from ..backtest import BacktestParams
from ..scoring import ScoreWeights, weights_from_dict
from ..signals import TFConfig


@dataclass
class OandaConfig:
    # --- connection ---
    env: str = "practice"                   # "practice" | "live"
    token: str = ""                         # OANDA API token
    account_id: str = ""                    # e.g. "101-001-1234567-001"

    # --- instrument / timeframes ---
    instrument: str = "JP225_JPY"           # OANDA Japan Nikkei 225 CFD
    granularity_entry: str = "M5"           # lower TF
    granularity_mid:   str = "H1"
    granularity_upper: str = "D1"
    candle_lookback: int = 500              # bars fetched per TF on each tick

    # --- strategy (mirrors BacktestParams / ScoreWeights) ---
    long_threshold: float = 10.0
    short_threshold: float = -10.0
    opposite_exit_score: float = 8.0
    risk_pct: float = 0.5                   # of NAV per trade; conservative default
    sl_atr_mult: float = 1.5
    tp_rr: float = 2.0
    trail_start_rr: float = 1.0
    atr_period: int = 14
    aps_lookback: int = 20
    aps_div_lookback: int = 30
    weights: ScoreWeights = field(default_factory=ScoreWeights)
    tf_cfg:  TFConfig     = field(default_factory=TFConfig)

    # --- runtime safety ---
    dry_run: bool = True                    # log orders but do not POST
    poll_buffer_sec: int = 8                # wait after bar close before polling
    max_units_per_trade: int = 50           # JP225: 1 unit = 1 JPY/pt; cap exposure
    max_daily_loss_pct: float = 3.0
    max_consec_losses: int = 4
    heartbeat_sec: int = 300                # log account summary every N sec
    log_csv_path: str | None = "oanda_runner.csv"


def _drop_missing(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


def load_config(path: str | Path | None = None) -> OandaConfig:
    """Load JSON config; env vars override token / account / env."""
    blob: dict = {}
    if path is not None:
        blob = json.loads(Path(path).read_text())
    cfg = OandaConfig()
    fields = {k for k in vars(cfg).keys() if k not in {"weights", "tf_cfg"}}
    for k, v in blob.items():
        if k in fields:
            setattr(cfg, k, v)
    if "weights" in blob:
        cfg.weights = weights_from_dict(blob["weights"])
    if "tf_cfg" in blob:
        tf = TFConfig()
        for k, v in blob["tf_cfg"].items():
            if hasattr(tf, k):
                setattr(tf, k, v)
        cfg.tf_cfg = tf

    # env override (so tokens never end up in JSON committed to git)
    cfg.token      = os.environ.get("OANDA_TOKEN",      cfg.token)
    cfg.account_id = os.environ.get("OANDA_ACCOUNT_ID", cfg.account_id)
    cfg.env        = os.environ.get("OANDA_ENV",        cfg.env)
    if os.environ.get("OANDA_DRY_RUN") is not None:
        cfg.dry_run = os.environ["OANDA_DRY_RUN"].lower() not in ("0", "false", "no")
    return cfg


def to_backtest_params(cfg: OandaConfig, initial_equity: float = 1.0) -> BacktestParams:
    """Map runtime config into the offline BacktestParams shape (for parity tests)."""
    return BacktestParams(
        long_threshold=cfg.long_threshold,
        short_threshold=cfg.short_threshold,
        opposite_exit_score=cfg.opposite_exit_score,
        risk_pct=cfg.risk_pct,
        sl_atr_mult=cfg.sl_atr_mult,
        tp_rr=cfg.tp_rr,
        trail_start_rr=cfg.trail_start_rr,
        atr_period=cfg.atr_period,
        aps_lookback=cfg.aps_lookback,
        aps_div_lookback=cfg.aps_div_lookback,
        max_daily_loss_pct=cfg.max_daily_loss_pct,
        max_consec_losses=cfg.max_consec_losses,
        initial_equity=initial_equity,
        weights=cfg.weights,
        tf_cfg=cfg.tf_cfg,
    )
