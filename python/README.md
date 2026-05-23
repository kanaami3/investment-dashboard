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

---

# OANDA Japan v20 ライブ運用 (`aps_mtf.oanda`)

オフラインで決めたパラメータを、**OANDA Japan のデモ口座 (fxTrade Practice)** から実際に発注する Python ランナーです。対象は JP225_JPY (日経225 CFD) を想定していますが、`instrument` を変えれば FX ペアにも使えます。

## 0. 事前準備 (OANDA Japan 側)

1. https://www.oanda.jp/ で口座開設 (デモは即時)
2. ログイン後 **「マイページ → APIアクセス」** からパーソナルアクセストークンを発行
3. アカウント ID をメモ (`xxx-xxx-xxxxxxx-xxx` 形式)

> **注意**: ライブ口座の API は申し込み制 / 利用規約への同意が必要なことがあります。まずデモ口座 (fxpractice) で動作確認してください。

## 1. 環境変数を設定

`python/examples/.env.example` を `python/.env` にコピーして編集:

```dotenv
OANDA_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
OANDA_ACCOUNT_ID=101-001-1234567-001
OANDA_ENV=practice
```

`.env` は `.gitignore` 済み。`python-dotenv` が CLI 起動時に自動で読み込みます。

## 2. 疎通確認

```bash
cd python
python -m aps_mtf.oanda.cli --config examples/oanda_jp225.json ping
```

→ 口座 ID、通貨、NAV、残高が出れば認証成功。

```bash
python -m aps_mtf.oanda.cli --config examples/oanda_jp225.json candles --count 5
```

→ JP225_JPY の M5 直近 5 本の OHLC が出れば、データ取得 OK。

## 3. 現在のスコアを確認 (ドライ)

```bash
python -m aps_mtf.oanda.cli --config examples/oanda_jp225.json score-now
```

→ 各 TF の素点 + 合計スコア + LONG / SHORT / HOLD 判定が JSON で出ます。発注はしません。

## 4. ライブループ (デモ口座 / dry-run)

```bash
python -m aps_mtf.oanda.cli --config examples/oanda_jp225.json run
```

- M5 バー確定 (UTC) + `poll_buffer_sec` 後にポーリング
- スコア計算 → エントリー/エグジット判定
- `dry_run: true` (デフォルト) なので注文は **POST されない**
- 全イベントは `oanda_runner.csv` に追記される (EA の CSV ログと同形式)

ターミナルログ例:
```
2026-05-23 09:25:08 INFO aps_mtf.oanda.runner: connected env=practice ... NAV=3000000 JPY dry_run=True
2026-05-23 09:30:08 INFO aps_mtf.oanda.runner: [DRY] LONG 20 JP225_JPY sl=38123.500 tp=38450.500 score=11.50 capped=True
```

## 5. デモ口座で実際に発注

```bash
python -m aps_mtf.oanda.cli --config examples/oanda_jp225.json run --live
```

`--live` フラグは「dry-run を OFF」の意味。`env=practice` のままなので **デモ口座での発注** です。

## 6. ライブ口座へ昇格 (慎重に)

1. `.env` で `OANDA_ENV=live`、`OANDA_ALLOW_LIVE=1` をセット
2. `examples/oanda_jp225.json` の `risk_pct` / `max_units_per_trade` を一桁ずつ下げて開始
3. 数日デモと並走、シグナル一致を `oanda_runner.csv` で確認してから本番投入

ランナーは `OANDA_ENV=live` かつ `OANDA_ALLOW_LIVE=1` でない限り live を拒否します。

## セーフティ機能

| 機能                  | 設定                                     |
|-----------------------|------------------------------------------|
| ドライラン            | `dry_run: true` または `--live` なし     |
| ポジションサイズ上限  | `max_units_per_trade`                    |
| 日次損失サーキット    | `max_daily_loss_pct`                     |
| 連敗ロック            | `max_consec_losses`                      |
| API リトライ          | 429 / 5xx は指数バックオフで最大 4 回    |
| ライブ昇格ガード      | `OANDA_ALLOW_LIVE=1` 環境変数            |
| Graceful shutdown     | SIGINT / SIGTERM でループを終了          |

## 既知の制約 / 注意点

- **JP225_JPY のサイズ計算は「1 unit = 1 JPY/pt」前提**。他の指数 CFD や FX (特に非 JPY 建て) は `sizing.py` を拡張して通貨換算を入れる必要あり。
- OANDA の出来高は **tick volume** のみ。APS pressure はこれで計算される (MT5 EA の `InpApsUseRealVolume=false` 相当)。
- マーケットクローズ中も M5 ループは回るが、candles レスポンスが空になるだけで HOLD ログが出る。JP225 は ~23 時間 / 平日。
- スプレッド・スリッページは OANDA 側で吸収されるので、`fee_bps` 等は **バックテスト専用**。
- 1 つの runner プロセス = 1 instrument。複数銘柄を回したい場合は config を分けてプロセス並走。

## ファイル構成

```
aps_mtf/oanda/
├── client.py    # v20 REST 最小ラッパ (requests)
├── config.py    # OandaConfig + JSON/env loader
├── sizing.py    # ATR + risk_pct → units
├── runner.py    # ライブループ本体 (バー確定 → スコア → 発注 / 管理)
└── cli.py       # ping / candles / score-now / run

examples/
├── oanda_jp225.json   # サンプル設定
└── .env.example       # トークン/アカウント ID 用テンプレ
```

