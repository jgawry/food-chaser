"""
Integration tests for the REST API routes.

Scrapers and email are mocked — no network or SMTP required.
"""
import json
from unittest.mock import patch, MagicMock

import pytest

from app.db import save_deals


SAMPLE_DEALS = [
    {
        "product_id": "route-test-001",
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
]


# ── POST /api/scrape ──────────────────────────────────────────────────────────

class TestScrapeRoute:
    def test_scrape_all_stores(self, client, flask_app):
        with patch("app.scraper.lidl.scrape_all_categories", return_value=SAMPLE_DEALS):
            resp = client.post("/api/scrape")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["scraped"] == 1
        assert data["saved"] == 1

    def test_scrape_specific_store(self, client):
        with patch("app.scraper.lidl.scrape_all_categories", return_value=SAMPLE_DEALS):
            resp = client.post("/api/scrape?store=lidl")
        assert resp.status_code == 200

    def test_scrape_unknown_store_returns_400(self, client):
        resp = client.post("/api/scrape?store=unknown")
        assert resp.status_code == 400
        assert "Unknown store" in resp.get_json()["error"]

    def test_scrape_exception_returns_500(self, client):
        with patch("app.scraper.lidl.scrape_all_categories", side_effect=RuntimeError("network error")):
            resp = client.post("/api/scrape")
        assert resp.status_code == 500
        assert "error" in resp.get_json()


# ── POST /api/scrape/leaflet ──────────────────────────────────────────────────

class TestScrapeLeafletRoute:
    def test_missing_pdf_path_returns_400(self, client):
        resp = client.post("/api/scrape/leaflet", json={"store": "lidl"})
        assert resp.status_code == 400
        assert "pdf_path" in resp.get_json()["error"]

    def test_missing_store_returns_400(self, client, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF")
        resp = client.post("/api/scrape/leaflet", json={"pdf_path": str(pdf)})
        assert resp.status_code == 400
        assert "store" in resp.get_json()["error"]

    def test_unknown_store_returns_400(self, client, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF")
        resp = client.post("/api/scrape/leaflet", json={"pdf_path": str(pdf), "store": "makro"})
        assert resp.status_code == 400
        assert "Unknown store" in resp.get_json()["error"]

    def test_missing_file_returns_404(self, client):
        resp = client.post("/api/scrape/leaflet", json={
            "pdf_path": "/nonexistent/path/file.pdf",
            "store": "lidl",
        })
        assert resp.status_code == 404

    def test_successful_parse(self, client, tmp_path):
        pdf = tmp_path / "leaflet.pdf"
        pdf.write_bytes(b"%PDF")
        with patch("app.scraper.lidl_leaflet.parse_leaflet", return_value=SAMPLE_DEALS):
            resp = client.post("/api/scrape/leaflet", json={
                "pdf_path": str(pdf),
                "store": "lidl",
            })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["parsed"] == 1
        assert data["saved"] == 1


# ── GET /api/deals ────────────────────────────────────────────────────────────

class TestDealsRoute:
    def test_returns_all_deals(self, client, populated_db):
        resp = client.get("/api/deals")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] == 2
        assert len(data["deals"]) == 2

    def test_filter_by_category(self, client, populated_db):
        resp = client.get("/api/deals?category=Gazetka")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] == 1
        assert data["deals"][0]["category"] == "Gazetka"

    def test_empty_db_returns_empty(self, client, flask_app):
        resp = client.get("/api/deals")
        assert resp.status_code == 200
        assert resp.get_json() == {"deals": [], "count": 0}


# ── GET /api/deals/categories ─────────────────────────────────────────────────

class TestCategoriesRoute:
    def test_returns_categories(self, client, populated_db):
        resp = client.get("/api/deals/categories")
        assert resp.status_code == 200
        cats = resp.get_json()["categories"]
        assert "Gazetka" in cats
        assert "Kupon" in cats

    def test_empty_db_returns_empty(self, client, flask_app):
        resp = client.get("/api/deals/categories")
        assert resp.status_code == 200
        assert resp.get_json()["categories"] == []


# ── GET /api/deals/export/pdf ─────────────────────────────────────────────────

class TestExportPdfRoute:
    def test_returns_pdf_bytes(self, client, populated_db):
        resp = client.get("/api/deals/export/pdf")
        assert resp.status_code == 200
        assert resp.content_type == "application/pdf"
        assert resp.data[:4] == b"%PDF"

    def test_content_disposition_header(self, client, populated_db):
        resp = client.get("/api/deals/export/pdf")
        assert "attachment" in resp.headers["Content-Disposition"]
        assert "deals-all.pdf" in resp.headers["Content-Disposition"]

    def test_category_filter_in_filename(self, client, populated_db):
        resp = client.get("/api/deals/export/pdf?category=Gazetka")
        assert "deals-Gazetka.pdf" in resp.headers["Content-Disposition"]


# ── POST /api/deals/export/email ─────────────────────────────────────────────

class TestEmailRoute:
    def test_sends_email_successfully(self, client, populated_db):
        # Patch where the name is used (the routes module), not the source module
        with patch("app.routes.deals.send_deals_email") as mock_send:
            resp = client.post("/api/deals/export/email")
        assert resp.status_code == 200
        assert resp.get_json() == {"sent": True}
        mock_send.assert_called_once()

    def test_email_error_returns_500(self, client, populated_db):
        with patch("app.routes.deals.send_deals_email", side_effect=RuntimeError("SMTP failed")):
            resp = client.post("/api/deals/export/email")
        assert resp.status_code == 500
        assert "error" in resp.get_json()

    def test_category_param_passed_to_email(self, client, populated_db):
        with patch("app.routes.deals.send_deals_email") as mock_send:
            client.post("/api/deals/export/email?category=Gazetka")
        mock_send.assert_called_once()
        call_args = mock_send.call_args
        assert "Gazetka" in str(call_args)


# ── GET /api/health ───────────────────────────────────────────────────────────

class TestHealthRoute:
    def test_health_check(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.get_json() == {"status": "ok"}
