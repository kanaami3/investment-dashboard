"""Grid search and walk-forward helpers."""

from __future__ import annotations

import itertools
from dataclasses import replace
from typing import Iterable

import pandas as pd

from .backtest import BacktestParams, BacktestResult, run_backtest
from .scoring import aggregate


def _iter_grid(grid: dict[str, Iterable]) -> Iterable[dict]:
    keys = list(grid.keys())
    for combo in itertools.product(*[list(grid[k]) for k in keys]):
        yield dict(zip(keys, combo))


def grid_search(
    m5: pd.DataFrame, h1: pd.DataFrame, d1: pd.DataFrame,
    base: BacktestParams,
    grid: dict[str, Iterable],
    metric: str = "sharpe",
) -> pd.DataFrame:
    """Run every combo in ``grid`` against the provided data window.

    ``grid`` keys must be field names of ``BacktestParams`` (e.g. ``long_threshold``).
    Returns a DataFrame sorted by ``metric`` descending.
    """
    rows = []
    for overrides in _iter_grid(grid):
        params = replace(base, **overrides)
        result = run_backtest(m5, h1, d1, params)
        rows.append({**overrides, **result.metrics})
    df = pd.DataFrame(rows)
    if metric in df.columns:
        df = df.sort_values(metric, ascending=False, kind="stable").reset_index(drop=True)
    return df


def walk_forward(
    m5: pd.DataFrame, h1: pd.DataFrame, d1: pd.DataFrame,
    base: BacktestParams,
    grid: dict[str, Iterable],
    train_days: int = 90,
    test_days: int = 30,
    step_days: int | None = None,
    metric: str = "sharpe",
) -> dict:
    """Rolling-window walk-forward:
       train -> grid_search -> best -> apply to next test window.

    Returns ``{"windows": DataFrame, "oos_equity": Series, "oos_trades": DataFrame}``.
    """
    step = step_days or test_days
    start = m5.index.min()
    end = m5.index.max()
    cur = start

    window_rows = []
    oos_pieces = []
    oos_trade_pieces = []

    while True:
        train_end = cur + pd.Timedelta(days=train_days)
        test_end  = train_end + pd.Timedelta(days=test_days)
        if test_end > end:
            break
        m5_tr = m5.loc[cur:train_end]
        h1_tr = h1.loc[cur:train_end]
        d1_tr = d1.loc[cur:train_end]
        if len(m5_tr) < 100:
            cur += pd.Timedelta(days=step)
            continue

        scores = grid_search(m5_tr, h1_tr, d1_tr, base, grid, metric)
        if scores.empty:
            cur += pd.Timedelta(days=step)
            continue
        best = scores.iloc[0]
        best_params = {k: best[k] for k in grid.keys() if k in scores.columns}
        params = replace(base, **best_params)

        m5_te = m5.loc[train_end:test_end]
        h1_te = h1.loc[cur:test_end]
        d1_te = d1.loc[cur:test_end]
        if m5_te.empty:
            cur += pd.Timedelta(days=step)
            continue
        oos = run_backtest(m5_te, h1_te, d1_te, params)
        window_rows.append({
            "train_start": cur, "train_end": train_end,
            "test_start": train_end, "test_end": test_end,
            **best_params,
            **{f"is_{k}": v for k, v in best.items() if k not in best_params},
            **{f"oos_{k}": v for k, v in oos.metrics.items()},
        })
        oos_pieces.append(oos.equity_curve)
        if not oos.trades.empty:
            oos_trade_pieces.append(oos.trades)
        cur += pd.Timedelta(days=step)

    oos_equity = pd.concat(oos_pieces) if oos_pieces else pd.Series(dtype=float)
    oos_trades = pd.concat(oos_trade_pieces, ignore_index=True) if oos_trade_pieces else pd.DataFrame()
    return {
        "windows": pd.DataFrame(window_rows),
        "oos_equity": oos_equity,
        "oos_trades": oos_trades,
    }
