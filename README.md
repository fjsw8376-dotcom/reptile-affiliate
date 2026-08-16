# reptile-affiliate（テラリウム生活ラボ）

テラリウムで飼う生きもの（爬虫類・両生類・昆虫/クモ類）の飼育グッズを紹介する
アフィリエイトサイト。毎週月曜にGitHub Actionsが Claude APIで記事を自動生成し、
GitHub Pagesで自動公開する。

note.com記事（https://note.com/tak5456/n/ndebf6ac9b3af）で紹介されていた
「Claude Codeに1文指示して自動収益サイトを作った」という仕組みを、実際に動く形で再構築したもの。
当初は爬虫類専門サイトとしてスタートし、市場調査の結果「同じ設備メーカー（GEX/エキゾテラ等）・
同じ客層で親和性が高い」両生類・昆虫/クモ類まで対象を広げた（サイト内は`genre`でジャンル分け）。

## 仕組み

```
毎週月曜 09:00 JST
  → GitHub Actions 起動
  → scripts/generate_article.py が Claude API で記事2本を生成 (articles/*.json)
  → scripts/build_site.py が docs/ に静的HTMLを再構築
  → 変更を自動コミット・push
  → GitHub Pages が /docs を自動配信
```

PA-API（Amazon商品情報自動取得）は使わない設計。商品は `products.json` に
手動で登録し、記事生成時にそこから関連商品を選ばせる。

## ディレクトリ構成

```
site_config.json       サイト名・Amazonタグなどの設定
topics.json             記事テーマのローテーションリスト
topics_state.json       次に生成するテーマのインデックス（Actionsが自動更新）
products.json           紹介するAmazon商品（手動管理）
articles/                生成された記事データ（JSON、build_site.pyの入力）
templates/               Jinja2テンプレート・CSS
docs/                    ビルド後の静的サイト（GitHub Pagesの配信元）
scripts/
  generate_article.py    Claude APIで記事を生成
  build_site.py           articles/ から docs/ を生成
  add_product.py          products.json に商品を対話形式で追加
.github/workflows/
  weekly-publish.yml      毎週の自動生成・公開ワークフロー
```

## 商品を追加する（手動）

PA-API未申請のため、紹介したいAmazon商品は自分で登録する。

```bash
python scripts/add_product.py
```

Amazonの商品ページURL（`https://www.amazon.co.jp/dp/XXXXXXXXXX` の形）を
貼り付けると、ASINを自動抽出して products.json に追加される。
`category` は `topics.json` の `related_categories` に出てくる値
（例: ケージ／保温器具／ライト／床材／餌）と一致させると、
該当テーマの記事で自動的に紹介候補になる。
`genre`（爬虫類／両生類／昆虫・クモ類、複数可）も一致している必要がある
（例: 爬虫類専用のUVBライトを昆虫記事で紹介しないようにするため）。

商品を登録していなくても記事自体は生成される（その回は商品紹介なしの
情報記事になる）。商品数が増えるほど記事の商品紹介の精度が上がる。

## ローカルでの動作確認

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# .env の ANTHROPIC_API_KEY に実際のキーを設定してから

export $(cat .env | xargs)
python scripts/generate_article.py   # articles/ に記事が2本増える
python scripts/build_site.py         # docs/ にサイトが生成される

python -m http.server 8000 --directory docs
# http://localhost:8000 で確認
```

## GitHub Secrets の設定（必須）

リポジトリの Settings → Secrets and variables → Actions →
New repository secret で以下を登録する。

- `ANTHROPIC_API_KEY`: Anthropic Console（https://console.anthropic.com/settings/keys）で発行したAPIキー

これを登録しないと `weekly-publish.yml` は失敗する。

## 手動で今すぐ1回実行したい場合

GitHubリポジトリの Actions タブ → 「Weekly Article Publish」→
「Run workflow」から手動トリガーできる（`workflow_dispatch` 設定済み）。

## 今後の改善候補

- products.json の商品数を増やす（ジャンル別に最低3〜5個ずつ）
- サイト名・タグライン（site_config.json）を実際のブランドに合わせて調整
- プライバシーポリシー・免責事項ページの追加
- 独自ドメインの検討（Settings → Pages → Custom domain）
