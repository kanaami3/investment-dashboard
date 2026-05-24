# 手順書 (Runbook) — MT5 APS_MTF_EA デモ運用

| 項目         | 値                                                       |
|--------------|----------------------------------------------------------|
| ドキュメント | MT5 EA デモ運用 Runbook                                  |
| 対象         | 利用者本人                                               |
| 前提         | MT5 が動くホスト (Windows / Wine / VPS)、ブローカー口座  |
| 所要時間     | Phase 0〜3 合計 ~3 時間 + デモ稼働 5 営業日以上          |
| 関連         | [03_runbook.md](03_runbook.md) は Python/OANDA 側。本書は MT5 側 |

このドキュメントは `mt5/Experts/APS_MTF_EA.mq5`(`mt5/Include/APS_MTF/*` を内包)を
**デモ口座で初めて動かして 1〜2 週間回す**ところまでをカバーする。ライブ昇格は別途。

---

## Phase 0: 事前準備

### 0-1. 必要なもの
- **MT5 ターミナル** がインストール済み(MetaQuotes 公式 or ブローカー配布版)
- **MT5 で日本株を扱えるブローカーのデモ口座**
  - 代表例: OANDA / IG / Saxo の CFD(JP225 や個別株 CFD)
  - 純日本株(現物)は MT5 非対応のことが多い — CFD 経由が現実解
- **VPS or 常時起動 PC**(自宅 PC 24h 起動でも可、ただし日本株時間中 9:00-15:00 だけ動けばよい)

### 0-2. ブローカー口座
1. ブローカーの Web で **デモ口座** を開設(本人確認なし、即時)
2. 表示された MT5 サーバー名 / ログイン番号 / パスワードをメモ
3. MT5 を起動 → 「ファイル → 取引口座にログイン」→ サーバー選択 → ログイン
4. 「気配値表示」ペインに目的銘柄(例: `JP225`)が出ているか確認
   - 出ない場合は右クリック → 「すべて表示」 or 「銘柄」検索

### 0-3. 取引可能性の最低確認
1. チャートを開く(例: `JP225` M5)
2. 「ワンクリック取引」をONして 0.1lot Buy → 即決済
3. ジャーナルに `deal #... done` が出れば OK
4. 履歴に約定が残っていることを確認(出ない場合は Server が休場 or 銘柄違い)

---

## Phase 1: EA インストール

### 1-1. ファイル配置
MT5 のデータフォルダを開く(MT5: ファイル → データフォルダを開く)。
リポジトリの内容をコピー:

```
リポジトリ                              MT5 データフォルダ
mt5/Experts/APS_MTF_EA.mq5         →   MQL5/Experts/APS_MTF_EA.mq5
mt5/Include/APS_MTF/*.mqh          →   MQL5/Include/APS_MTF/*.mqh
mt5/Indicators/APS_Pressure.mq5    →   MQL5/Indicators/APS_Pressure.mq5
mt5/Presets/APS_MTF_EA.set         →   MQL5/Profiles/Tester/APS_MTF_EA.set
```

> Windows の場合、リポジトリのファイルを直接コピーペーストで OK。
> macOS + Wine の場合は `~/.wine/drive_c/users/<you>/AppData/Roaming/MetaQuotes/Terminal/<HASH>/MQL5/` 配下。

### 1-2. コンパイル
1. MT5 で **MetaEditor** を開く(F4)
2. `Experts/APS_MTF_EA.mq5` を開く → **F7**
3. 出力欄が `0 errors, 0 warnings` であること
4. 同様に `Indicators/APS_Pressure.mq5` も F7

### 1-3. EA をチャートに付ける(まだ自動取引は OFF)
1. MT5 の「ナビゲーター」→ Experts → `APS_MTF_EA` をチャートにドラッグ
2. 「全般」タブ:
   - 「アルゴリズム取引を許可する」を **チェック**
   - 「DLL の使用を許可する」は不要
3. 「パラメータ」タブで `InpVerboseLog=true`, `InpCsvLog=true` を一時 ON
4. OK
5. ターミナル下部の「エキスパート」タブに `[APS_MTF] Initialized on JP225. TF lower=PERIOD_M5 ...` が出ること
6. **ツールバーの「アルゴリズム取引」ボタンは OFF のままに**(まだ発注させない)

---

## Phase 2: Strategy Tester でスモーク

実発注前に過去データで挙動を確認する。

