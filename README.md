# テック朝刊 ☕

GitHub Actions + Gemini API(無料枠)で毎朝、技術ニュースの朝刊を自動発行するリポジトリ。

- **GitHub Pages**: 要約付きの朝刊ページを毎朝更新(バックナンバー付き)
- **メール**: 同じ紙面を自分宛に送信(任意)
- **コスト**: 0円(publicリポジトリのActions無料 + Gemini無料枠)

## 仕組み

毎朝 JST 6:30 に GitHub Actions が起動し、`feeds.yml` のRSSを巡回。
過去26時間の新着記事を Gemini に1リクエストでまとめて渡し、
日本語要約と注目度(必読/注目/参考)を付けて `docs/index.html` を生成・コミットします。
Geminiが失敗しても要約なしで発行は継続します(発行が止まらない設計)。

## セットアップ手順

### 1. リポジトリ作成

このディレクトリ一式を **public** リポジトリとしてpush。
(publicならActionsの実行時間が無制限で無料)

### 2. Gemini APIキー取得

1. [Google AI Studio](https://aistudio.google.com/) にGoogleアカウントでログイン
2. 「Get API key」からキーを作成(クレジットカード不要)
3. リポジトリの Settings → Secrets and variables → Actions → New repository secret
   - Name: `GEMINI_API_KEY` / Value: 取得したキー

### 3. GitHub Pages 有効化

Settings → Pages → Build and deployment:
- Source: **Deploy from a branch**
- Branch: **main** / フォルダ: **/docs**

公開URLは `https://<ユーザー名>.github.io/<リポジトリ名>/` 。これをブックマーク。

### 4. メール送信(任意)

Gmailを使う場合:

1. Googleアカウントで2段階認証を有効化
2. [アプリパスワード](https://myaccount.google.com/apppasswords) を発行
3. Secretsに以下を追加:
   - `MAIL_USERNAME`: Gmailアドレス
   - `MAIL_PASSWORD`: アプリパスワード(16桁)
   - `MAIL_TO`: 送信先アドレス(自分宛なら同じでOK)

Secrets未設定ならメールステップは自動でスキップされます。

### 5. 動作確認

Actions タブ → `morning-paper` → **Run workflow** で手動実行。
成功したらPagesのURLを開いて紙面を確認。

## カスタマイズ

- **フィードの追加/削除**: `feeds.yml` を編集するだけ
- **配信時刻**: `.github/workflows/morning.yml` の cron(UTC表記に注意。JST-9時間)
- **モデル変更**: Settings → Variables に `GEMINI_MODEL` を設定(デフォルト `gemini-2.5-flash`)
- **見た目**: `scripts/generate.py` の `CSS` 定数

## 注意事項

- GitHub Actions の schedule は数分〜数十分遅延することがあります(仕様)
- Gemini無料枠のプロンプトはGoogleのモデル改善に使われる場合があります(公開RSSの要約なので実害なし)
- Anthropic Newsは公式RSSがないため非公式ミラーを使用。止まったら
  `https://github.com/Olshansk/rss-feeds` の `feed_anthropic_news.xml` 等に差し替え可
