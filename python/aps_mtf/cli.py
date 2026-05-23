"""Command-line entry: load CSV → backtest or grid-search → emit CSV / JSON.

Usage:
    python -m aps_mtf.cli backtest --m5 m5.csv --grid examples/grid.json
    python -m aps_mtf.cli grid     --m5 m5.csv --grid examples/grid.json --out results.csv
    python -m aps_mtf.cli wf       --m5 m5.csv --grid examples/grid.json --train-days 90 --test-days 30
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from .backtest import BacktestParams, run_backtest
from .data import load_csv, resample
from .optimize import grid_search, walk_forward
from .scoring import weights_from_dict


def _load_three_tfs(m5_path: str, h1_path: str | None, d1_path: str | None,
                    use_real_volume: bool):
    m5 = load_csv(m5_path, use_real_volume=use_real_volume)
    h1 = load_csv(h1_path, use_real_volume=use_real_volume) if h1_path else resample(m5, "1h")
    d1 = load_csv(d1_path, use_real_volume=use_real_volume) if d1_path else resample(m5, "1D")
    return m5, h1, d1


def _params_from_json(blob: dict) -> BacktestParams:
    p = BacktestParams()
    fields = {k for k in vars(p).keys() if k not in {"weights", "tf_cfg"}}
    for k, v in blob.get("params", {}).items():
        if k in fields:
            setattr(p, k, v)
    if "weights" in blob:
        p.weights = weights_from_dict(blob["weights"])
    return p


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser("aps_mtf")
    sub = parser.add_subparsers(dest="cmd", required=True)

    def add_common(sp):
        sp.add_argument("--m5", required=True, help="M5 CSV path")
        sp.add_argument("--h1", default=None, help="H1 CSV (else resample from M5)")
        sp.add_argument("--d1", default=None, help="D1 CSV (else resample from M5)")
        sp.add_argument("--grid", default=None, help="JSON file with params/weights/grid")
        sp.add_argument("--real-volume", action="store_true")
        sp.add_argument("--out", default=None, help="Output CSV/JSON path")

    bt = sub.add_parser("backtest")
    add_common(bt)

    gs = sub.add_parser("grid")
    add_common(gs)
    gs.add_argument("--metric", default="sharpe")

    wf = sub.add_parser("wf")
    add_common(wf)
    wf.add_argument("--train-days", type=int, default=90)
    wf.add_argument("--test-days",  type=int, default=30)
    wf.add_argument("--step-days",  type=int, default=None)
    wf.add_argument("--metric", default="sharpe")

    args = parser.parse_args(argv)
    blob = json.loads(Path(args.grid).read_text()) if args.grid else {}
    base = _params_from_json(blob)
    grid = blob.get("grid", {})

    m5, h1, d1 = _load_three_tfs(args.m5, args.h1, args.d1, args.real_volume)

    if args.cmd == "backtest":
        result = run_backtest(m5, h1, d1, base)
        print(json.dumps(result.metrics, indent=2, default=float))
        if args.out:
            Path(args.out).write_text(result.trades.to_csv(index=False))
        return 0

    if args.cmd == "grid":
        df = grid_search(m5, h1, d1, base, grid, metric=args.metric)
        if args.out:
            df.to_csv(args.out, index=False)
        print(df.head(20).to_string(index=False))
        return 0

    if args.cmd == "wf":
        out = walk_forward(m5, h1, d1, base, grid,
                           train_days=args.train_days,
                           test_days=args.test_days,
                           step_days=args.step_days,
                           metric=args.metric)
        if args.out:
            out["windows"].to_csv(args.out, index=False)
        print(out["windows"].to_string(index=False))
        print("\n=== aggregate OOS ===")
        if not out["oos_trades"].empty:
            total = out["oos_trades"]["pnl"].sum()
            wins  = (out["oos_trades"]["pnl"] > 0).mean()
            print(f"trades={len(out['oos_trades'])}  total_pnl={total:.2f}  win_rate={wins:.3f}")
        return 0

    parser.error(f"Unknown command: {args.cmd}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
