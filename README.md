# investment-dashboard

投資 AI / 自動売買リポジトリ。

## APS + MTF (Stoch RSI / RCI / MACD) スコアリング型 EA

MetaTrader 5 (MQL5) で動作する EA を `mt5/` 配下に実装しています。

- 上位 D1 / 中位 H1 / 下位 M5 の 3 階層 MTF
- APS (Absorption Pressure System) の圧力値 + ダイバージェンスを主トリガー
- Stoch RSI / RCI / MACD の各 TF スコアを重み付け合算
- ATR ベースのロット計算と SL/TP、トレーリング、日次損失・連敗サーキットブレーカー
- 日本株 (CFD 含む) 向けの JST セッションフィルター

詳細仕様は [docs/SPEC.md](docs/SPEC.md) を参照。

### ファイル構成

```
mt5/
├── Experts/APS_MTF_EA.mq5           # メイン EA
├── Include/APS_MTF/
│   ├── APS.mqh                       # 圧力 + ダイバージェンス
│   ├── RCI.mqh
│   ├── StochRSI.mqh
│   ├── MTFSignals.mqh                # TF 別スコアリング
│   ├── Scoring.mqh                   # 重み付け合算
│   ├── RiskManager.mqh
│   └── SessionFilter.mqh
└── Indicators/APS_Pressure.mq5      # チャート用 APS 可視化
```

### インストール

1. MT5 を起動し `File > Open Data Folder` → `MQL5/` を開く。
2. このリポジトリの `mt5/Experts/APS_MTF_EA.mq5` を `MQL5/Experts/` にコピー。
3. `mt5/Include/APS_MTF/` を `MQL5/Include/` にディレクトリごとコピー (結果: `MQL5/Include/APS_MTF/*.mqh`)。
4. `mt5/Indicators/APS_Pressure.mq5` を `MQL5/Indicators/` にコピー (任意・可視化用)。
5. MetaEditor で `APS_MTF_EA.mq5` をコンパイル (F7)。
6. 対象銘柄チャート (M5 推奨) にドラッグして、自動売買を許可。

### 主要パラメータ

| グループ   | パラメータ               | 既定値    |
|------------|--------------------------|-----------|
| MTF        | TfLower / TfMiddle / TfUpper | M5 / H1 / D1 |
| APS        | Lookback / DivLookback   | 20 / 30   |
| Scoring    | Long / Short Threshold   | +10 / -10 |
| Risk       | RiskPct / SL_ATR / TP_RR | 1% / 1.5 / 2.0 |
| Session    | UseSessionFilter / JstOffsetMinutes | true / 0 |

すべての入力は MetaTrader の EA プロパティから変更可能。詳細は SPEC.md。

### バックテスト

- ストラテジーテスター → Expert: `APS_MTF_EA`
- 期間: 直近 6 ヶ月以上推奨
- モデル: 「全ティック (リアルティックに基づく)」
- 銘柄: ブローカー側で MT5 提供のある日本株 CFD / 株価指数。日本株現物が無いブローカーでは日経 225 mini / 個別株 CFD で代用可能。

### 注意

- 日本株を MT5 で扱えるブローカーは限定的。提供シンボル一覧を必ず事前確認。
- スプレッド・手数料は MT5 のシンボル仕様に従う。
- 配当落ち日・権利付き最終日のギャップは別途対策が必要 (`AllowOvernight=false` 推奨)。
- バックテストでパラメータ最適化する際は、過剰最適化に注意。ウォークフォワード分析を推奨。
