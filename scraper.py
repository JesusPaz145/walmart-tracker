import requests
import json
import re
import time
import random
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
    "DNT": "1",
}

WALMART_URLS = [
    ("Electronics Deals", "https://www.walmart.com/shop/deals/electronics"),
]

SAMS_URLS = [
    ("Tech Deals", "https://www.samsclub.com/b/tech-deals/1240109"),
]

CATEGORIES = [
    ("Laptops & Computers", [
        "laptop", "notebook", "chromebook", "macbook", "desktop", "all-in-one",
        "computer", " pc ", "gaming pc", "mini pc", "imac", "thinkpad", "ideapad",
        "vivobook", "zenbook", "surface pro", "surface laptop",
    ]),
    ("Phones", [
        "phone", "smartphone", "iphone", "galaxy s", "galaxy a", "pixel ",
        "motorola moto", "prepaid phone", "unlocked phone", "5g phone",
    ]),
    ("TVs", [
        " tv", "television", "oled", "qled", "4k tv", "8k tv", "smart tv",
        "roku tv", "fire tv", "android tv", "hisense", "tcl ", "vizio",
        "samsung tv", "lg tv", "sony tv",
    ]),
    ("Consoles & Gaming", [
        "playstation", "xbox", "nintendo", "switch ", "ps5", "ps4", "game console",
        "gaming console", "steam deck", "oculus", "meta quest", "vr headset",
        "controller", "gamepad",
    ]),
    ("Audio", [
        "headphone", "earbud", "airpod", "earphone", "speaker", "soundbar",
        "bluetooth speaker", "headset", "subwoofer", "home theater",
        "noise canceling", "noise cancelling",
    ]),
    ("Tablets", [
        "tablet", "ipad", "fire hd", "fire tablet", "android tablet",
        "drawing tablet", "e-reader", "kindle",
    ]),
    ("Smart Home & Cameras", [
        "smart home", "smart plug", "smart bulb", "smart light", "ring ",
        "security camera", "doorbell camera", "nest ", "echo ", "alexa ",
        "google home", "robot vacuum", "roomba",
    ]),
]
OTHER_CATEGORY = "Other Tech"


def categorize(name: str) -> str:
    lower = " " + name.lower() + " "
    for category, keywords in CATEGORIES:
        for kw in keywords:
            if kw in lower:
                return category
    return OTHER_CATEGORY


def make_session() -> requests.Session:
    return requests.Session()


def fetch_page(session: requests.Session, url: str) -> str | None:
    for attempt in range(2):
        try:
            resp = session.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
            if resp.status_code == 200:
                return resp.text
        except requests.RequestException as e:
            print(f"    attempt {attempt + 1} failed: {e}")
    return None


def parse_price_str(s) -> float | None:
    if isinstance(s, (int, float)):
        return float(s) if s > 0 else None
    if isinstance(s, str):
        clean = re.sub(r"[^\d.]", "", s)
        try:
            v = float(clean)
            return v if v > 0 else None
        except ValueError:
            pass
    return None


def parse_item(item: dict, base_url: str) -> dict | None:
    name = item.get("name") or item.get("title") or item.get("displayName")
    if not name:
        return None

    price_info = item.get("priceInfo") or {}

    price = parse_price_str(item.get("price"))
    if price is None:
        for key in ("minPrice", "currentPrice", "salePrice"):
            price = parse_price_str(price_info.get(key))
            if price:
                break
    if price is None:
        price = parse_price_str(price_info.get("linePrice"))

    was_price = parse_price_str(price_info.get("wasPrice"))

    savings = None
    savings_pct = None
    if was_price and price and was_price > price:
        savings = round(was_price - price, 2)
    else:
        amt = price_info.get("savingsAmt")
        if isinstance(amt, (int, float)) and amt > 0 and price:
            savings = round(float(amt), 2)
            was_price = round(price + savings, 2)

    if savings and was_price:
        savings_pct = round((savings / was_price) * 100)
    if not savings:
        return None  # not a real deal

    if not price or price <= 0:
        return None

    url = item.get("canonicalUrl") or item.get("productUrl") or item.get("url") or ""
    if url and not url.startswith("http"):
        url = base_url + url
    if not url:
        item_id = item.get("id") or item.get("usItemId") or item.get("itemId")
        if item_id:
            url = f"{base_url}/ip/{item_id}"
    if not url:
        return None

    image = None
    img_info = item.get("imageInfo") or {}
    if isinstance(img_info, dict):
        image = img_info.get("thumbnailUrl") or img_info.get("url")
    if not image:
        image = item.get("image") or item.get("thumbnailUrl")

    return {
        "name": name.strip(),
        "price": price,
        "was_price": was_price,
        "savings": savings,
        "savings_pct": savings_pct,
        "url": url,
        "image": image,
        "category": categorize(name),
    }


def extract_products(data: dict, base_url: str) -> list[dict]:
    products = []

    def search(obj, depth=0):
        if depth > 30:
            return
        if isinstance(obj, dict):
            if "itemStacks" in obj:
                for stack in obj["itemStacks"]:
                    if isinstance(stack, dict):
                        for item in stack.get("items", []):
                            if isinstance(item, dict):
                                p = parse_item(item, base_url)
                                if p:
                                    products.append(p)
            for v in obj.values():
                if isinstance(v, (dict, list)):
                    search(v, depth + 1)
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, (dict, list)):
                    search(item, depth + 1)

    search(data)
    return products


def parse_html(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    script = soup.find("script", {"id": "__NEXT_DATA__"})
    if script and script.string:
        try:
            return extract_products(json.loads(script.string), base_url)
        except json.JSONDecodeError:
            pass
    return []


def is_blocked(html: str) -> bool:
    """Detect common bot-block pages."""
    lower = html[:2000].lower()
    return any(k in lower for k in ("access denied", "blocked", "robot", "captcha", "unusual traffic"))


def scrape(urls: list[tuple], base_url: str, retailer: str) -> tuple[list[dict], str | None]:
    session = make_session()
    all_products: list[dict] = []
    seen: set[str] = set()
    error = None

    for label, url in urls:
        print(f"  [{retailer}] {label}")
        html = fetch_page(session, url)
        if not html:
            error = f"{retailer} no respondió"
            continue
        if is_blocked(html):
            error = f"{retailer} bloqueó la solicitud (IP de servidor detectada)"
            print(f"  [{retailer}] BLOCKED")
            continue
        for p in parse_html(html, base_url):
            if p["url"] not in seen:
                seen.add(p["url"])
                p["source"] = label
                p["retailer"] = retailer
                all_products.append(p)

    print(f"  [{retailer}] Total: {len(all_products)} deals")
    return all_products, error if not all_products else None


def _build_result(products: list[dict], error: str | None) -> dict:
    category_counts: dict[str, int] = {}
    for p in products:
        cat = p.get("category", OTHER_CATEGORY)
        category_counts[cat] = category_counts.get(cat, 0) + 1
    return {
        "products": products,
        "total": len(products),
        "categories": category_counts,
        "error": error,
    }


def get_walmart_deals() -> dict:
    products, error = scrape(WALMART_URLS, "https://www.walmart.com", "Walmart")
    return _build_result(products, error)


def get_sams_deals() -> dict:
    products, error = scrape(SAMS_URLS, "https://www.samsclub.com", "Sam's Club")
    return _build_result(products, error)