### 2-1. テスター起動
1. MT5 → 表示 → ストラテジーテスター(Ctrl+R)
2. EA: `APS_MTF_EA`
3. 銘柄: 本番と同じ(例 `JP225`)
4. 期間: `M5`(InpTfLower と一致させる)
5. モデル: **「全ティック」**(初回)/ 後で「OHLC M1」に下げて高速化
6. 日付: 直近 3〜6 ヶ月
7. デポジット: 100,000 JPY、レバレッジ: 口座と同じ
8. 「単一テスト」で実行

### 2-2. 期待される結果
- 約定回数: 数十〜数百(0 なら閾値が厳しすぎ or データ不足)
- グラフ: 直線でない(=実際にトレードしている)
- 「結果」タブで `エラー: 0` または `不十分な金額: 0`

問題があるとき:
- **約定 0** → `InpLongThreshold` を下げる(例 10 → 6)/ 期間を伸ばす
- **ロット 0 エラー** → `InpRiskPct` を上げる(例 1 → 2)/ デポジットを増やす
- **「無効な SL」** → `InpSlAtrMult` を上げる(例 1.5 → 2.0)or ブローカーの最小ストップを確認

### 2-3. Genetic 最適化(任意 / 推奨)
1. テスター → 「最適化: 高速(遺伝的)」
2. 「入力パラメータ」タブで `APS_MTF_EA.set` を読み込み
3. **Phase 1 のみ**(thresholds + risk)を Y、他は N で実行 — Preset コメント参照
4. 上位 10 件をスプレッドシートにエクスポート → walk-forward 検証
5. 勝ち組のパラメータを `.set` に書き戻して保存

---

## Phase 3: デモ口座でドライ稼働

### 3-1. EA をデモ口座で起動
1. 該当チャートで EA がアタッチされた状態を確認(右上にスマイリー顔)
2. パラメータを確認:
   - `InpCsvLog=true`
   - `InpCsvLogPath=APS_MTF_signals.csv`(MT5 データフォルダ/MQL5/Files/ に出る)
   - `InpVerboseLog=true`(初週のみ)
3. ツールバーの **「アルゴリズム取引」を ON**
4. ターミナル → 取引タブで建玉が出るのを待つ(M5 確定 +数秒)

### 3-2. 初日(D+0)チェックリスト
取引時間中、最初の 1 時間で以下を確認:

- [ ] エキスパートタブに `Initialized on ...` が出ている
- [ ] エキスパートタブに 5 分ごとに `[APS_MTF] APS press=... ` が出ている(InpVerboseLog=true 時)
- [ ] `MQL5/Files/APS_MTF_signals.csv` が生成され、5 分ごとに 1 行追加されている
- [ ] CSV の `action` 列に `HOLD` / `BLOCKED` / `OPEN_*` のどれかが出ている
- [ ] `BLOCKED` の場合 `block_reason` 列に `session` / `risk` / `session+risk` が入っている
- [ ] `OPEN_LONG` または `OPEN_SHORT` が出たら、取引タブにポジション、CSV の次行で `IN_POSITION`
- [ ] SL/TP がポジションに付いている(取引タブで `SL`, `TP` 列が 0 でない)

### 3-3. 取引時間終了後(D+0 16:00)
- [ ] `InpAllowOvernight=false` の場合、15:00 直前に `EOD-flatten` 由来でポジションがクローズされている
- [ ] CSV を 1 件バックアップ: `MQL5/Files/APS_MTF_signals.csv` を `backups/YYYY-MM-DD.csv` にコピー
- [ ] その日の `OPEN_*` 行数 ≦ 想定エントリー回数 / 日

---

## Phase 4: 監視・運用(D+1 以降)

### 4-1. 毎営業日(取引時間中 1 回)
- [ ] MT5 が立ち上がっており EA がスマイリー
- [ ] 取引タブに想定外のポジション(他 magic、手動建玉)が混在していないか
- [ ] エキスパートタブにエラー(`failed`, `error`, `invalid`)が出ていないか

### 4-2. 毎営業日終わり
- [ ] CSV 末尾 20 行を確認(`OPEN_*` が出ているか、`block_reason` の偏り)
- [ ] OANDA / ブローカー Web UI で口座残高を確認
- [ ] 日次損益が `InpMaxDailyLossPct` を超えていないか

### 4-3. 毎週末(土)
- [ ] CSV をバックアップ
- [ ] スプレッドシートに取り込み、以下を集計:
  - エントリー回数 / 勝率 / 平均利益 / 平均損失 / 最大 DD
  - `block_reason` の出現比率(`session` ばかりなら時間帯ミス、`risk` ばかりなら循環ブレーカー多発)
  - `spread_points` の中央値(極端に大きい時間帯があれば取引除外検討)
  - `atr` と勝率の相関(高ボラ帯のみ機能/逆 など)
