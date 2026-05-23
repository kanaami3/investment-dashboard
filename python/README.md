# aps_mtf — Python tuning harness for the APS+MTF EA

オフラインで MQL5 EA と**同じスコアリングロジック**を回し、グリッドサーチ／ウォークフォワードでパラメータ・重みをチューニングするためのツールです。

## セットアップ

```bash
cd python
pip install -r requirements.txt
```

依存は `pandas`, `numpy` のみ。

## 入力データ

MT5 のチャートから `File > Save As (CSV)` でエクスポートした OHLCV CSV を想定。次のいずれかの列構成に対応:

1. `DATE,TIME,OPEN,HIGH,LOW,CLOSE,TICKVOL,VOL,SPREAD`
2. `DATETIME,OPEN,HIGH,LOW,CLOSE,VOLUME`

M5 のみ与えれば H1/D1 は自動的にリサンプリングします (`--h1`, `--d1` で個別指定も可)。

## 使い方

### バックテスト (単発)

```bash
python -m aps_mtf.cli backtest --m5 ./data/sym_m5.csv --grid examples/grid.json
```

### グリッドサーチ

```bash
python -m aps_mtf.cli grid --m5 ./data/sym_m5.csv --grid examples/grid.json \
    --metric sharpe --out results.csv
```

### ウォークフォワード

```bash
python -m aps_mtf.cli wf --m5 ./data/sym_m5.csv --grid examples/grid.json \
    --train-days 90 --test-days 30 --metric sharpe --out wf.csv
```

## grid.json の構造

```json
{
  "params":  { "sl_atr_mult": 1.5, "tp_rr": 2.0, ... },
  "weights": { "w_aps_pressure": 2.5, "w_d1_macd": 1.5, ... },
  "grid":    { "long_threshold": [7,8,9,10,11,12,13],
               "sl_atr_mult":    [1.0, 1.5, 2.0] }
}
```

- `params`: `BacktestParams` の既定値を上書き (リスク、SL/TP、初期資金、手数料 bps 等)
- `weights`: `ScoreWeights` の上書き
- `grid`: 探索する `BacktestParams` フィールド → 値リスト の dict

## ライブラリとして使う

```python
import pandas as pd
from aps_mtf import BacktestParams, run_backtest, grid_search, walk_forward
from aps_mtf.data import load_csv, resample

m5 = load_csv("data/sym_m5.csv")
h1 = resample(m5, "1h")
d1 = resample(m5, "1D")

# 単発
r = run_backtest(m5, h1, d1, BacktestParams(long_threshold=11))
print(r.metrics)
r.equity_curve.plot()

# グリッド
df = grid_search(m5, h1, d1, BacktestParams(),
                 grid={"long_threshold":[8,10,12],
                       "sl_atr_mult":[1.0,1.5,2.0]},
                 metric="sharpe")

# ウォークフォワード
wf = walk_forward(m5, h1, d1, BacktestParams(),
                  grid={"long_threshold":[8,10,12]},
                  train_days=120, test_days=30)
wf["oos_equity"].plot()
```

## EA の CSV ログとの突き合わせ

EA 側で `InpCsvLog=true, InpCsvLogPath=APS_MTF_signals.csv` にすると、各バーの素点・合計スコア・アクションを CSV 出力します。
Python 側で同じ OHLCV を `aggregate()` に通せば `total` 列が同じ値になるはずで、両者を比較してロジック差異の有無を検証できます。

## 指標ロジックの対応

| MQL5                                  | Python                                   |
|---------------------------------------|------------------------------------------|
| `mt5/Include/APS_MTF/APS.mqh`         | `aps_mtf/indicators.py::aps_pressure / aps_divergence` |
| `mt5/Include/APS_MTF/RCI.mqh`         | `aps_mtf/indicators.py::rci`             |
| `mt5/Include/APS_MTF/StochRSI.mqh`    | `aps_mtf/indicators.py::stoch_rsi` (Wilder RSI) |
| `mt5/Include/APS_MTF/MTFSignals.mqh`  | `aps_mtf/signals.py::tf_scores`          |
| `mt5/Include/APS_MTF/Scoring.mqh`     | `aps_mtf/scoring.py::aggregate`          |
| `mt5/Include/APS_MTF/RiskManager.mqh` | `aps_mtf/backtest.py::run_backtest`      |

## 既知の差分

- Python の StochRSI は Wilder RSI を pandas EWM で計算。MT5 の `iRSI` も Wilder ベースだが、シリーズ先頭のシード処理が異なるため、データ先頭 1〜2 期間の値はわずかに乖離。十分な履歴を与えれば収束。
- Divergence の極値検出はバー内 tick の精度では一致しない。「終値ベースで同等」の判定。
- 手数料・スリッページは固定 bps で簡略化。MT5 側は `SYMBOL_TRADE_TICK_VALUE` 経由で算出するため、現物 vs CFD で誤差が出る。
