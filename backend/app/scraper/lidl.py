import html
import json
import logging
import re
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

CATEGORIES = [
    {"slug": "owoce-i-warzywa",          "id": "h10071012", "label": "Owoce i warzywa", "type": "h"},
    {"slug": "mieso-i-wedliny",          "id": "h10071016", "label": "Mięso i wędliny", "type": "h"},
    {"slug": "sery-nabial",              "id": "h10071017", "label": "Sery i nabiał",   "type": "h"},
    {"slug": "napoje",                   "id": "h10071022", "label": "Napoje",           "type": "h"},
    {"slug": "jaja-i-podstawowa-zywnosc","id": "h10071045", "label": "Jaja i żywność",  "type": "h"},
    {"slug": "piekarnia-lidla",          "id": "s10008570", "label": "Piekarnia",        "type": "c"},
]

_BASE_URL = "https://www.lidl.pl"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pl-PL,pl;q=0.9",
    "Accept": "text/html,application/xhtml+xml,*/*",
}

_PRODUCT_URL_RE = re.compile(r"^/p/.+/p(\d{7,9})$")
_DISCOUNT_RE = re.compile(r"(\d+)%\s*taniej")


def _make_request(url: str, timeout: int = 10) -> str:
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError):
        # one retry
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")


def _extract_nuxt_data(page_html: str) -> list:
    m = re.search(
        r'<script[^>]+id=["\']__NUXT_DATA__["\'][^>]*>(.*?)</script>',
        page_html,
        re.DOTALL,
    )
    if not m:
        return []
    raw = html.unescape(m.group(1).strip())
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning("Failed to parse __NUXT_DATA__: %s", e)
        return []


_NAME_JUNK_RE = re.compile(
    r"^(?:code_\d+_|text_\d+_|https?://|/[phc]/|Więcej|Światy|PLN|RETAIL|0/\d|"
    r"StrikePrice|progress_|IN_STORE|white_|cena przed|\*$|Food$|Jedzenie$|"
    r"default$|Limit:|[A-Z][a-z]+/)",  # "default" theme value; "Limit:" coupon text
    re.IGNORECASE,
)


def _parse_products_from_nuxt(nuxt_array: list, category_label: str) -> list[dict]:
    """
    Parse the Nuxt3 __NUXT_DATA__ flat array.

    Layout observed for each product block (offsets from the URL string):
      URL       at i       e.g. /p/polskie-pieczarki/p10032680
      name      at i+~14   e.g. "Polskie pieczarki"
      product_id at i+~21  e.g. 10032680  (int)
      image     at i-~10   (appears before the URL)
      old_price at i+~34   (float, only if discounted)
      discount  at i+~35   e.g. "37% taniej"
      price     at i+~40   (float, current/sale price)

    For non-discounted products the single price appears at i+~24.
    We use a forward window of 45 to catch all cases.
    """
    products = []
    seen_ids = set()
    n = len(nuxt_array)

    for i, val in enumerate(nuxt_array):
        if not isinstance(val, str):
            continue
        m = _PRODUCT_URL_RE.match(val)
        if not m:
            continue
        product_id = m.group(1)
        if product_id in seen_ids:
            continue

        # Forward window captures prices; small backward window captures image
        back = nuxt_array[max(0, i - 15):i]
        fwd = nuxt_array[i + 1: min(n, i + 46)]
        combined = back + [val] + fwd

        # Prices: floats in PLN range within the forward slice only
        price_floats = sorted(
            v for v in fwd if isinstance(v, float) and 0.5 < v < 1000
        )
        if not price_floats:
            continue

        price = round(price_floats[0], 2)
        old_price = round(price_floats[-1], 2) if len(price_floats) >= 2 else None

        # Discount string
        discount_pct = None
        for v in fwd:
            if isinstance(v, str):
                dm = _DISCOUNT_RE.search(v)
                if dm:
                    discount_pct = int(dm.group(1))
                    break

        # Image URL: appears ~10 positions after the product URL string
        image_url = next(
            (v for v in fwd[:20] if isinstance(v, str) and "imgproxy" in v),
            None,
        )

        # Name: first clean short string in the forward slice
        name = None
        for v in fwd[:30]:
            if (
                isinstance(v, str)
                and 6 <= len(v) <= 80
                and not _NAME_JUNK_RE.search(v)
                and any(c.isalpha() for c in v)
                and "%" not in v
            ):
                name = v
                break

        seen_ids.add(product_id)
        products.append({
            "product_id": product_id,
            "name": name,
            "category": category_label,
            "price": price,
            "old_price": old_price if old_price != price else None,
            "discount_pct": discount_pct,
            "image_url": image_url,
            "product_url": f"{_BASE_URL}{val}",
        })

    if not products:
        logger.warning(
            "No products parsed for category '%s' — page structure may have changed",
            category_label,
        )

    return products


def scrape_all_categories() -> list:
    all_products = []

    for cat in CATEGORIES:
        url = f"{_BASE_URL}/{cat['type']}/{cat['slug']}/{cat['id']}"
        logger.info("Scraping category: %s", cat["label"])
        try:
            page_html = _make_request(url)
            nuxt_array = _extract_nuxt_data(page_html)
            products = _parse_products_from_nuxt(nuxt_array, cat["label"])
            logger.info("  Found %d products in '%s'", len(products), cat["label"])
            all_products.extend(products)
        except Exception as e:
            logger.error("Failed to scrape category '%s': %s", cat["label"], e)

    return all_products
