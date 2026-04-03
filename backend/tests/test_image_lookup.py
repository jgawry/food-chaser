import pytest
from unittest.mock import patch, MagicMock, call

from app.db import save_deals, get_deals_needing_images, update_deal_image, get_image_cache, set_image_cache
from app.image_lookup import _search_wikipedia, _run_lookup, enqueue_missing, PLACEHOLDER_URL


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def app_with_imageless_deal(flask_app):
    save_deals(flask_app, [{
        "product_id": "p1",
        "name": "Raffaello",
        "brand": "Ferrero",
        "qty": "150 g",
        "source": "leaflet",
        "category": "Gazetka",
        "price": 15.99,
    }])
    return flask_app


def _mock_wiki_responses(search_titles, thumbnail_url):
    """Build the two mock responses Wikipedia lookup makes."""
    search_resp = MagicMock()
    search_resp.status_code = 200
    search_resp.json.return_value = ["query", search_titles, [], []]

    summary_resp = MagicMock()
    summary_resp.status_code = 200
    summary_resp.json.return_value = (
        {"thumbnail": {"source": thumbnail_url}} if thumbnail_url else {}
    )

    return [search_resp, summary_resp]


# ── _search_wikipedia ─────────────────────────────────────────────────────────

def test_search_wikipedia_returns_thumbnail_url():
    responses = _mock_wiki_responses(["Raffaello (confectionery)"], "https://wiki.org/raffaello.jpg")
    with patch("app.image_lookup.requests.get", side_effect=responses):
        result = _search_wikipedia("Raffaello", "Ferrero")
    assert result == "https://wiki.org/raffaello.jpg"


def test_search_wikipedia_includes_brand_in_query():
    responses = _mock_wiki_responses([], None)
    with patch("app.image_lookup.requests.get", side_effect=responses[:1]) as mock_get:
        _search_wikipedia("Raffaello", "Ferrero")
    params = mock_get.call_args_list[0][1]["params"]
    assert params["search"] == "Ferrero Raffaello"


def test_search_wikipedia_uses_name_only_when_no_brand():
    responses = _mock_wiki_responses([], None)
    with patch("app.image_lookup.requests.get", side_effect=responses[:1]) as mock_get:
        _search_wikipedia("Pepsi")
    assert mock_get.call_args_list[0][1]["params"]["search"] == "Pepsi"


def test_search_wikipedia_returns_none_when_no_search_results():
    search_resp = MagicMock()
    search_resp.json.return_value = ["query", [], [], []]
    with patch("app.image_lookup.requests.get", return_value=search_resp):
        result = _search_wikipedia("Unknown Product XYZ")
    assert result is None


def test_search_wikipedia_returns_none_when_article_has_no_thumbnail():
    responses = _mock_wiki_responses(["Some Article"], None)
    with patch("app.image_lookup.requests.get", side_effect=responses):
        result = _search_wikipedia("Some Product")
    assert result is None


def test_search_wikipedia_returns_none_on_404_summary():
    search_resp = MagicMock()
    search_resp.json.return_value = ["query", ["Some Article"], [], []]

    summary_resp = MagicMock()
    summary_resp.status_code = 404
    summary_resp.raise_for_status.side_effect = None

    with patch("app.image_lookup.requests.get", side_effect=[search_resp, summary_resp]):
        result = _search_wikipedia("Some Product")
    assert result is None


def test_search_wikipedia_raises_on_network_error():
    with patch("app.image_lookup.requests.get", side_effect=Exception("timeout")):
        with pytest.raises(Exception):
            _search_wikipedia("Raffaello")


# ── DB helpers ────────────────────────────────────────────────────────────────

def test_get_deals_needing_images_returns_null_image_deals(app_with_imageless_deal):
    deals = get_deals_needing_images(app_with_imageless_deal)
    assert len(deals) == 1
    assert deals[0]["name"] == "Raffaello"
    assert deals[0]["brand"] == "Ferrero"


def test_get_deals_needing_images_excludes_deals_with_image(flask_app):
    save_deals(flask_app, [{
        "product_id": "p2", "name": "Chleb", "source": "web",
        "category": "Pieczywo", "price": 2.50,
        "image_url": "https://example.com/bread.jpg",
    }])
    assert all(d["product_id"] != "p2" for d in get_deals_needing_images(flask_app))


