"""
Unit tests for the database layer (db.py).

Uses a real SQLite DB in a pytest tmp_path directory — no mocking needed.
"""
import pytest

from app.db import save_deals, get_deals, get_categories, upsert_product_images, fill_images_from_db


class TestSaveDeals:
    def test_returns_count(self, flask_app, sample_deal):
        saved = save_deals(flask_app, [sample_deal])
        assert saved == 1

    def test_empty_list_returns_zero(self, flask_app):
        assert save_deals(flask_app, []) == 0

    def test_multiple_deals(self, flask_app, sample_deal):
        deal2 = {**sample_deal, "product_id": "test-002"}
        saved = save_deals(flask_app, [sample_deal, deal2])
        assert saved == 2

    def test_upsert_replaces_existing(self, flask_app, sample_deal):
        save_deals(flask_app, [sample_deal])
        updated = {**sample_deal, "price": 2.49}
        save_deals(flask_app, [updated])
        deals = get_deals(flask_app)
        assert len(deals) == 1
        assert deals[0]["price"] == pytest.approx(2.49)

    def test_different_category_same_product_id_is_separate_row(self, flask_app, sample_deal):
        deal2 = {**sample_deal, "category": "Kupon"}
        saved = save_deals(flask_app, [sample_deal, deal2])
        assert saved == 2
        assert len(get_deals(flask_app)) == 2

    def test_optional_fields_can_be_none(self, flask_app):
        minimal = {
            "product_id": "min-001",
            "category": "Gazetka",
            "price": 1.99,
            "source": "web",
        }
        assert save_deals(flask_app, [minimal]) == 1
        deals = get_deals(flask_app)
        assert deals[0]["brand"] is None
        assert deals[0]["qty"] is None
        assert deals[0]["old_price"] is None

    def test_remove_stale_deletes_old_deals_same_source(self, flask_app, sample_deal):
        """Deals from the same source not in the new batch should be removed."""
        old_deal = {**sample_deal, "product_id": "old-001", "source": "web"}
        save_deals(flask_app, [old_deal])
        assert len(get_deals(flask_app)) == 1

        new_deal = {**sample_deal, "product_id": "new-001", "source": "web"}
        save_deals(flask_app, [new_deal], remove_stale=True)
        deals = get_deals(flask_app)
        assert len(deals) == 1
        assert deals[0]["product_id"] == "new-001"

    def test_remove_stale_preserves_other_sources(self, flask_app, sample_deal):
        """Stale removal only affects sources present in the new batch."""
        leaflet_deal = {**sample_deal, "product_id": "leaf-001", "source": "leaflet"}
        save_deals(flask_app, [leaflet_deal])

        web_deal = {**sample_deal, "product_id": "web-001", "source": "web"}
        save_deals(flask_app, [web_deal], remove_stale=True)
        deals = get_deals(flask_app)
        ids = {d["product_id"] for d in deals}
        assert "leaf-001" in ids
        assert "web-001" in ids

    def test_remove_stale_false_keeps_old_deals(self, flask_app, sample_deal):
        """Default behavior (remove_stale=False) should keep old deals."""
        old_deal = {**sample_deal, "product_id": "old-001", "source": "web"}
        save_deals(flask_app, [old_deal])

        new_deal = {**sample_deal, "product_id": "new-001", "source": "web"}
        save_deals(flask_app, [new_deal], remove_stale=False)
        assert len(get_deals(flask_app)) == 2


class TestGetDeals:
    def test_returns_all_deals(self, populated_db):
        deals = get_deals(populated_db)
        assert len(deals) == 2

    def test_filter_by_category(self, populated_db):
        deals = get_deals(populated_db, "Gazetka")
        assert len(deals) == 1
        assert deals[0]["category"] == "Gazetka"

    def test_filter_nonexistent_category_returns_empty(self, populated_db):
        assert get_deals(populated_db, "DoesNotExist") == []

    def test_sorted_by_discount_desc(self, flask_app, sample_deal):
        low = {**sample_deal, "product_id": "low", "discount_pct": 10}
        high = {**sample_deal, "product_id": "high", "discount_pct": 50}
        no_disc = {**sample_deal, "product_id": "nodis", "discount_pct": None}
        save_deals(flask_app, [low, high, no_disc])
        deals = get_deals(flask_app)
        discounts = [d["discount_pct"] for d in deals]
        assert discounts[0] == 50
        assert discounts[1] == 10
        assert discounts[2] is None  # NULLs last

    def test_returns_list_of_dicts(self, populated_db):
        deals = get_deals(populated_db)
        assert all(isinstance(d, dict) for d in deals)

    def test_empty_db_returns_empty(self, flask_app):
        assert get_deals(flask_app) == []


