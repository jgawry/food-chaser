"""
Unit tests for the database layer (db.py).

Uses a real SQLite DB in a pytest tmp_path directory — no mocking needed.
"""
import pytest

from app.db import save_deals, get_deals, get_categories


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