def test_update_deal_image_sets_url(app_with_imageless_deal):
    update_deal_image(app_with_imageless_deal, "p1", "Gazetka", "https://example.com/img.jpg")
    assert len(get_deals_needing_images(app_with_imageless_deal)) == 0


def test_get_image_cache_returns_none_on_miss(flask_app):
    assert get_image_cache(flask_app, "nonexistent key") is None


def test_image_cache_roundtrip(flask_app):
    set_image_cache(flask_app, "raffaello", "https://wiki.org/raffaello.jpg")
    cached = get_image_cache(flask_app, "raffaello")
    assert cached["image_url"] == "https://wiki.org/raffaello.jpg"
    assert "cached_at" in cached


def test_image_cache_stores_none_for_not_found(flask_app):
    set_image_cache(flask_app, "unknown xyz", None)
    assert get_image_cache(flask_app, "unknown xyz")["image_url"] is None


def test_image_cache_overwrites_on_duplicate_key(flask_app):
    set_image_cache(flask_app, "maslo", "https://example.com/old.jpg")
    set_image_cache(flask_app, "maslo", "https://example.com/new.jpg")
    assert get_image_cache(flask_app, "maslo")["image_url"] == "https://example.com/new.jpg"


# ── _run_lookup ───────────────────────────────────────────────────────────────

def test_run_lookup_fetches_and_updates_deal(app_with_imageless_deal):
    with patch("app.image_lookup._search_wikipedia", return_value="https://wiki.org/img.jpg") as mock_search:
        with patch("app.image_lookup.time.sleep"):
            _run_lookup(app_with_imageless_deal)
    mock_search.assert_called_once_with("Raffaello", "Ferrero")
    assert len(get_deals_needing_images(app_with_imageless_deal)) == 0


def test_run_lookup_sets_placeholder_when_not_found(app_with_imageless_deal):
    with patch("app.image_lookup._search_wikipedia", return_value=None):
        _run_lookup(app_with_imageless_deal)
    assert len(get_deals_needing_images(app_with_imageless_deal)) == 0


def test_run_lookup_uses_cached_url_without_calling_wikipedia(app_with_imageless_deal):
    set_image_cache(app_with_imageless_deal, "ferrero raffaello", "https://cached.com/img.jpg")
    with patch("app.image_lookup._search_wikipedia") as mock_search:
        _run_lookup(app_with_imageless_deal)
    mock_search.assert_not_called()
    assert len(get_deals_needing_images(app_with_imageless_deal)) == 0


def test_run_lookup_uses_placeholder_for_cached_not_found(app_with_imageless_deal):
    set_image_cache(app_with_imageless_deal, "ferrero raffaello", None)
    with patch("app.image_lookup._search_wikipedia") as mock_search:
        _run_lookup(app_with_imageless_deal)
    mock_search.assert_not_called()
    assert len(get_deals_needing_images(app_with_imageless_deal)) == 0


def test_run_lookup_skips_cache_and_update_on_error(app_with_imageless_deal):
    with patch("app.image_lookup._search_wikipedia", side_effect=Exception("timeout")):
        _run_lookup(app_with_imageless_deal)
    assert get_image_cache(app_with_imageless_deal, "ferrero raffaello") is None
    assert len(get_deals_needing_images(app_with_imageless_deal)) == 1


def test_run_lookup_skips_deals_without_name(flask_app):
    save_deals(flask_app, [{
        "product_id": "nameless", "name": None,
        "source": "leaflet", "category": "Gazetka", "price": 1.00,
    }])
    with patch("app.image_lookup._search_wikipedia") as mock_search:
        _run_lookup(flask_app)
    mock_search.assert_not_called()


def test_run_lookup_stores_cache_entry_after_lookup(app_with_imageless_deal):
    with patch("app.image_lookup._search_wikipedia", return_value="https://wiki.org/img.jpg"):
        _run_lookup(app_with_imageless_deal)
    cached = get_image_cache(app_with_imageless_deal, "ferrero raffaello")
    assert cached["image_url"] == "https://wiki.org/img.jpg"


# ── placeholder route ─────────────────────────────────────────────────────────

def test_placeholder_image_route_returns_svg(client):
    resp = client.get("/api/placeholder-image")
    assert resp.status_code == 200
    assert resp.content_type.startswith("image/svg+xml")
    assert b"<svg" in resp.data


def test_placeholder_image_route_is_cacheable(client):
    resp = client.get("/api/placeholder-image")
    assert "Cache-Control" in resp.headers
