# 手順書 (Runbook) — OANDA Japan デモ口座 ライブ運用

| 項目         | 値                                                  |
|--------------|-----------------------------------------------------|
| ドキュメント | 手順書 (Runbook)                                    |
| 対象         | 利用者本人                                          |
| 前提         | `01_requirements.md` / `02_design.md` を一読済み    |
| 所要時間     | Phase 0〜3 合計 ~2 時間 + デモ稼働期間 5 営業日     |

---

## Phase 0: OANDA Japan 口座準備

### 0-1. デモ口座開設
1. https://www.oanda.jp/ にアクセス
2. 「デモ口座開設」→ 氏名 / メール / パスワードを登録
3. 確認メールから本登録完了 (即時)

### 0-2. API トークン発行
1. デモ口座でログイン
2. マイページ → **「APIアクセス」** タブ
3. 「個人アクセストークンを発行」ボタン
4. 表示されたトークンをコピー (一度しか表示されないので注意)

### 0-3. アカウント ID をメモ
- マイページ上部の「ID: `101-001-xxxxxxx-001`」形式の文字列をメモ
- これがランナーの `OANDA_ACCOUNT_ID` になる

> ❗ **トークンは絶対に GitHub / Slack / メール / Discord に貼らない**

---

## Phase 1: 実行ホストのセットアップ

### 1-1. リポジトリ取得
```bash
git clone https://github.com/kanaami3/investment-dashboard.git
cd investment-dashboard
git checkout claude/aps-pressure-mtf-signals-8NQ53
```

### 1-2. Python 環境
```bash
cd python
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

確認:
```bash
python -c "import requests, pandas, numpy, dotenv; print('ok')"
```

### 1-3. 環境変数ファイル
```bash
cp examples/.env.example .env
```

`.env` を編集:
```dotenv
OANDA_TOKEN=<Phase 0-2 で取得したトークン>
OANDA_ACCOUNT_ID=<Phase 0-3 で取得した ID>
OANDA_ENV=practice
```

確認:
```bash
grep -c OANDA_TOKEN .env       # → 1 行のみ
git status                     # .env が "Untracked" に出ないことを確認 (gitignore済)
```

---

## Phase 2: 疎通確認 (手動)

### 2-1. アカウント疎通
```bash
python -m aps_mtf.oanda.cli --config examples/oanda_jp225.json ping
```

期待: JSON で `id`, `currency`, `balance`, `NAV` などが返る。
失敗時:
- `401` → トークン誤り
- `403` → アカウント ID 不一致
- 接続エラー → ホストのアウトバウンド HTTPS / DNS を確認

### 2-2. ローソク足取得
```bash
python -m aps_mtf.oanda.cli --config examples/oanda_jp225.json candles --count 5
```

期待: 直近 5 本の M5 OHLCV が DataFrame で表示される。
失敗時:
- 銘柄が空 → デモ口座で JP225_JPY が有効か OANDA Web UI で確認
- 取引時間外 → 平日昼の JST に再試行

### 2-3. 現在スコア
```bash
python -m aps_mtf.oanda.cli --config examples/oanda_jp225.json score-now
```

期待: `total / bull_total / bear_total / decision` を含む JSON。
失敗時:
- `decision` が常に HOLD でも問題なし (閾値未達なだけ)
- 各 TF の素点 (`d1.srsi` 等) が `NaN` → `candle_lookback` を増やす

---

## Phase 3: ドライ運用 (発注しない)

### 3-1. フォアグラウンド実行
```bash
python -m aps_mtf.oanda.cli --config examples/oanda_jp225.json --verbose run
```

5 分待って次のログを確認:
- `connected env=practice ...` (起動成功)
- M5 確定 +8 秒で `[DRY] LONG ...` または `HOLD` などのアクションログ
- `oanda_runner.csv` に 1 行追記されている

Ctrl-C で停止 → `runner stopped` が出れば OK。

### 3-2. バックグラウンド常駐 (Linux: nohup)
```bash
nohup python -m aps_mtf.oanda.cli --config examples/oanda_jp225.json run \
  > runner.log 2>&1 &
echo $! > runner.pid
```

停止:
```bash
kill -TERM $(cat runner.pid)
```

### 3-3. systemd ユニット (推奨)
`/etc/systemd/system/aps-mtf-runner.service`:
```ini
[Unit]
Description=APS+MTF OANDA Runner
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/home/youruser/investment-dashboard/python
EnvironmentFile=/home/youruser/investment-dashboard/python/.env
ExecStart=/home/youruser/investment-dashboard/python/.venv/bin/python \
  -m aps_mtf.oanda.cli --config examples/oanda_jp225.json run
