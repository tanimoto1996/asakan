# CLAUDE.md

## プロジェクト概要

**テック朝刊** — GitHub Actions + Gemini API(無料枠)で毎朝JST 6:30に技術ニュースの朝刊を自動発行する個人プロジェクト。

- 配信先: GitHub Pages(`docs/index.html`)+ Gmail経由の自分宛メール
- コスト0円運用が絶対条件(publicリポジトリのActions無料枠 + Gemini無料枠)

## アーキテクチャ

```
feeds.yml                        # 購読フィード定義(カテゴリ別)
scripts/generate.py              # 巡回 → Gemini要約 → HTML生成(単一スクリプト)
.github/workflows/morning.yml    # cron起動 → 生成 → docs/にcommit → メール送信
docs/                            # GitHub Pages公開ディレクトリ(生成物)
docs/archive/YYYY-MM-DD.html     # バックナンバー
```

処理フロー: `collect_articles()`(feedparser、過去26h)→ `summarize_with_gemini()`(全記事を**1リクエスト**にまとめてJSON応答)→ `render_html()`(新聞風HTML)。

## 開発コマンド

```bash
# ローカル実行(要約なしフォールバックで動作確認)
python scripts/generate.py

# Gemini込みで実行
GEMINI_API_KEY=xxx python scripts/generate.py

# 生成結果の確認
python -m http.server -d docs 8000
```

テストフレームワークは未導入。動作確認は上記の実行+`docs/index.html`の目視/grep。

## 設計原則(変更時に守ること)

1. **発行は絶対に止めない**: フィード取得失敗は該当フィードのみskip、Gemini失敗は要約なしで発行継続。例外で全体を落とすコードを書かない。
2. **Gemini呼び出しは1日1リクエスト**: 記事ごとにAPIを叩かない(無料枠のRPM/RPD節約)。
3. **依存は最小限**: 現在 `feedparser` と `pyyaml` のみ。追加時は本当に必要か検討。Gemini APIはSDKでなく`urllib`で直接叩く方針。
4. **secretsをコードに書かない**: APIキー・メール認証情報はすべてGitHub Secrets経由の環境変数。
5. **docs/ は生成物**: 手で編集しない。スタイル変更は `generate.py` の `CSS` 定数。

## 既知の注意点

- Anthropic系フィード2本は非公式ミラー(公式RSSが存在しないため)。壊れやすい前提で扱う。
- GitHub Actionsのscheduleは遅延あり(仕様)。時刻厳密性を要求する変更はしない。
- `feeds.yml` の `window_hours: 26` はcron間隔24h+遅延バッファ。短くしない。
- HTMLエスケープ必須(フィード由来のテキストは信頼しない)。

## コミット規約

日本語でOK。プレフィックス: `feat:` `fix:` `docs:` `chore:`。
生成物(docs/)のコミットはbot専用。手動コミットに含めない。
