# stock_tools — Streamlit ダッシュボード + 毎時アラート

| 項目     | 値                                                                  |
|----------|---------------------------------------------------------------------|
| パッケージ | `python/stock_tools/`                                              |
| 通知    | Discord webhook (LINE Notify は 2025-03-31 で終了)                   |
| データ源 | yfinance (Yahoo Finance, 認証不要)                                    |
| アラート | APS+MTF (`aps_mtf.scoring.aggregate`) を 60m/1d/1wk で実行            |

---

## 1. ファイル構成

```
python/stock_tools/
├── __init__.py
├── data.py         # yfinance fetch
├── indicators.py   # MA(5/25/75/200) / RSI / MACD / Bollinger
├── crosses.py      # Golden / Dead クロス検出
├── signal.py       # aps_mtf.scoring へのブリッジ (60m/1d/1wk)
├── watchlist.py    # CSV ローダ
├── notifier.py     # Discord webhook クライアント
├── scheduler.py    # 毎時ポーリングループ
├── dashboard.py    # Streamlit UI
└── cli.py          # analyze / score / notify / watch

python/examples/watchlist.csv  # サンプル監視リスト
```

## 2. セットアップ

```bash
cd python
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

`.env` に追加 (`examples/.env.example` 参照):

```dotenv
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/<id>/<token>
```

> ⚠️ Webhook URL はそれ自体がシークレット。Slack / メール / 公開リポジトリに貼らない。
> 漏洩したら Discord の Webhook 設定で **削除→新規作成** でローテート。

### Discord webhook の作り方

1. 通知を受け取りたいサーバー → チャンネル右クリック → **「チャンネルの編集」**
2. 左メニュー **「連携サービス」** → **「ウェブフック」** → **「新しいウェブフック」**
3. 名前を設定 (例: `stock-tools`) → **「ウェブフックURLをコピー」**
4. コピーした URL を `.env` の `DISCORD_WEBHOOK_URL` に貼る

## 3. 使い方

### 3-1. ダッシュボード (Streamlit)

```bash
cd python
streamlit run stock_tools/dashboard.py
```

ブラウザで `http://localhost:8501` を開く。サイドバーで:
- Symbol: yfinance ティッカー (例: `7203.T`, `^N225`, `AAPL`)
- Interval: `1d` / `60m` / `1h` / `1wk` / `1mo`
- Period: `1y` / `2y` / `5y` ...
- MA 窓 / APS+MTF 閾値

タブ:
- **Chart**: ローソク足 + MA + ボリンジャー、RSI、MACD ヒストグラム
- **APS+MTF Score**: EA と同じスコアロジック (60m=entry / 1d=mid / 1wk=upper) で算出した最新シグナル
- **Crosses**: ゴールデン/デッドクロス履歴
- **Raw data**: 直近 200 本の OHLCV

### 3-2. CLI

```bash
# 単発のテクニカル分析
python -m stock_tools.cli analyze 7203.T --interval 1d --period 2y

# 最新の APS+MTF スコア
python -m stock_tools.cli score 7203.T

# Discord テスト送信
python -m stock_tools.cli notify --message "ping from stock_tools"

# 毎時の監視ループ
python -m stock_tools.cli watch --watchlist examples/watchlist.csv
```

### 3-3. 監視リスト (CSV)

`examples/watchlist.csv` をコピーして編集。

| 列                | 内容                                                |
|-------------------|-----------------------------------------------------|
| `symbol`          | yfinance ティッカー (必須)                          |
| `name`            | 表示名                                              |
| `long_threshold`  | LONG 通知する total スコア下限 (空=デフォルト 6.0)  |
| `short_threshold` | SHORT 通知する total スコア上限 (空=デフォルト -6.0)|
| `enabled`         | `true` / `false`                                    |

例:
```csv
symbol,name,long_threshold,short_threshold,enabled
7203.T,Toyota Motor,6.0,-6.0,true
6758.T,Sony Group,6.0,-6.0,true
^N225,Nikkei 225,7.0,-7.0,true
```

## 4. アラート発火タイミング

`stock_tools.scheduler` は毎時 (デフォルトは UTC の毎時 00 分 +10 秒) に以下を実行:

1. CSV から enabled の銘柄を読み込み
2. 各銘柄について 60m / 1d / 1wk の OHLCV を取得
3. `aps_mtf.scoring.aggregate` で total / bull / bear / 11 成分を算出
4. `total >= long_threshold` → LONG、`<= short_threshold` → SHORT、それ以外 → HOLD
5. 当日のゴールデン/デッドクロスも併せて確認
6. LONG / SHORT または当日クロスがあれば Discord にリッチ Embed を送信

連続して同じ HOLD が出ても通知しない (LONG / SHORT は毎時送る — 強いシグナルなので)。

## 5. 常駐実行 (systemd)

`/etc/systemd/system/stock-tools-watch.service`:

```ini
[Unit]
Description=stock_tools hourly watcher
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/home/youruser/investment-dashboard/python
EnvironmentFile=/home/youruser/investment-dashboard/python/.env
ExecStart=/home/youruser/investment-dashboard/python/.venv/bin/python \
  -m stock_tools.cli watch --watchlist examples/watchlist.csv
Restart=on-failure
RestartSec=15

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now stock-tools-watch
sudo journalctl -u stock-tools-watch -f
```

## 6. 既知の制約

- **yfinance** は Yahoo の非公式 API。レート制限やフィールド変更で突然動かなくなることがある
- **60m データ**は最大 730 日まで遡れる。1d なら無制限
- **休場日**は前営業日のデータが返る。スコア計算上は問題ないが、休場中の毎時通知は同じ内容になる
- **^N225 等の指数**は出来高が常時 0。APS pressure (出来高加重) は無効化される — 株式銘柄の方が APS は効く
- **タイムゾーン**は内部 UTC 統一。Discord 通知時刻も UTC で記録される

## 7. トラブルシュート

| 症状                                  | 対処                                                  |
|---------------------------------------|-------------------------------------------------------|
| `DISCORD_WEBHOOK_URL not set`         | `.env` の存在と書式を確認、`--env-file` の指定確認    |
| `discord webhook failed 401/404`      | Webhook が削除/再作成されている → URL を更新          |
| `discord webhook failed 429`          | 自動リトライ済。それでも頻発するなら通知頻度を下げる |
| `no data for <symbol>`                | ティッカー誤り、または yfinance の API 変更           |
| ダッシュボードに空グラフ              | サイドバーの period が短すぎる → MA200 が NaN になる |
