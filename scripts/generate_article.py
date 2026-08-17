"""Claude APIでテラリウム系生体（爬虫類・両生類・昆虫/クモ類）の
グッズ紹介記事を自動生成し articles/ に保存する。

GitHub Actionsから毎週実行される想定。topics_state.json のインデックスを
進めながら topics.json を順番に消化する。1回の実行で site_config.json の
articles_per_run 件を生成する。
"""
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent.parent
SITE_CONFIG_PATH = ROOT / "site_config.json"
TOPICS_PATH = ROOT / "topics.json"
STATE_PATH = ROOT / "topics_state.json"
PRODUCTS_PATH = ROOT / "products.json"
SPECIES_IMAGES_PATH = ROOT / "species_images.json"
ARTICLES_DIR = ROOT / "articles"

MODEL = "claude-sonnet-5"

SYSTEM_PROMPT = """あなたは日本のテラリウム系ペット飼育情報サイトの専属ライターです。
爬虫類・両生類・昆虫/クモ類（クワガタ、カブトムシ、タランチュラ等）を対象に、
初心者〜中級者の飼育者に向けて、信頼できる一般的な飼育知識を分かりやすく伝える記事を書きます。

厳守事項:
- 記事は指定されたジャンル（爬虫類／両生類／昆虫・クモ類）の生体に関する内容に限定する。他ジャンルの生体を混同しない
- 事実に基づかない断定（治療効果・寿命の保証など）は書かない
- 商品の価格や詳細スペックの具体的な数字は書かない（変動するため。名前と用途の説明にとどめる）
- 個体の健康に関わる内容は「専門の動物病院・ショップに相談を」という趣旨を自然に含める
- 見出し・本文は自然なSEOを意識するが、キーワードの不自然な連呼はしない
- 断定できない情報は「一般的には」「〜と言われています」等、表現を和らげる
- 本文はHTMLの断片（h2は使わず、pやul/li、strongなどのタグのみ）で書く。h1やhtml/head/bodyタグは書かない
"""

ARTICLE_TOOL = {
    "name": "submit_article",
    "description": "生成した記事をJSON構造で提出する",
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "記事タイトル（30〜40字目安）"},
            "meta_description": {"type": "string", "description": "検索結果に出る説明文。100〜120字"},
            "slug": {"type": "string", "description": "URL用のスラッグ。半角英数とハイフンのみ"},
            "intro_html": {"type": "string", "description": "導入部分のHTML断片（2〜3段落）"},
            "sections": {
                "type": "array",
                "description": "本文の見出しセクション。3〜5個",
                "items": {
                    "type": "object",
                    "properties": {
                        "heading": {"type": "string"},
                        "html": {"type": "string"},
                    },
                    "required": ["heading", "html"],
                    "additionalProperties": False,
                },
            },
            "faq": {
                "type": "array",
                "description": "よくある質問。2〜4個",
                "items": {
                    "type": "object",
                    "properties": {"q": {"type": "string"}, "a": {"type": "string"}},
                    "required": ["q", "a"],
                    "additionalProperties": False,
                },
            },
            "recommended_product_ids": {
                "type": "array",
                "description": "紹介候補として渡された商品リストの中から、この記事に関連するものの id。関連商品がなければ空配列",
                "items": {"type": "string"},
            },
        },
        "required": [
            "title",
            "meta_description",
            "slug",
            "intro_html",
            "sections",
            "faq",
            "recommended_product_ids",
        ],
        "additionalProperties": False,
    },
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


GUIDE_FORMAT_INSTRUCTIONS = """記事の形式: ガイド・ハウツー記事
- テーマについて知っておくべきポイントを3〜5個のセクションに分けて解説する
- 各セクションは「なぜそれが重要か」「初心者がやりがちな失敗」を含めると読み応えが出る
- 商品紹介は自然な流れで触れる程度でよい（無理に全セクションに商品を絡めない）
"""

COMPARISON_FORMAT_INSTRUCTIONS = """記事の形式: 比較・おすすめランキング記事
- 「結局どれを選べばいいか」に答える記事にする。読者は購入を検討している
- sections は基本的に1セクション＝1商品として構成する（候補商品の数だけセクションを作る。3〜5個の範囲に収める）
- 各セクションのhtmlには、その商品の特徴・メリット・「こんな人におすすめ」を必ず1文含める
- recommended_product_ids には、記事で取り上げた商品のidを漏れなく含める
- 候補商品が2個以下しかない場合は、無理に比較記事にせず「選ぶ時に見るべきポイント」を中心にした構成に切り替えてよい
- 記事の冒頭（intro_html）で「結論、こういう人には〇〇がおすすめ」という要約を先出しする
"""


