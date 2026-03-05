import pytest

from app import create_app
from app.db import init_db, save_deals


@pytest.fixture
def flask_app(tmp_path):
    app = create_app(instance_path=str(tmp_path))
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(flask_app):
    return flask_app.test_client()


@pytest.fixture
def sample_deal():
    return {
        "product_id": "test-product-001",
        "name": "Mleko UHT",
        "brand": "MLEKOVITA",
        "qty": "1 L",
        "source": "leaflet",
        "category": "Gazetka",
        "price": 3.99,
        "old_price": 4.99,
        "discount_pct": 20,
        "promo_label": None,
        "image_url": None,
        "product_url": None,
    }


@pytest.fixture
def populated_db(flask_app, sample_deal):
    """Flask app with two deals pre-inserted."""
    deal2 = {**sample_deal, "product_id": "test-product-002", "category": "Kupon", "discount_pct": 50}
    save_deals(flask_app, [sample_deal, deal2])
    return flask_app
