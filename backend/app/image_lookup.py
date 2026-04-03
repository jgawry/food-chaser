import time
import threading
import logging

import requests

from .db import (
    get_deals_needing_images,
    get_image_cache,
    set_image_cache,
    update_deal_image,
)

logger = logging.getLogger(__name__)

PLACEHOLDER_URL = "/api/placeholder-image"
_WIKI_SEARCH_URL = "https://en.wikipedia.org/w/api.php"
_WIKI_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{}"
_USER_AGENT = "food-chaser/1.0 (grocery deal tracker; https://github.com)"


def _search_wikipedia(name: str, brand: str = None) -> str | None:
    """Search Wikipedia for a product image URL.

    Returns a URL string if a thumbnail was found, or None if Wikipedia
    responded successfully but had no matching article/image. Raises on
    network/server errors so the caller can skip caching and retry.
    """
    query = f"{brand} {name}".strip() if brand else name

    # Step 1: find the best-matching article title
    search_resp = requests.get(
        _WIKI_SEARCH_URL,
        params={
            "action": "opensearch",
            "search": query,
            "limit": 1,
            "format": "json",
        },
        timeout=8,
        headers={"User-Agent": _USER_AGENT},
    )
    search_resp.raise_for_status()
    results = search_resp.json()
    titles = results[1] if len(results) > 1 else []
    if not titles:
        return None

    # Step 2: fetch the article summary and extract thumbnail
    summary_resp = requests.get(
        _WIKI_SUMMARY_URL.format(requests.utils.quote(titles[0], safe="")),
        timeout=8,
        headers={"User-Agent": _USER_AGENT},
    )
    if summary_resp.status_code == 404:
        return None
    summary_resp.raise_for_status()
    thumbnail = summary_resp.json().get("thumbnail")
    if thumbnail:
        return thumbnail.get("source")
    return None


def _run_lookup(app):
    """Background worker: fill in image_url for deals that lack one."""
    deals = get_deals_needing_images(app)
    first_request = True
    for deal in deals:
        name = deal.get("name") or ""
        brand = deal.get("brand") or ""
        key = f"{brand} {name}".strip().lower()
        if not key:
            continue

        cached = get_image_cache(app, key)
        if cached is not None:
            url = cached["image_url"] or PLACEHOLDER_URL
        else:
            if not first_request:
                time.sleep(0.3)
            first_request = False
            try:
                url = _search_wikipedia(name, brand or None)
            except Exception:
                logger.warning("Wikipedia lookup failed for %r", key, exc_info=True)
                continue  # don't cache — leave image_url NULL so next scrape retries
            set_image_cache(app, key, url)
            url = url or PLACEHOLDER_URL

        update_deal_image(app, deal["product_id"], deal["category"], url)


def enqueue_missing(app):
    """Spawn a background thread to fill in image_url for deals that lack one."""
    t = threading.Thread(target=_run_lookup, args=(app,), daemon=True)
    t.start()