Restart=on-failure
RestartSec=15

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now aps-mtf-runner
sudo journalctl -u aps-mtf-runner -f
```

### 3-4. 24h ドライ稼働の確認
- CSV 行数が ~288 行/日 (M5 × 24h = 288, ただし JP225 休止時間で若干減)
- 例外スタックトレースが `runner.log` に出ていない
- 同時刻のスコアが `tune.py` 出力と ±0.5 以内 (要週末バッチ突合)

---

## Phase 4: デモ実発注

### 4-1. パラメータ最終確認
`examples/oanda_jp225.json` で:
- `risk_pct`: 0.5% (デモなら 1% でも可)
- `max_units_per_trade`: 20 units (= 概ね JPY 76万円相当のエクスポージャ @38000)
- `max_daily_loss_pct`: 3.0%
- `max_consec_losses`: 4

### 4-2. ライブモード起動 (デモ口座)
```bash
python -m aps_mtf.oanda.cli --config examples/oanda_jp225.json run --live
```

> `--live` は「dry-run を無効化」の意味。`OANDA_ENV=practice` のままならデモ口座での発注。

### 4-3. 初回エントリー確認
1. ターミナルに `OPEN LONG ...` ログが出る
2. OANDA Web UI (デモ) のポジションタブに JP225_JPY ポジションが表示される
3. ポジション詳細で SL/TP がセットされている
4. `oanda_runner.csv` の `action` 列に `OPEN_LONG` (または SHORT) が記録されている

### 4-4. クローズ動作確認
- 反対シグナル発火 → `CLOSE_opposite-bear` 等が CSV に出る
- SL/TP ヒット → OANDA 側で自動決済 (CSV には次バー以降の HOLD が記録される)

---

## Phase 5: 監視・運用

### 5-1. 日次チェック (毎営業日 09:00 JST)
- [ ] `systemctl status aps-mtf-runner` (or `ps aux | grep aps_mtf`) で生存確認
- [ ] `tail -20 oanda_runner.csv` で直近行を確認 (HOLD でも更新されているか)
- [ ] OANDA Web UI で NAV と建玉数を確認
- [ ] 日次損益が `max_daily_loss_pct` を超えていないか

### 5-2. 週次チェック (土曜)
- [ ] CSV をローカルへバックアップ (`cp oanda_runner.csv backups/$(date +%F).csv`)
- [ ] スコアパリティ: 同期間のオフライン `tune.py` 出力と差分 < 0.5
- [ ] エントリー回数 / 勝率 / 最大連敗 / 最大DD を集計

### 5-3. 月次レビュー
- [ ] `risk_pct` / 重みパラメータの再チューニング (オフライン)
- [ ] パラメータ変更前後の CSV を分離 (`oanda_runner_v2.csv` に切替)

---

## Phase 6: 障害対応

### 障害: ランナーが落ちた
```bash
# 1. 状態確認
sudo systemctl status aps-mtf-runner
sudo journalctl -u aps-mtf-runner -n 100

# 2. OANDA に建玉が残っていないか Web UI で確認
#    残っていれば手動でクローズ判断
# 3. 再起動
sudo systemctl restart aps-mtf-runner
```

### 障害: API 401/403 が連発
- トークンが失効 / 削除された可能性 → OANDA Web UI で再発行
- `.env` を更新 → `sudo systemctl restart aps-mtf-runner`

### 障害: 想定外の大ロット発注
1. 即座に OANDA Web UI で手動クローズ
2. ランナー停止 (`sudo systemctl stop aps-mtf-runner`)
3. `oanda_runner.csv` の直近行から原因特定
4. `max_units_per_trade` 引き下げ、再起動

### 障害: NAV が急減 (>5% / 日)
1. ランナー停止
2. ポジション全クローズ (手動)
3. `max_daily_loss_pct` が機能しなかった理由を CSV で確認
4. 修正後に再開

---

## Phase 7: ライブ口座昇格 (将来 — 別案件)

スコープ外。実施時は本書を branch して別ドキュメント化すること。最低限の前提:
- デモで連続 4 週間、AC-02 〜 AC-07 を満たす
- OANDA Japan ライブ口座 API 申請 → 承認
- `risk_pct` を 0.1% から開始 (デモの 1/5)
- `OANDA_ENV=live`, `OANDA_ALLOW_LIVE=1` を **明示的に** セット
- 初週は毎日 NAV を手動チェック
