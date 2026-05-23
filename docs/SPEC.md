# APS + MTF (Stoch RSI / RCI / MACD) スコアリング型 EA 仕様書

対象環境: MetaTrader 5 (MQL5)
対象資産: 日本株 (CFD 含む。symbol を入力で切替可能)
時間軸 (MTF): エントリー M5 / 中位 H1 / 上位 D1

---

## 1. 目的

「APS（買売圧力＋ダイバージェンス）」を主トリガーに、上位足のトレンドと下位足のオシレーター反転をスコア合計で評価し、閾値超過時に自動エントリーする。

## 2. 指標構成

### 2.1 APS (Absorption Pressure System)

- Pressure 値: Chaikin Money Flow 系の方向付き出来高比率
  - 各バーの Money Flow Multiplier: `MFM = ((C - L) - (H - C)) / (H - L)`
  - Money Flow Volume: `MFV = MFM * Volume`
  - `Pressure = ΣMFV(+) - ΣMFV(-) / (ΣMFV(+) + ΣMFV(-))` 範囲: -1 〜 +1
  - 既定 lookback: 20 本
- ダイバージェンス検出: lookback (既定 30 本) を前半・後半に分割し、各半区間の最安値・最高値を抽出して比較
  - 強気: 価格 LL かつ APS HL → +1
  - 弱気: 価格 HH かつ APS LH → -1
- 出来高ソース: `iTickVolume` (既定) / `iRealVolume` を入力で切替

### 2.2 Stochastic RSI (各TF)

- RSI(14) → Stoch(14, smoothK=3, smoothD=3)
- K/D の値、クロス、過熱ゾーン (>80/<20) でスコア化

### 2.3 RCI (各TF)

- 期間: 短期 9 / 長期 26 (入力で変更可)
- 値: -100 〜 +100
- 過熱ゾーン (±80) からの反転、長期 RCI の符号でトレンド方向

### 2.4 MACD (各TF)

- 既定 (12, 26, 9)
- MACD と Signal、ヒストグラムの傾き、ゼロライン関係でスコア化

## 3. スコアリング規則

各指標の素点（-2 〜 +2）に時間軸別の重み `w_tf` を掛けて加算する。

| TF  | 役割           | StochRSI 重み | RCI 重み | MACD 重み |
|-----|----------------|---------------|----------|-----------|
| D1  | 上位トレンド   | 1.0           | 1.0      | 1.5       |
| H1  | 中位確認       | 1.5           | 1.5      | 2.0       |
| M5  | エントリー時計 | 2.0           | 2.0      | 1.0       |

APS 系は時間軸非依存（M5 で計算）:
- APS Pressure 素点（-2〜+2）× 重み 2.5
- APS Divergence 素点（-2/0/+2）× 重み 3.0

合計スコア理論最大値はおよそ ±26。既定閾値:
- Long エントリー: `score >= +10`
- Short エントリー: `score <= -10`
- 反転 Exit: 逆サイドの素点合計が `>= 8` で建玉決済

### 3.1 各素点ロジック

**StochRSI**
- K が D を下から上抜け かつ 共に <20: +2
- K > D かつ K 上昇: +1
- K < D かつ K 下降: -1
- K が D を上から下抜け かつ 共に >80: -2

**RCI**
- 短期 RCI が -80 を上抜け: +2
- 短期 RCI > 0 かつ 長期 RCI > 0: +1
- 短期 RCI < 0 かつ 長期 RCI < 0: -1
- 短期 RCI が +80 を下抜け: -2

**MACD**
- Hist が負から正に反転 かつ MACD < 0: +2
- MACD > Signal: +1
- MACD < Signal: -1
- Hist が正から負に反転 かつ MACD > 0: -2

## 4. リスク管理

- 1 注文あたりリスク: 口座残高の `RiskPct` % (既定 1.0%)
- SL: `ATR(14, M5) * SL_AtrMult` (既定 1.5)
- TP: `SL距離 * TP_RR` (既定 2.0)
- 同一銘柄の最大同時建玉: 1
- 最大日次損失: 口座残高の `MaxDailyLossPct` % 超で当日エントリー停止 (既定 3.0%)
- 最大連敗ストップ: `MaxConsecLosses` 連敗で次の取引日まで停止 (既定 4)
- トレーリングストップ: 利益が SL距離 * `TrailStartRR` (既定 1.0) 到達後、SLを建値以遠に追従

## 5. セッションフィルター (日本株)

JST タイムゾーン基準:
- 前場: 09:00 - 11:30
- 後場: 12:30 - 15:00
- エントリーは前場/後場開始から 5 分後 〜 引け 15 分前 のみ
- 引け 30 分前以降は新規不可 (持ち越し可否は入力で切替)

サーバ時刻と JST の差は入力 `JstOffsetMinutes` で補正。

## 6. EA 入力パラメータ (主要)

