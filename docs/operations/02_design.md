# 設計書 — OANDA Japan ライブランナー

| 項目         | 値                                                     |
|--------------|--------------------------------------------------------|
| ドキュメント | 設計書 (Design)                                        |
| 対象モジュール| `aps_mtf.oanda`                                       |
| 関連要件     | `01_requirements.md`                                   |
| 作成日       | 2026-05-23                                             |

---

## 1. 概要

OANDA Japan v20 REST API の上に、既存のスコアリングロジック (`aps_mtf.scoring.aggregate`) を**そのまま再利用**するライブ自動売買ランナーを構築する。

設計の中核は「**スコア計算式の単一実装ルール**」: バックテスト / MT5 EA / ライブの 3 経路で**同じ関数**を呼ぶ。OANDA 連携層は **データ取得・サイズ計算・発注・状態管理** のみを担当する。

## 2. アーキテクチャ

```
                  ┌───────────────────┐
                  │  OandaConfig      │  JSON + env-var で外部化
                  └────────┬──────────┘
                           │
                           ▼
┌──────────────┐  ┌───────────────────┐  ┌──────────────────────┐
│ OandaClient  │◄─┤  LiveRunner.run() ├─►│  scoring.aggregate() │
│ (requests)   │  │  - schedule       │  │  signals.* (既存)    │
│ - candles    │  │  - tick()         │  │  indicators.* (既存) │
│ - pricing    │  │  - gates          │  └──────────────────────┘
│ - orders     │  │  - log_row()      │
│ - positions  │  └───────────────────┘
└──────┬───────┘            │
       │                    ▼
       │            ┌──────────────────┐
       │            │  sizing.size_*() │
       │            └──────────────────┘
       │
       ▼
  api-fxpractice.oanda.com (HTTPS)
```

## 3. モジュール構成

```
python/aps_mtf/oanda/
├── __init__.py          # 公開 API
├── client.py            # v20 REST 最小ラッパ
├── config.py            # OandaConfig dataclass + loader
├── sizing.py            # NAV * risk_pct / (ATR * mult) → units
├── runner.py            # ライブループ本体
└── cli.py               # ping / candles / score-now / run
```

### 3.1 `OandaClient` (`client.py`)

- 依存: `requests` のみ
- 認証: `Authorization: Bearer <token>` ヘッダ
- ベース URL: `practice` / `live` で切替
- 公開メソッド:
  - `get_account_summary() -> dict`
  - `get_pricing(instruments) -> list[dict]`
  - `get_instrument(instrument) -> dict | None`
  - `get_candles(instrument, granularity, count|from|to, price="M", include_incomplete=False) -> DataFrame`
  - `get_open_position(instrument) -> dict | None`
  - `get_open_positions() -> list[dict]`
  - `place_market_order(instrument, units, sl_price, tp_price, client_tag) -> dict`
  - `close_position(instrument, long, short) -> dict`
- リトライ: 429 / 5xx を最大 4 回、指数バックオフ (1→2→4→8 秒)
- 4xx は即時例外 (`OandaError`) で握りつぶさない

### 3.2 `OandaConfig` (`config.py`)

すべてのチューニング対象を 1 つの dataclass に集約。優先度:

1. JSON ファイル (例: `examples/oanda_jp225.json`)
2. 環境変数 (`OANDA_TOKEN` / `OANDA_ACCOUNT_ID` / `OANDA_ENV` / `OANDA_DRY_RUN`)

カテゴリ:
- 接続: `env`, `token`, `account_id`
- 銘柄: `instrument`, `granularity_entry/mid/upper`, `candle_lookback`
- 戦略: `BacktestParams` と同じフィールド (閾値 / リスク / ATR / 重み)
- セーフティ: `dry_run`, `poll_buffer_sec`, `max_units_per_trade`, `max_daily_loss_pct`, `max_consec_losses`, `log_csv_path`

### 3.3 `size_index_units` (`sizing.py`)

```
risk_money    = NAV * risk_pct / 100
sl_distance   = ATR * sl_atr_mult
units         = floor(risk_money / sl_distance)        # JP225_JPY: 1 unit = 1 JPY/pt
units_final   = min(units, max_units_per_trade)
```

JP225_JPY 以外の銘柄 (特に非 JPY 建て FX) は通貨換算が必要 → 将来拡張ポイント。

### 3.4 `LiveRunner` (`runner.py`)

#### 3.4.1 ライフサイクル
1. 起動時: アカウント疎通 (`get_account_summary`)
2. `signal.signal(SIGINT/SIGTERM, request_stop)` を設定
3. メインループ:
   1. `next_bar_close(now_utc, granularity_entry)` で次のバー確定時刻を計算
   2. `+ poll_buffer_sec` だけ待機 (`time.sleep` を 5 秒刻みで分割し、`_stop` を確認)
   3. `_tick()` 実行
   4. 例外時はログして次イテレーションへ
4. 停止: `_stop=True` を見てループ脱出

#### 3.4.2 `_tick()` の流れ
```
fetch M5 / H1 / D1 candles (complete=True のみ)
↓
aggregate(...) → SignalsAggregated
↓
NAV / 日次基準価 / ポジション状態取得
↓
分岐:
  - in-position: 反対シグナル >= opposite_exit_score → close
  - flat:
      - daily_loss / consec_loss / atr_na ガード
      - score >= long_threshold → BUY
      - score <= short_threshold → SELL
      - else → HOLD
↓
log_row(CSV)
```

#### 3.4.3 SL / TP 計算
- BUY: `sl = close - ATR * mult`, `tp = close + ATR * mult * tp_rr`
- SELL: `sl = close + ATR * mult`, `tp = close - ATR * mult * tp_rr`
- OANDA 側で `stopLossOnFill` / `takeProfitOnFill` をブラケット指定

