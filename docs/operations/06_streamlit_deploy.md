# Streamlit Cloud デプロイ手順

| 項目     | 値                                                       |
|----------|----------------------------------------------------------|
| ドメイン | `https://<your-app>.streamlit.app`                       |
| 認証     | パスワード (アプリ内、`st.secrets.app_password` で照合)  |
| 課金     | Streamlit Community Cloud は個人利用無料                  |
| 自動更新 | GitHub の対象ブランチに push すると自動で再デプロイ       |

---

## 1. 何が公開され、何が公開されないか

| コンポーネント                  | クラウドで動く?              | 補足                                     |
|---------------------------------|-----------------------------|------------------------------------------|
| `streamlit_app.py` (ダッシュボード)| ✅ 動く                    | 閲覧専用、yfinance で都度データ取得      |
| `stock_tools.scheduler` (毎時通知) | ❌ 動かない                | 常駐プロセス不可。自宅PC/VPS で systemd |
| `aps_mtf.oanda.runner` (OANDA EA) | ❌ 動かない                | 同上                                     |

> **Streamlit Cloud は HTTP リクエスト駆動**。アイドル時にスリープ、最初の
> アクセスで起動するモデルなので、「裏で動き続ける処理」は別ホストに置く。

## 2. 事前準備

### 2-1. GitHub への push
```bash
git push -u origin claude/aps-pressure-mtf-signals-8NQ53
```
Streamlit Cloud は **public または接続済み private** リポジトリを対象に
デプロイ可能。`kanaami3/investment-dashboard` は private でも問題なし。

### 2-2. パスワードを準備
```bash
python -c "import secrets; print(secrets.token_urlsafe(24))"
```
出力 (例: `b5J8...xLpQ`) をメモ。**生成された文字列が漏れたら使い回さない**。

## 3. Streamlit Community Cloud にデプロイ

### 3-1. アカウント連携
1. https://share.streamlit.io にアクセス
2. **「Continue with GitHub」** で GitHub アカウントを連携
3. private リポジトリへのアクセスを許可

### 3-2. アプリ作成
1. ダッシュボード右上 **「New app」** → **「Deploy a public app from GitHub」**
2. 入力:
   - **Repository**: `kanaami3/investment-dashboard`
   - **Branch**: `claude/aps-pressure-mtf-signals-8NQ53` (または `main`)
   - **Main file path**: `streamlit_app.py` ← 必ず repo root のこれ
   - **App URL**: 任意のサブドメイン (例 `aps-mtf-ta`)
3. **「Advanced settings」** → **「Python version」** を `3.11` に設定 (推奨)
4. **「Deploy!」** を押すと build → install → run が走る (3〜5 分)

### 3-3. secrets を投入
1. デプロイ完了後、アプリ右上 **⋮ → Settings → Secrets**
2. 以下を貼り付け (`.streamlit/secrets.toml.example` と同じ書式):
   ```toml
   app_password = "<2-2 で生成した文字列>"
   ```
3. **「Save」** → アプリが自動で再起動

### 3-4. 動作確認
1. `https://<your-app>.streamlit.app` を開く
2. パスワード入力欄が出ることを確認
3. 誤入力 → `wrong password` 表示
4. 正入力 → ダッシュボード表示
5. サイドバーで `7203.T` などを入れてチャート描画を確認

## 4. ローカル開発

`.streamlit/secrets.toml` を手元に作る:
```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# エディタで app_password を編集
```

起動:
```bash
streamlit run streamlit_app.py
```

`.streamlit/secrets.toml` は `.gitignore` 済 — コミット対象に含めない。
`git status` で出てこないことを必ず確認すること。

## 5. 更新・運用

### 5-1. コード更新
通常の `git push` で自動再デプロイ。アプリページ右下に build ログ表示。

### 5-2. パスワード変更
1. アプリ Settings → Secrets で `app_password` を書き換え → Save
2. 既にログインしているセッションは無効化されない (session_state ベース)
   → 強制ログアウトしたい場合は **Manage app → Reboot app** で全セッションリセット

### 5-3. アプリ削除/停止
- 停止: Manage app → Pause (リクエストで再開しない)
- 削除: Settings → Delete app

## 6. トラブルシュート

| 症状                                          | 対処                                                       |
|-----------------------------------------------|------------------------------------------------------------|
| build で `ModuleNotFoundError: stock_tools`   | `streamlit_app.py` が repo root にあるか、`Main file path` が正しいか確認 |
| build で `Could not find requirements.txt`    | `requirements.txt` が repo root にあるか確認               |
| `Server misconfiguration: app_password ...`   | Secrets UI に `app_password = "..."` を投入                |
| デプロイ後ずっと "Please wait..."             | アイドルスリープ後の cold start (30〜60秒)、待つ           |
| `429 Too Many Requests` (yfinance)            | アクセス集中時の Yahoo 制限 → 数分待つ                     |
| パスワード入力後画面が真っ白                  | dashboard.py の例外 → Manage app → Logs で stack 確認      |

## 7. セキュリティ・運用ノート

- **パスワードはあくまで簡易ゲート**。本格的な認証 (MFA/OIDC) が必要なら
  Streamlit Cloud Teams (有料) または FastAPI ベースに移行する
- **secrets.toml は絶対にコミットしない**。`git log --all -p -S app_password`
  で履歴に残っていないか時々確認
- **public リポジトリ化する場合**は、watchlist.csv 等に機密情報が
  入っていないかも合わせて確認 (現状は銘柄リストのみで問題なし)
- **アクセスログ**は Streamlit Cloud 側で確認可 (Settings → Logs)
- **負荷上限**: Community Cloud は 1GB RAM / 1 vCPU 程度。重いバックテスト
  は別途オフラインで実行する想定で
