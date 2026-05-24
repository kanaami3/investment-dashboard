# Operations Docs — OANDA Japan ライブ運用

`aps_mtf` パッケージを OANDA Japan デモ口座で運用立ち上げするためのドキュメント一式。

| ファイル                  | 目的                                            | 主な読者         |
|---------------------------|-------------------------------------------------|------------------|
| `01_requirements.md`      | 要件定義 (FR / NFR / 受け入れ基準 / リスク)     | 利用者・レビュア |
| `02_design.md`            | 設計書 (アーキテクチャ / モジュール / DataFlow) | 開発者・利用者   |
| `03_runbook.md`           | 手順書 (Phase 0〜6 の作業手順)                  | 利用者 (運用)    |
| `04_tasks.md`             | タスクリスト (進捗トラッキング)                  | 利用者           |
| `05_stock_tools.md`       | 株式 TA ダッシュボード + 毎時 Discord 通知       | 利用者           |
| `06_streamlit_deploy.md`  | Streamlit Community Cloud デプロイ手順           | 利用者           |
| `07_mt5_demo_runbook.md`  | MT5 APS_MTF_EA デモ運用手順                      | 利用者 (運用)    |

## 読む順番

1. `01_requirements.md` で「**何を達成するか / なぜ**」を理解
2. `02_design.md` で「**どう動くか**」を理解
3. `03_runbook.md` で「**何をどう操作するか**」を実行
4. `04_tasks.md` で「**今どこまで進んだか**」を管理

## 関連ファイル

- 実装: `python/aps_mtf/oanda/`
- 設定例: `python/examples/oanda_jp225.json`
- 環境変数例: `python/examples/.env.example`
- スコアロジック仕様: `docs/SPEC.md`
