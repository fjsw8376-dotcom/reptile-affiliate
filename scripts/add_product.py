"""products.json に実在するAmazon商品を対話形式で追加するヘルパー。

PA-APIを使わない設計のため、商品情報は手動で登録する。
Amazonの商品ページURLを貼り付けるとASINを自動抽出する。

使い方:
    python scripts/add_product.py
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRODUCTS_PATH = ROOT / "products.json"
TOPICS_PATH = ROOT / "topics.json"

ASIN_PATTERN = re.compile(r"/(?:dp|gp/product)/([A-Z0-9]{10})")


def extract_asin(url: str) -> str | None:
    match = ASIN_PATTERN.search(url)
    return match.group(1) if match else None


def load_categories() -> list[str]:
    topics = json.loads(TOPICS_PATH.read_text(encoding="utf-8"))
    categories: set[str] = set()
    for t in topics:
        categories.update(t.get("related_categories", []))
    return sorted(categories)


def main() -> None:
    products = json.loads(PRODUCTS_PATH.read_text(encoding="utf-8"))
    categories = load_categories()

    print("=== 商品追加 ===")
    print(f"登録済みカテゴリ例: {', '.join(categories)}")

    url = input("AmazonのURL（商品ページ）: ").strip()
    asin = extract_asin(url)
    if not asin:
        asin = input("ASINを自動抽出できませんでした。ASINを直接入力してください: ").strip()

    if any(p["asin"] == asin for p in products):
        print(f"ASIN {asin} は既に登録済みです。中断しました。")
        return

    name = input("商品名: ").strip()
    category = input(f"カテゴリ（{'/'.join(categories)}）: ").strip()
    notes = input("補足メモ（商品の特徴・おすすめポイント。価格は書かない）: ").strip()
    image_url = input(
        "商品画像URL（SiteStripeで取得したもの。任意・空欄でスキップ可）: "
    ).strip()

    entry = {
        "id": asin.lower(),
        "asin": asin,
        "name": name,
        "category": category,
        "notes": notes,
    }
    if image_url:
        entry["image_url"] = image_url

    products.append(entry)

    PRODUCTS_PATH.write_text(
        json.dumps(products, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"追加しました: {name} ({asin})")


if __name__ == "__main__":
    main()