| グループ      | 名前                  | 型     | 既定      | 説明                                    |
|---------------|-----------------------|--------|-----------|-----------------------------------------|
| 一般          | `MagicNumber`         | long   | 20260523  | 注文識別                                |
| 一般          | `Comment`             | string | "APS_MTF" | 注文コメント                            |
| MTF           | `TF_Lower`            | ENUM   | M5        | エントリー時間軸                        |
| MTF           | `TF_Middle`           | ENUM   | H1        | 中位時間軸                              |
| MTF           | `TF_Upper`            | ENUM   | D1        | 上位時間軸                              |
| APS           | `Aps_Lookback`        | int    | 20        | Pressure 集計本数                       |
| APS           | `Aps_DivLookback`     | int    | 30        | Divergence 検出本数                     |
| APS           | `Aps_UseRealVolume`   | bool   | false     | 出来高ソース                            |
| StochRSI      | `Srsi_RsiPeriod`      | int    | 14        |                                         |
| StochRSI      | `Srsi_StochPeriod`    | int    | 14        |                                         |
| StochRSI      | `Srsi_SmoothK`        | int    | 3         |                                         |
| StochRSI      | `Srsi_SmoothD`        | int    | 3         |                                         |
| RCI           | `Rci_Short`           | int    | 9         |                                         |
| RCI           | `Rci_Long`            | int    | 26        |                                         |
| MACD          | `Macd_Fast`           | int    | 12        |                                         |
| MACD          | `Macd_Slow`           | int    | 26        |                                         |
| MACD          | `Macd_Signal`         | int    | 9         |                                         |
| スコア        | `LongThreshold`       | double | 10.0      | Long エントリー閾値                     |
| スコア        | `ShortThreshold`      | double | -10.0     | Short エントリー閾値                    |
| スコア        | `OppositeExitScore`   | double | 8.0       | 反転 Exit の絶対値閾値                  |
| リスク        | `RiskPct`             | double | 1.0       | 1 注文あたりリスク (%)                  |
| リスク        | `SL_AtrMult`          | double | 1.5       | SL = ATR * mult                         |
| リスク        | `TP_RR`               | double | 2.0       | TP = SL * RR                            |
| リスク        | `TrailStartRR`        | double | 1.0       | トレール開始 RR                         |
| リスク        | `MaxDailyLossPct`     | double | 3.0       |                                         |
| リスク        | `MaxConsecLosses`     | int    | 4         |                                         |
| セッション    | `UseSessionFilter`    | bool   | true      | 日本株セッションフィルター              |
| セッション    | `JstOffsetMinutes`    | int    | 0         | サーバ時刻 + offset = JST               |
| セッション    | `AllowOvernight`      | bool   | false     | 大引け跨ぎ保有                          |
| デバッグ      | `VerboseLog`          | bool   | false     | スコア内訳を Print                      |

## 7. ファイル構成

```
mt5/
├── Experts/
│   └── APS_MTF_EA.mq5            // メイン EA
├── Include/APS_MTF/
│   ├── APS.mqh                   // 圧力 + ダイバージェンス
│   ├── RCI.mqh                   // RCI 計算
│   ├── StochRSI.mqh              // Stoch RSI 計算
│   ├── MTFSignals.mqh            // MTF スコア素点
│   ├── Scoring.mqh               // 合計スコア・閾値判定
│   ├── RiskManager.mqh           // ロット計算・SL/TP・トレーリング
│   └── SessionFilter.mqh         // JP 株セッション
└── Indicators/
    └── APS_Pressure.mq5          // チャート用 APS 可視化
```

## 8. インストール

1. MT5 を起動し `File > Open Data Folder` → `MQL5/` を開く
2. `mt5/Experts/*.mq5` → `MQL5/Experts/` へコピー
3. `mt5/Include/APS_MTF/*.mqh` → `MQL5/Include/APS_MTF/` へコピー
4. `mt5/Indicators/*.mq5` → `MQL5/Indicators/` へコピー
5. MetaEditor で `APS_MTF_EA.mq5` をコンパイル
6. 対象銘柄のチャート (M5 推奨) に EA をアタッチ
7. 「自動売買を許可」「DLL の使用を許可」(本実装では DLL 未使用)

## 9. バックテスト手順

- ストラテジーテスター → Expert: `APS_MTF_EA`
- 期間: 直近 6 ヶ月以上を推奨
- モデル: 「全ティック (リアルティックに基づく)」推奨
- 銘柄: ブローカー側で MT5 提供のある日本株 CFD / 株価指数

## 10. 制限事項・注意

- 日本株を MT5 で扱えるブローカーは限定的。動作確認はブローカー提供のシンボル一覧で要確認。
- スプレッド・スリッページ・取引手数料は別途バックテスト条件に反映。
- 売買代金単位 (株式の場合 100 株単位等) はブローカー仕様に従う。コード上は `SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP)` で丸める。
- 配当落ち日・権利付き最終日のギャップは別途対策が必要。
