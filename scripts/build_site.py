"""articles/*.json から docs/ 以下に静的サイトを生成する。

GitHub Pages は main ブランチの /docs を配信対象にしているため、
このスクリプトの出力はそのまま公開される。
"""
import json
import shutil
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = ROOT / "templates"
ARTICLES_DIR = ROOT / "articles"
DOCS_DIR = ROOT / "docs"
PRODUCTS_PATH = ROOT / "products.json"
SITE_CONFIG_PATH = ROOT / "site_config.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def is_valid_article(article: dict) -> bool:
    return (
        isinstance(article.get("sections"), list)
        and all(isinstance(s, dict) and "heading" in s and "html" in s for s in article["sections"])
        and isinstance(article.get("faq"), list)
        and all(isinstance(f, dict) and "q" in f and "a" in f for f in article["faq"])
    )


def load_articles() -> list[dict]:
    articles = []
    for path in sorted(ARTICLES_DIR.glob("*.json")):
        article = load_json(path)
        if not is_valid_article(article):
            print(f"警告: {path.name} の形式が不正なためスキップします")
            continue
        articles.append(article)
    articles.sort(key=lambda a: a["published_date"], reverse=True)
    return articles


def main() -> None:
    site = load_json(SITE_CONFIG_PATH)
    products = load_json(PRODUCTS_PATH)
    products_by_id = {p["id"]: p for p in products}
    articles = load_articles()

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    current_year = datetime.now().year

    DOCS_DIR.mkdir(exist_ok=True)
    (DOCS_DIR / "articles").mkdir(exist_ok=True)

    # .nojekyll がないと GitHub Pages が Jekyll としてビルドしようとし
    # アンダースコア始まりのファイル等が無視される場合がある
    (DOCS_DIR / ".nojekyll").touch()

    assets_src = TEMPLATES_DIR / "assets"
    assets_dst = DOCS_DIR / "assets"
    if assets_dst.exists():
        shutil.rmtree(assets_dst)
    shutil.copytree(assets_src, assets_dst)

    index_tpl = env.get_template("index.html")
    (DOCS_DIR / "index.html").write_text(
        index_tpl.render(
            site=site,
            articles=articles,
            current_year=current_year,
            root_prefix="",
            asset_prefix="",
        ),
        encoding="utf-8",
    )

    article_tpl = env.get_template("article.html")
    for article in articles:
        recommended_products = [
            products_by_id[pid]
            for pid in article.get("recommended_product_ids", [])
            if pid in products_by_id
        ]
        out_path = DOCS_DIR / "articles" / f"{article['slug']}.html"
        out_path.write_text(
            article_tpl.render(
                site=site,
                article=article,
                recommended_products=recommended_products,
                current_year=current_year,
                root_prefix="../",
                asset_prefix="../",
            ),
            encoding="utf-8",
        )

    print(f"生成完了: 記事 {len(articles)} 件 -> {DOCS_DIR}")


if __name__ == "__main__":
    main()