def build_user_prompt(topic: dict, candidate_products: list[dict]) -> str:
    products_text = "なし"
    if candidate_products:
        lines = [
            f"- id: {p['id']} / 商品名: {p['name']} / メモ: {p.get('notes', '')}"
            for p in candidate_products
        ]
        products_text = "\n".join(lines)

    format_instructions = (
        COMPARISON_FORMAT_INSTRUCTIONS
        if topic.get("format") == "comparison"
        else GUIDE_FORMAT_INSTRUCTIONS
    )

    return f"""以下のテーマで記事を1本作成し、submit_article ツールで提出してください。

対象ジャンル: {topic.get('genre', '爬虫類')}
テーマ: {topic['topic']}

{format_instructions}

紹介候補の商品（この中から関連するものだけ recommended_product_ids に含める。無理に全部使わなくてよい。存在しない商品や候補にない商品を書かない）:
{products_text}
"""


def validate_article(article: dict) -> None:
    if not isinstance(article.get("sections"), list) or not all(
        isinstance(s, dict) and isinstance(s.get("heading"), str) and isinstance(s.get("html"), str)
        for s in article["sections"]
    ):
        raise ValueError("sections が不正な形式です")
    if not isinstance(article.get("faq"), list) or not all(
        isinstance(f, dict) and isinstance(f.get("q"), str) and isinstance(f.get("a"), str)
        for f in article["faq"]
    ):
        raise ValueError("faq が不正な形式です")
    if not isinstance(article.get("recommended_product_ids"), list):
        raise ValueError("recommended_product_ids が不正な形式です")


def generate_one(
    client: anthropic.Anthropic, topic: dict, products: list[dict], max_attempts: int = 3
) -> dict:
    genre = topic.get("genre", "爬虫類")
    candidates = [
        p
        for p in products
        if p["category"] in topic.get("related_categories", []) and genre in p.get("genre", [])
    ]

    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        response = client.messages.create(
            model=MODEL,
            max_tokens=4000,
            system=SYSTEM_PROMPT,
            tools=[ARTICLE_TOOL],
            tool_choice={"type": "tool", "name": "submit_article"},
            messages=[{"role": "user", "content": build_user_prompt(topic, candidates)}],
        )

        article = None
        for block in response.content:
            if block.type == "tool_use" and block.name == "submit_article":
                article = block.input
                break

        if article is None:
            last_error = RuntimeError("submit_article ツール呼び出しが見つかりませんでした")
            print(f"  試行{attempt}: ツール呼び出しなし。再試行します")
            continue

        try:
            validate_article(article)
            return article
        except ValueError as e:
            last_error = e
            print(f"  試行{attempt}: 生成データが不正でした（{e}）。再試行します")

    raise RuntimeError(f"{max_attempts}回試行しましたが有効な記事を生成できませんでした: {last_error}")


def find_species_image(topic_text: str, species_images: dict) -> dict | None:
    for keyword, image in species_images.items():
        if keyword in topic_text:
            return image
    return None


def main() -> None:
    config = load_json(SITE_CONFIG_PATH)
    topics = load_json(TOPICS_PATH)
    state = load_json(STATE_PATH)
    products = load_json(PRODUCTS_PATH)
    species_images = load_json(SPECIES_IMAGES_PATH) if SPECIES_IMAGES_PATH.exists() else {}

    client = anthropic.Anthropic()

    count = config.get("articles_per_run", 2)
    today = date.today().isoformat()
    now_iso = datetime.now(timezone.utc).isoformat()

    ARTICLES_DIR.mkdir(exist_ok=True)

    for _ in range(count):
        state["last_index"] = (state["last_index"] + 1) % len(topics)
        topic = topics[state["last_index"]]

        print(f"生成中: {topic['topic']}")
        article = generate_one(client, topic, products)
        article["published_date"] = today
        article["generated_at"] = now_iso
        article["source_topic"] = topic["topic"]
        article["format"] = topic.get("format", "guide")
        article["genre"] = topic.get("genre", "爬虫類")
        species_image = find_species_image(topic["topic"], species_images)
        if species_image:
            article["species_image"] = species_image

        out_path = ARTICLES_DIR / f"{today}-{article['slug']}.json"
        save_json(out_path, article)
        print(f"保存: {out_path}")

    save_json(STATE_PATH, state)


if __name__ == "__main__":
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("環境変数 ANTHROPIC_API_KEY が設定されていません")
    main()
