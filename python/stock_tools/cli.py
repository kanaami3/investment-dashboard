"""CLI entry points for stock_tools.

Subcommands:
    analyze   — one-shot console analysis for a single symbol
    score     — print latest APS+MTF score
    notify    — send a single test message to Discord
    watch     — run the hourly polling scheduler
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from .crosses import golden_dead_crosses
from .data import fetch_history, fetch_mtf
from .indicators import bollinger_bands, macd, moving_averages, rsi
from .notifier import DiscordNotifier
from .scheduler import SchedulerConfig, run as scheduler_run
from .signal import StockSignalConfig, score_latest


def _cmd_analyze(args: argparse.Namespace) -> int:
    df = fetch_history(args.symbol, interval=args.interval, period=args.period)
    if df.empty:
        print(f"no data for {args.symbol}")
        return 1
    mas = moving_averages(df["close"])
    rsi_s = rsi(df["close"])
    macd_r = macd(df["close"])
    bb = bollinger_bands(df["close"])
    crosses = golden_dead_crosses(mas)

    last = df.iloc[-1]
    print(f"{args.symbol}  {df.index[-1].isoformat()}")
    print(f"  close   {last['close']:,.2f}")
    print(f"  ma5     {mas['ma5'].iloc[-1]:,.2f}")
    print(f"  ma25    {mas['ma25'].iloc[-1]:,.2f}")
    print(f"  ma75    {mas['ma75'].iloc[-1]:,.2f}")
    print(f"  ma200   {mas['ma200'].iloc[-1]:,.2f}")
    print(f"  rsi14   {rsi_s.iloc[-1]:.1f}")
    print(f"  macd    {macd_r.macd.iloc[-1]:+.3f}  signal {macd_r.signal.iloc[-1]:+.3f}  hist {macd_r.hist.iloc[-1]:+.3f}")
    print(f"  bb      mid {bb.middle.iloc[-1]:,.2f}  upper {bb.upper.iloc[-1]:,.2f}  lower {bb.lower.iloc[-1]:,.2f}")
    print(f"  recent crosses (last 5):")
    for e in crosses[-5:]:
        print(f"    {e.time.date()}  {e.kind.upper():6s}  ma{e.short_window}/ma{e.long_window}")
    return 0


def _cmd_score(args: argparse.Namespace) -> int:
    entry, mid, upper = fetch_mtf(args.symbol)
    sig = score_latest(entry, mid, upper, StockSignalConfig(
        long_threshold=args.long_threshold,
        short_threshold=args.short_threshold,
    ))
    if sig is None:
        print(f"no data for {args.symbol}")
        return 1
    out = {
        "symbol": args.symbol,
        "time": sig.time.isoformat(),
        "decision": sig.decision,
        "total": sig.total,
        "bull_total": sig.bull_total,
        "bear_total": sig.bear_total,
        "components": sig.components,
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def _cmd_notify(args: argparse.Namespace) -> int:
    notifier = DiscordNotifier.from_env()
    notifier.send(content=args.message)
    print("sent")
    return 0


def _cmd_watch(args: argparse.Namespace) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    cfg = SchedulerConfig(
        watchlist_path=args.watchlist,
        interval_minutes=args.interval,
        align_to_top_of_hour=not args.no_align,
        notify_on=tuple(args.notify_on.split(",")),
    )
    scheduler_run(cfg)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="stock_tools")
    p.add_argument("--env-file", default=".env", help="path to .env (default: .env in cwd)")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("analyze", help="one-shot indicator dump")
    a.add_argument("symbol")
    a.add_argument("--interval", default="1d")
    a.add_argument("--period", default=None)
    a.set_defaults(func=_cmd_analyze)

    s = sub.add_parser("score", help="latest APS+MTF score")
    s.add_argument("symbol")
    s.add_argument("--long-threshold", type=float, default=6.0)
    s.add_argument("--short-threshold", type=float, default=-6.0)
    s.set_defaults(func=_cmd_score)

    n = sub.add_parser("notify", help="send a test Discord message")
    n.add_argument("--message", default="stock_tools notify test")
    n.set_defaults(func=_cmd_notify)

    w = sub.add_parser("watch", help="run the hourly polling loop")
    w.add_argument("--watchlist", required=True)
    w.add_argument("--interval", type=int, default=60, help="minutes between checks")
    w.add_argument("--no-align", action="store_true", help="do not align to top of hour")
    w.add_argument("--notify-on", default="LONG,SHORT", help="comma-separated decisions to notify")
    w.set_defaults(func=_cmd_watch)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    env_path = Path(args.env_file)
    if env_path.exists():
        load_dotenv(env_path)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
