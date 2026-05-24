"""Hourly polling loop that scores watchlist symbols and notifies via Discord.

Run via the CLI:
    python -m stock_tools.cli watch --watchlist examples/watchlist.csv

State (last sent decision per symbol) is kept in memory so identical signals
on consecutive hours do not re-spam the channel. Restart the process to reset.
"""

from __future__ import annotations

import logging
import signal as _signal
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .crosses import golden_dead_crosses
from .data import fetch_history, fetch_mtf
from .indicators import moving_averages
from .notifier import DiscordNotifier, format_signal_embed
from .signal import StockSignalConfig, score_latest
from .watchlist import WatchItem, load_watchlist

LOGGER = logging.getLogger("stock_tools.scheduler")


@dataclass
class SchedulerConfig:
    watchlist_path: str
    interval_minutes: int = 60
    notify_on: tuple[str, ...] = ("LONG", "SHORT")  # add "HOLD" to also send no-op pulses
    notify_cross_today: bool = True
    signal: StockSignalConfig = field(default_factory=StockSignalConfig)
    align_to_top_of_hour: bool = True


def _seconds_until_next_tick(interval_min: int, align: bool) -> float:
    now = datetime.now(timezone.utc)
    if align and interval_min == 60:
        nxt = (now.replace(minute=0, second=10, microsecond=0) + timedelta(hours=1))
        return max(1.0, (nxt - now).total_seconds())
    return interval_min * 60.0


def _check_one(item: WatchItem, cfg: SchedulerConfig) -> tuple[dict | None, str]:
    """Return (embed_dict_or_None, decision)."""
    entry, mid, upper = fetch_mtf(item.symbol)
    if entry.empty or mid.empty or upper.empty:
        return None, "NO_DATA"

    scfg = StockSignalConfig(
        long_threshold=item.long_threshold if item.long_threshold is not None else cfg.signal.long_threshold,
        short_threshold=item.short_threshold if item.short_threshold is not None else cfg.signal.short_threshold,
        opposite_exit_score=cfg.signal.opposite_exit_score,
        weights=cfg.signal.weights,
        aps_lookback=cfg.signal.aps_lookback,
        aps_div_lookback=cfg.signal.aps_div_lookback,
    )
    sig = score_latest(entry, mid, upper, scfg)
    if sig is None:
        return None, "NO_DATA"

    extra: list[str] = []
    if cfg.notify_cross_today:
        daily = fetch_history(item.symbol, interval="1d", period="2y")
        if not daily.empty:
            mas = moving_averages(daily["close"])
            events = golden_dead_crosses(mas)
            today = datetime.now(timezone.utc).date()
            todays = [e for e in events if e.time.date() == today]
            for e in todays:
                arrow = "↑" if e.kind == "golden" else "↓"
                extra.append(f"{arrow} {e.kind.upper()} CROSS ma{e.short_window}/ma{e.long_window}")

    should_notify = sig.decision in cfg.notify_on or (extra and cfg.notify_cross_today)
    if not should_notify:
        return None, sig.decision

    price = float(entry["close"].iloc[-1])
    embed = format_signal_embed(
        symbol=item.symbol,
        name=item.name,
        decision=sig.decision,
        total=sig.total,
        bull=sig.bull_total,
        bear=sig.bear_total,
        price=price,
        components=sig.components,
        extra_lines=extra,
    )
    return embed, sig.decision


def run(cfg: SchedulerConfig) -> None:
    notifier = DiscordNotifier.from_env()
    items = load_watchlist(cfg.watchlist_path)
    LOGGER.info("watching %d symbols, interval=%dm", len(items), cfg.interval_minutes)

    stop = {"flag": False}

    def _on_sig(signum, frame):
        LOGGER.info("signal %d received, stopping", signum)
        stop["flag"] = True

    _signal.signal(_signal.SIGINT, _on_sig)
    _signal.signal(_signal.SIGTERM, _on_sig)

    last_decision: dict[str, str] = {}

    while not stop["flag"]:
        wait_s = _seconds_until_next_tick(cfg.interval_minutes, cfg.align_to_top_of_hour)
        LOGGER.info("sleeping %.0fs until next tick", wait_s)
        end = time.time() + wait_s
        while not stop["flag"] and time.time() < end:
            time.sleep(min(5.0, end - time.time()))
        if stop["flag"]:
            break

        for item in items:
            try:
                embed, decision = _check_one(item, cfg)
            except Exception:
                LOGGER.exception("error scoring %s", item.symbol)
                continue
            if embed is None:
                LOGGER.info("%s: %s (no notify)", item.symbol, decision)
                continue
            if last_decision.get(item.symbol) == decision and decision not in ("LONG", "SHORT"):
                continue
            try:
                notifier.send(content="", embeds=[embed])
                LOGGER.info("%s: notified %s", item.symbol, decision)
                last_decision[item.symbol] = decision
            except Exception:
                LOGGER.exception("discord send failed for %s", item.symbol)

    LOGGER.info("scheduler stopped")
