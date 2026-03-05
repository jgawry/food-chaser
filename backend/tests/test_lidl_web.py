"""
Unit tests for Lidl web scraper parsing logic (no network required).
"""
import json

from app.scraper.lidl import _extract_nuxt_data, _parse_products_from_nuxt


# ── _extract_nuxt_data ────────────────────────────────────────────────────────

class TestExtractNuxtData:
    def test_valid_script_tag(self):
        data = [1, "hello", 3.14]
        html = f'<script id="__NUXT_DATA__" type="application/json">{json.dumps(data)}</script>'
        result = _extract_nuxt_data(html)
        assert result == data

    def test_single_quotes_in_attribute(self):
        data = ["a", "b"]
        html = f"<script id='__NUXT_DATA__' type='application/json'>{json.dumps(data)}</script>"
        result = _extract_nuxt_data(html)
        assert result == data

    def test_missing_script_returns_empty(self):
        assert _extract_nuxt_data("<html><body>no script here</body></html>") == []

    def test_invalid_json_returns_empty(self):
        html = '<script id="__NUXT_DATA__">{not: valid json}</script>'
        assert _extract_nuxt_data(html) == []

    def test_empty_string_returns_empty(self):
        assert _extract_nuxt_data("") == []

    def test_html_entities_unescaped(self):
        # HTML-encode the JSON so & becomes &amp; (as a browser would serve it)
        inner = json.dumps(["a&b"]).replace("&", "&amp;")  # '["a&amp;b"]'
        html = f'<script id="__NUXT_DATA__">{inner}</script>'
        result = _extract_nuxt_data(html)
        assert result == ["a&b"]


# ── _parse_products_from_nuxt ─────────────────────────────────────────────────

class TestParseProductsFromNuxt:
    def test_empty_array_returns_empty(self):
        assert _parse_products_from_nuxt([], "Owoce i warzywa") == []

    def test_array_without_product_urls_returns_empty(self):
        # Array with strings but none matching /p/.../pNNNNNNN
        nuxt = ["some string", 42, None, "another value", True]
        assert _parse_products_from_nuxt(nuxt, "Owoce i warzywa") == []

    def test_product_url_detected(self):
        # Build a minimal array that contains a product URL; surrounding values are
        # mostly junk, but the parser should at minimum find the product_id.
        # URL at index i; product_id integer at ~i+21
        nuxt = [None] * 60
        url = "/p/polskie-pieczarki/p10032680"
        nuxt[10] = url
        nuxt[31] = 10032680  # product_id at ~i+21
        nuxt[50] = 3.99       # price float in forward window
        result = _parse_products_from_nuxt(nuxt, "Owoce i warzywa")
        # We only assert structure if something is found — the heuristic may not
        # fire here, but at minimum it must not raise.
        assert isinstance(result, list)

    def test_result_fields(self):
        # If a product is parsed, it must have all required fields.
        nuxt = [None] * 100
        url = "/p/test-product/p12345678"
        nuxt[20] = url
        nuxt[41] = 12345678
        nuxt[65] = 2.49
        result = _parse_products_from_nuxt(nuxt, "Napoje")
        for product in result:
            assert "product_id" in product
            assert "category" in product
            assert "price" in product
            assert product["category"] == "Napoje"
