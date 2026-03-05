"""
Unit tests for the Lidl leaflet PDF parser.

All tests operate on pre-cleaned line lists (as would be passed to _parse_page)
or raw text strings (as would be passed to _parse_coupon_page), so no real PDF is needed.
"""
import pytest

from app.scraper.lidl_leaflet import (
    _is_noise,
    _is_brand,
    _try_parse_price_block,
    _collect_grouped_prices,
    _parse_page,
    _parse_coupon_page,
    _clean_lines,
)


# ── _is_noise ─────────────────────────────────────────────────────────────────

class TestIsNoise:
    def test_exact_match(self):
        assert _is_noise("Nowa cena")
        assert _is_noise("gratis")
        assert _is_noise("Supercena")
        assert _is_noise("regularna")

    def test_startswith_match(self):
        assert _is_noise("Limit: 2 szt.")
        assert _is_noise("Aktywuj kupon w aplikacji")
        assert _is_noise("Cena poza promocją: 4,99")
        assert _is_noise("Od czwartku, 6.03")

    def test_regex_match(self):
        assert _is_noise("42")          # digits only
        assert _is_noise("20% taniej")  # discount description
        assert _is_noise("3 x ")         # multiplier prefix
        assert _is_noise("100 g = 0,50") # unit price

    def test_clean_strings_pass(self):
        assert not _is_noise("MLEKOVITA")
        assert not _is_noise("Mleko UHT 3.2%")
        assert not _is_noise("1 L")
        assert not _is_noise("3,99")
        assert not _is_noise("-20%")
        assert not _is_noise("4,99*")


# ── _is_brand ─────────────────────────────────────────────────────────────────

class TestIsBrand:
    def test_all_uppercase(self):
        assert _is_brand("MLEKOVITA")
        assert _is_brand("LIDL")
        assert _is_brand("ACTIVIA")

    def test_uppercase_with_punctuation(self):
        assert _is_brand("DR. OETKER")   # dots don't count as alpha
        assert _is_brand("HOCHLAND")

    def test_mixed_case_rejected(self):
        assert not _is_brand("Mleko")
        assert not _is_brand("mleko uht")
        assert not _is_brand("Hochland")

    def test_too_short_rejected(self):
        assert not _is_brand("A")
        assert not _is_brand("")

    def test_mostly_digits_rejected(self):
        assert not _is_brand("1 L")
        assert not _is_brand("500 g")


# ── _try_parse_price_block ────────────────────────────────────────────────────

class TestTryParsePriceBlock:
    def test_format_price_then_compact(self):
        # "3,99" then "-20% 4,99*" on one line
        lines = ["3,99", "-20% 4,99*"]
        result = _try_parse_price_block(lines, 0)
        assert result == (20, 3.99, 4.99, 2)

    def test_format_price_then_old_star(self):
        # "3,99" then "4,99*" (no explicit discount)
        lines = ["3,99", "4,99*"]
        result = _try_parse_price_block(lines, 0)
        assert result == (None, 3.99, 4.99, 2)

    def test_format_discount_price_old_star(self):
        # "-20%" then "3,99" then "4,99*"
        lines = ["-20%", "3,99", "4,99*"]
        result = _try_parse_price_block(lines, 0)
        assert result == (20, 3.99, 4.99, 3)

    def test_no_match_returns_none(self):
        assert _try_parse_price_block(["Some text"], 0) is None
        assert _try_parse_price_block(["MLEKOVITA", "Mleko UHT"], 0) is None

    def test_out_of_bounds_returns_none(self):
        lines = ["3,99"]
        assert _try_parse_price_block(lines, 5) is None

    def test_incomplete_discount_format_returns_none(self):
        # "-20%" then "3,99" but no old price — format 3 incomplete
        lines = ["-20%", "3,99"]
        assert _try_parse_price_block(lines, 0) is None

    def test_offset_into_list(self):
        lines = ["IGNORE", "3,99", "4,99*"]
        result = _try_parse_price_block(lines, 1)
        assert result == (None, 3.99, 4.99, 3)


# ── _collect_grouped_prices ───────────────────────────────────────────────────

class TestCollectGroupedPrices:
    def test_two_discount_groups(self):
        lines = ["-20%", "-30%", "3,99", "5,99", "4,99*", "8,49*"]
        result, next_i = _collect_grouped_prices(lines, 0)
        assert result == [(20, 3.99, 4.99), (30, 5.99, 8.49)]
        assert next_i == 6

    def test_three_discount_groups(self):
        lines = ["-10%", "-20%", "-30%", "1,99", "3,99", "5,99", "2,19*", "4,99*", "8,49*"]
        result, next_i = _collect_grouped_prices(lines, 0)
        assert len(result) == 3
        assert result[0] == (10, 1.99, 2.19)
        assert next_i == 9

    def test_single_discount_not_grouped(self):
        # Only one discount line — not a grouped format
        lines = ["-20%", "3,99", "4,99*"]
        result, next_i = _collect_grouped_prices(lines, 0)
        assert result == []
        assert next_i == 0  # unchanged

    def test_missing_old_prices_not_grouped(self):
        lines = ["-20%", "-30%", "3,99", "5,99"]  # no old_price lines
        result, next_i = _collect_grouped_prices(lines, 0)
        assert result == []
        assert next_i == 0

    def test_offset_respected(self):
        lines = ["IGNORE", "-20%", "-30%", "3,99", "5,99", "4,99*", "8,49*"]
        result, next_i = _collect_grouped_prices(lines, 1)
        assert len(result) == 2
        assert next_i == 7