class TestGetCategories:
    def test_returns_distinct_categories(self, populated_db):
        cats = get_categories(populated_db)
        assert sorted(cats) == ["Gazetka", "Kupon"]

    def test_returns_sorted(self, flask_app, sample_deal):
        for cat in ["Warzywa", "Nabiał", "Gazetka"]:
            save_deals(flask_app, [{**sample_deal, "product_id": cat, "category": cat}])
        cats = get_categories(flask_app)
        assert cats == sorted(cats)

    def test_empty_db_returns_empty(self, flask_app):
        assert get_categories(flask_app) == []

    def test_multiple_deals_same_category_counted_once(self, flask_app, sample_deal):
        deal2 = {**sample_deal, "product_id": "test-002"}
        save_deals(flask_app, [sample_deal, deal2])
        cats = get_categories(flask_app)
        assert cats.count("Gazetka") == 1


class TestProductImageDb:
    """Tests for the product_images lookup table and image-preservation upsert."""

    WEB_DEAL = {
        "product_id": "web-001",
        "name": "Raffaello",
        "category": "Słodycze",
        "price": 9.99,
        "source": "web",
        "image_url": "https://example.com/raffaello.jpg",
    }
    LEAFLET_DEAL = {
        "product_id": "leaf-001",
        "name": "Raffaello",
        "category": "Gazetka",
        "price": 8.99,
        "source": "leaflet",
        "image_url": None,
    }

    def test_upsert_product_images_stores_entries(self, flask_app):
        count = upsert_product_images(flask_app, [self.WEB_DEAL])
        assert count == 1

    def test_upsert_product_images_skips_missing_image(self, flask_app):
        count = upsert_product_images(flask_app, [self.LEAFLET_DEAL])
        assert count == 0

    def test_fill_images_from_db_matches_by_name(self, flask_app):
        upsert_product_images(flask_app, [self.WEB_DEAL])
        deals = [{**self.LEAFLET_DEAL}]
        filled = fill_images_from_db(flask_app, deals)
        assert filled == 1
        assert deals[0]["image_url"] == self.WEB_DEAL["image_url"]

    def test_fill_images_case_insensitive(self, flask_app):
        upsert_product_images(flask_app, [{**self.WEB_DEAL, "name": "RAFFAELLO"}])
        deals = [{**self.LEAFLET_DEAL, "name": "raffaello"}]
        fill_images_from_db(flask_app, deals)
        assert deals[0]["image_url"] == self.WEB_DEAL["image_url"]

    def test_fill_images_no_match_leaves_none(self, flask_app):
        deals = [{**self.LEAFLET_DEAL}]
        fill_images_from_db(flask_app, deals)
        assert deals[0]["image_url"] is None

    def test_fill_images_skips_deals_already_having_image(self, flask_app):
        upsert_product_images(flask_app, [self.WEB_DEAL])
        deals = [{**self.LEAFLET_DEAL, "image_url": "https://existing.com/img.jpg"}]
        filled = fill_images_from_db(flask_app, deals)
        assert filled == 0
        assert deals[0]["image_url"] == "https://existing.com/img.jpg"

    def test_save_deals_preserves_image_on_re_scrape(self, flask_app):
        """Re-scraping a leaflet deal must not wipe an image set from the web scraper."""
        web_deal = {**self.WEB_DEAL}
        save_deals(flask_app, [web_deal])

        # Simulate re-scraping same product with no image
        no_image = {**self.WEB_DEAL, "image_url": None, "price": 11.99}
        save_deals(flask_app, [no_image])

        deals = get_deals(flask_app)
        assert len(deals) == 1
        assert deals[0]["image_url"] == self.WEB_DEAL["image_url"]
        assert deals[0]["price"] == pytest.approx(11.99)
