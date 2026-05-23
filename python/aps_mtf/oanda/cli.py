"""CLI for the OANDA live runner / one-shot diagnostics.

    python -m aps_mtf.oanda.cli ping        --config config.json
    python -m aps_mtf.oanda.cli candles     --config config.json --count 100
    python -m aps_mtf.oanda.cli score-now   --config config.json
    python -m aps_mtf.oanda.cli run         --config config.json [--live]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from .config import load_config
from .client import OandaClient
from .runner import LiveRunner


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _maybe_load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    _maybe_load_dotenv()
    parser = argparse.ArgumentParser("aps_mtf.oanda")
    parser.add_argument("--config", required=False, help="JSON config path")
    parser.add_argument("--verbose", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("ping",  help="GET /summary — verify auth + account")
    c = sub.add_parser("candles", help="Fetch recent candles for the instrument")
    c.add_argument("--granularity", default=None)
    c.add_argument("--count", type=int, default=20)

    sub.add_parser("score-now", help="One-shot: fetch all 3 TFs and print the current score")

    r = sub.add_parser("run", help="Live runner loop (Ctrl-C to stop)")
    r.add_argument("--live", action="store_true",
                   help="Disable dry-run; actually POST orders")

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    cfg = load_config(args.config) if args.config else load_config()
    if not cfg.token or not cfg.account_id:
        print("ERROR: set OANDA_TOKEN and OANDA_ACCOUNT_ID (env or .env)", file=sys.stderr)
        return 2

    client = OandaClient(cfg.token, cfg.account_id, cfg.env)

    if args.cmd == "ping":
        acct = client.get_account_summary()
        print(json.dumps({k: acct[k] for k in (
            "id", "alias", "currency", "balance", "NAV", "unrealizedPL",
            "marginAvailable", "openTradeCount", "openPositionCount"
        ) if k in acct}, indent=2))
        return 0

    if args.cmd == "candles":
        gran = args.granularity or cfg.granularity_entry
        df = client.get_candles(cfg.instrument, gran, count=args.count)
        if df.empty:
            print("(no candles returned)")
        else:
            print(df.tail(20).to_string())
        return 0

    if args.cmd == "score-now":
        from ..scoring import aggregate
        m5 = client.get_candles(cfg.instrument, cfg.granularity_entry,
                                count=cfg.candle_lookback)
        h1 = client.get_candles(cfg.instrument, cfg.granularity_mid,
                                count=cfg.candle_lookback)
        d1 = client.get_candles(cfg.instrument, cfg.granularity_upper,
                                count=cfg.candle_lookback)
        sig = aggregate(m5, h1, d1, cfg.weights, cfg.aps_lookback,
                        cfg.aps_div_lookback, cfg.tf_cfg)
        last = sig.total.index[-1]
        out = {
            "time":               str(last),
            "instrument":         cfg.instrument,
            "score_total":        round(float(sig.total.iloc[-1]), 2),
            "bull_total":         round(float(sig.bull_total.iloc[-1]), 2),
            "bear_total":         round(float(sig.bear_total.iloc[-1]), 2),
            "aps_pressure":       round(float(sig.aps_pressure_raw.iloc[-1]), 3),
            "aps_pressure_score": round(float(sig.aps_pressure_score.iloc[-1]), 2),
            "aps_div":            round(float(sig.aps_div_raw.iloc[-1]), 0),
            "d1": {k: round(float(sig.d1[k].iloc[-1]), 2) for k in ["srsi", "rci", "macd"]},
            "h1": {k: round(float(sig.h1[k].iloc[-1]), 2) for k in ["srsi", "rci", "macd"]},
            "m5": {k: round(float(sig.m5[k].iloc[-1]), 2) for k in ["srsi", "rci", "macd"]},
            "decision": ("LONG"  if sig.total.iloc[-1] >= cfg.long_threshold else
                         "SHORT" if sig.total.iloc[-1] <= cfg.short_threshold else
                         "HOLD"),
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0

    if args.cmd == "run":
        if args.live:
            cfg.dry_run = False
            if cfg.env == "live" and not os.environ.get("OANDA_ALLOW_LIVE"):
                print("ERROR: set OANDA_ALLOW_LIVE=1 to run live", file=sys.stderr)
                return 2
        runner = LiveRunner(cfg, client)
        runner.run()
        return 0

    parser.error(f"unknown command: {args.cmd}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