# ── _clean_lines ──────────────────────────────────────────────────────────────

class TestCleanLines:
    def test_filters_noise(self):
        text = "MLEKOVITA\nNowa cena\nMleko UHT\n42\n1 L\n"
        lines = _clean_lines(text)
        assert "Nowa cena" not in lines
        assert "42" not in lines
        assert "MLEKOVITA" in lines
        assert "Mleko UHT" in lines
        assert "1 L" in lines

    def test_strips_whitespace(self):
        text = "  MLEKOVITA  \n  Mleko UHT  \n"
        lines = _clean_lines(text)
        assert lines == ["MLEKOVITA", "Mleko UHT"]

    def test_replaces_nbsp(self):
        text = "3,99\xa0zł"
        lines = _clean_lines(text)
        assert lines == ["3,99 zł"]

    def test_empty_lines_skipped(self):
        text = "BRAND\n\n\nProduct\n"
        lines = _clean_lines(text)
        assert lines == ["BRAND", "Product"]


# ── _parse_page ───────────────────────────────────────────────────────────────

class TestParsePage:
    def test_basic_product_with_stara_price(self):
        # Typical Lidl layout: brand → description → qty → stara line → price + compact
        lines = [
            "MLEKOVITA",
            "Mleko UHT",
            "1 L",
            "* najniższa cena przed obniżką: 4,99",
            "3,99",
            "-20% 4,99*",
        ]
        result = _parse_page(lines)
        assert len(result) == 1
        p = result[0]
        assert p["brand"] == "MLEKOVITA"
        assert p["name"] == "Mleko UHT"
        assert p["qty"] == "1 L"
        assert p["new_price"] == pytest.approx(3.99)
        assert p["old_price"] == pytest.approx(4.99)
        assert p["discount_pct"] == 20

    def test_product_without_qty(self):
        lines = [
            "HOCHLAND",
            "Ser żółty",
            "* cena przed obniżką: 8,99",
            "5,99",
            "-33% 8,99*",
        ]
        result = _parse_page(lines)
        assert len(result) == 1
        p = result[0]
        assert p["brand"] == "HOCHLAND"
        assert p["name"] == "Ser żółty"
        assert p["qty"] == ""

    def test_multiple_products(self):
        lines = [
            "MLEKOVITA",
            "Mleko UHT",
            "1 L",
            "* cena przed: 4,99",
            "3,99",
            "-20% 4,99*",
            "ACTIVIA",
            "Jogurt naturalny",
            "150 g",
            "* stara cena przed obniżką: 2,49",
            "1,99",
            "-20% 2,49*",
        ]
        result = _parse_page(lines)
        assert len(result) == 2
        brands = {p["brand"] for p in result}
        assert brands == {"MLEKOVITA", "ACTIVIA"}

    def test_product_without_price_excluded(self):
        # A product with no price block should not appear in results
        lines = ["MLEKOVITA", "Mleko UHT", "1 L"]
        result = _parse_page(lines)
        assert result == []

    def test_empty_lines(self):
        assert _parse_page([]) == []


# ── _parse_coupon_page ────────────────────────────────────────────────────────

class TestParseCouponPage:
    def test_basic_coupon(self):
        # "2+2 gratis" format with brand, name, qty on separate lines
        text = (
            "ACTIVIA\n"
            "Jogurt pitny\n"
            "500 g\n"
            "Cena poza promocją: 3,99\n"
            "2,99\n"
            "2 + 2\n"
            "gratis\n"
        )
        result = _parse_coupon_page(text)
        assert len(result) == 1
        c = result[0]
        assert c["brand"] == "ACTIVIA"
        assert c["name"] == "Jogurt pitny"
        assert c["qty"] == "500 g"
        assert c["new_price"] == pytest.approx(2.99)
        assert c["buy_n"] == 2
        assert c["get_m"] == 2
        assert c["discount_pct"] == 50  # 2/(2+2)*100

    def test_one_plus_one_coupon(self):
        text = (
            "HOCHLAND\n"
            "Ser twarogowy\n"
            "200 g\n"
            "Cena poza promocją: 4,99\n"
            "3,99\n"
            "1 + 1\n"
        )
        result = _parse_coupon_page(text)
        assert len(result) == 1
        assert result[0]["buy_n"] == 1
        assert result[0]["get_m"] == 1
        assert result[0]["discount_pct"] == 50  # 1/(1+1)*100

    def test_no_coupon_anchor_returns_empty(self):
        text = "MLEKOVITA\nMleko UHT\n1 L\n3,99\n"
        result = _parse_coupon_page(text)
        assert result == []

    def test_incomplete_coupon_excluded(self):
        # Anchor present but no price/buy-get pattern
        text = "Cena poza promocją: 3,99\n"
        result = _parse_coupon_page(text)
        assert result == []  # name is empty → not included

    def test_empty_text(self):
        assert _parse_coupon_page("") == []