- [ ] パラメータ調整の必要があれば月次まで温める(週次でいじらない)

### 4-4. 月次レビュー
- [ ] 過去 1 ヶ月の CSV + 取引履歴を見て、Strategy Tester の最適化を再実行
- [ ] 勝ったパラメータと現行を walk-forward 比較
- [ ] 変更する場合は `.set` を新ファイル名で保存(`APS_MTF_EA_2026-06.set` 等)し、CSV ファイル名も変更して旧データと分離

---

## Phase 5: 緊急停止

### 想定外の建玉 / 損失拡大
1. MT5 上部の **「アルゴリズム取引」ボタンを OFF**(新規発注停止)
2. 取引タブで該当ポジションを右クリック → 「ポジションを閉じる」(手動全クローズ)
3. EA をチャートから外す(右クリック → エキスパートを削除)
4. CSV の直近行を確認して原因特定
5. 修正後、Phase 2 のテスター→Phase 3 のドライ確認をやり直してから再投入

### MT5 が落ちた / VPS が再起動した
- MT5 を起動して口座にログイン
- EA がアタッチされていれば自動再開(`InpMagicNumber` で旧建玉を引き継ぐ)
- もしポジションが残っていて EA が外れていた場合は、手動でクローズしてから EA を再アタッチ(EA は他人の建玉に対するトレールはしない)

### ブローカー API がエラー連発
- エキスパートタブの `Trade failed` を確認
- ブローカーの障害情報ページ確認
- 続くようなら EA OFF → 様子見

---

## Phase 6: ライブ昇格(将来 — 別案件)

スコープ外。最低限の前提:
- デモで連続 4 週間問題なく稼働
- 月次の勝率 / DD が事前定義した受け入れ基準内
- `InpRiskPct` を 0.1〜0.3% から開始(デモ運用値の 1/5)
- magic 番号を変更(デモと混ぜない)
- ライブ用 `.set` を別名保存

---

## 付録 A: CSV 列リファレンス

| 列 | 意味 |
|----|------|
| `time` | M5 確定バーの open 時刻(ブローカー時間) |
| `symbol` / `tf` | 銘柄 / 下位 TF |
| `aps_pressure_raw` / `_score` | APS 圧力指標(生値と -1..+1 正規化) |
| `aps_div_raw` / `_score` | ダイバージェンス検出(-1/0/+1)とスコア |
| `d1_* / h1_* / m5_*` | 各 TF の Stoch RSI / RCI / MACD スコア(-1..+1) |
| `bull_total` / `bear_total` | 正/負寄与の絶対値合計 |
| `total` | 重み付き合計(エントリー判定の対象) |
| `long_thr` / `short_thr` | その時点で有効だった閾値 |
| `action` | `HOLD` / `OPEN_LONG` / `OPEN_SHORT` / `EXIT_LONG` / `EXIT_SHORT` / `IN_POSITION` / `BLOCKED` |
| `price` | 判定時の Bid(SHORT 時は Ask) |
| `atr` | 下位 TF の ATR(SL 距離の参考) |
| `spread_points` | 判定時のスプレッド(ポイント単位) |
| `equity` / `balance` | 口座残高 |
| `block_reason` | `BLOCKED` 時のみ: `session` / `risk` / `session+risk` |
| `pos_type` / `pos_volume` / `pos_pl` | 建玉中のみ: 方向 / lot / 未実現損益 |

---

## 付録 B: トラブルシューティング早見表

| 症状 | 一次切り分け |
|------|--------------|
| EA がアタッチできない | コンパイルエラーが残っている → MetaEditor で F7 |
| `Initialized` ログが出ない | EA がアタッチされていない or アルゴリズム取引 OFF |
| ずっと `HOLD` ばかり | `InpLongThreshold` が高すぎ、または銘柄ボラが低い時間帯 |
| `BLOCKED` ばかり (`block_reason=session`) | `InpJstOffsetMinutes` がブローカーサーバー時間とずれている |
| `BLOCKED` ばかり (`block_reason=risk`) | 連敗ロックアウト中 or 日次損失が閾値超え |
| `IN_POSITION` のままトレールしない | `InpTrailStartRR` 未到達 / トレール条件未充足(ATR と SL 距離を確認) |
| ロット 0 / `invalid volume` | `InpRiskPct` が小さすぎ、または銘柄の最小ロット未満 |