#### 3.4.4 セーフティガード
| ガード         | 発火条件                                                 | アクション                       |
|----------------|----------------------------------------------------------|----------------------------------|
| daily_loss     | `(anchor_nav - nav) / anchor_nav >= max_daily_loss_pct`  | 新規発注スキップ                 |
| consec_loss    | 連続損切 >= `max_consec_losses`                          | 新規発注スキップ                 |
| atr_na         | ATR が NaN または 0                                      | 新規発注スキップ                 |
| max_units      | 計算 units > `max_units_per_trade`                       | キャップして発注 (キャップフラグ)|
| live_guard     | `env=live` かつ `OANDA_ALLOW_LIVE` 未設定                | 起動時に例外で拒否               |

## 4. データフロー

### 4.1 入力
- OANDA v20 candles (M5 / H1 / D1, mid price, complete=True)
- OANDA v20 account summary (NAV, currency, openTradeCount)
- OANDA v20 openPosition (instrument 単体)

### 4.2 中間
- `pandas.DataFrame` (index = UTC timestamp, cols = OHLCV + complete)
- `SignalsAggregated` (既存型, scoring.py)

### 4.3 出力
- OANDA v20 market order POST (units, SL, TP)
- ローカル CSV (`log_csv_path`)
  - 各行: `time, instrument, tf, score_total, bull_total, bear_total, aps_pressure_score, aps_div_score, d1_*, h1_*, m5_*, atr, price, nav, action`
- 標準ログ (logging, INFO レベル)

## 5. シーケンス (発注フロー)

```
LiveRunner       OandaClient        OANDA REST API
   │                 │                   │
   ├─ schedule next M5+8s ──             │
   │                 │                   │
   │  _tick()        │                   │
   ├────────────────►│ get_candles M5    │
   │                 ├──────────────────►│
   │                 │◄── 200 OK ────────┤
   │                 │                   │
   │                 │ (×3 TF)           │
   │                 │                   │
   ├─ aggregate() ────────────────────── │ (local)
   ├─ sizing() ─────────────────────────│ (local)
   │                 │                   │
   ├────────────────►│ summary           │
   │                 ├──────────────────►│
   │                 │◄── 200 OK ────────┤
   │                 │                   │
   │  (score >= thr) │                   │
   ├────────────────►│ place_market_order│
   │                 ├──────────────────►│
   │                 │◄── 201 Created ───┤
   │                 │                   │
   ├─ log_row ──────────────────────────►│ (CSV)
```

## 6. エラーハンドリング戦略

| エラー                  | 対応                                                     |
|-------------------------|----------------------------------------------------------|
| 接続エラー / Timeout    | `requests` 例外 → リトライ (4 回)                        |
| HTTP 429 / 5xx          | 指数バックオフでリトライ → 諦めたら `OandaError`         |
| HTTP 4xx (auth, 不正)   | 即時 `OandaError`、ループ側でログして 15 秒待機 → 続行   |
| Pandas / scoring 例外   | catch all、`logging.exception`、30 秒待機 → 続行          |
| `SIGINT/SIGTERM`        | `_stop=True`、現在のスリープから抜けて exit              |
| 非対応 granularity      | 起動時 `ValueError`                                      |

> **ループ自体は落とさない** が、auth エラーのような根本問題は CSV/ログを見て利用者が手動で対処する。サイレント失敗を避けるため、全エラーを `logging.error` で出力。

## 7. セキュリティ

- API トークンは **環境変数のみ** で受け取る (`OANDA_TOKEN`)
- `.env` を `.gitignore`、`examples/.env.example` のみリポジトリ管理
- HTTPS 強制 (OANDA エンドポイントは HTTPS only)
- `OANDA_ENV=live` には `OANDA_ALLOW_LIVE=1` の二重ガード
- ログ・CSV にはトークンが入らないことを確認 (現状未使用)
- リトライログに HTTP body の先頭 300 文字のみ出力 (token は body に含まれない)

## 8. テスト戦略

| レイヤ          | 手法                                                     |
|-----------------|----------------------------------------------------------|
| `sizing.py`     | ユニットテスト (NAV / ATR の各種境界)                    |
| `runner.next_bar_close` | ユニットテスト (M5 / H1 / D1 境界, 分跨ぎ, 時跨ぎ) |
| `OandaClient`   | `requests.Session.request` を mock → body / param 検証   |
| エンドツーエンド| デモ口座で `--dry-run`、24h 連続稼働、CSV 突合           |
| パリティ        | デモ CSV vs オフライン backtest CSV を `diff` で比較     |

## 9. デプロイ環境

候補:
- **ローカル PC** (常時稼働できる前提なら最も簡単)
- **クラウド VPS** (Lightsail / さくら / ConoHa 月額 〜1,500 円)
- **コンテナ** (Docker + `restart: unless-stopped`)

最小要件: Python 3.10+, 512MB RAM, アウトバウンド HTTPS 許可, NTP 同期。

推奨: `systemd` (Linux) / `launchd` (macOS) / `nssm` (Windows) でサービス化。

## 10. 将来拡張ポイント

- **複数銘柄**: `OandaConfig.instruments: list[str]` 化、`_tick()` を per-instrument 化
- **通知**: `notifier.py` を追加し、エントリー/エグジット/サーキット発火を Webhook 送信
- **ストリーミング価格**: `/v3/accounts/{id}/pricing/stream` を購読、バー内 SL ヒット先取り
- **ポジションサイズ最適化**: ATR ベースから Kelly / 平均 RR ベースへ
- **資金通貨換算**: 非 JPY 建て FX 用に `sizing.size_fx_units()` を追加
- **モデル更新**: スコア式を `tune.py` 出力 JSON で動的差し替え
