"""
Tests for the scraper registry and abstract base class contracts.
"""
from app.scraper import WEB_SCRAPERS, LEAFLET_SCRAPERS
from app.scraper.base import WebScraper, LeafletScraper
from app.scraper.lidl import LidlWebScraper
from app.scraper.lidl_leaflet import LidlLeafletScraper


class TestScraperRegistry:
    def test_lidl_in_web_scrapers(self):
        assert "lidl" in WEB_SCRAPERS

    def test_lidl_in_leaflet_scrapers(self):
        assert "lidl" in LEAFLET_SCRAPERS

    def test_web_scrapers_values_are_web_scraper_instances(self):
        for scraper in WEB_SCRAPERS.values():
            assert isinstance(scraper, WebScraper)

    def test_leaflet_scrapers_values_are_leaflet_scraper_instances(self):
        for scraper in LEAFLET_SCRAPERS.values():
            assert isinstance(scraper, LeafletScraper)


class TestLidlWebScraper:
    def test_store_name(self):
        assert LidlWebScraper.store_name == "Lidl"

    def test_implements_web_scraper(self):
        assert issubclass(LidlWebScraper, WebScraper)

    def test_has_scrape_method(self):
        assert callable(LidlWebScraper().scrape)


class TestLidlLeafletScraper:
    def test_store_name(self):
        assert LidlLeafletScraper.store_name == "Lidl"

    def test_implements_leaflet_scraper(self):
        assert issubclass(LidlLeafletScraper, LeafletScraper)

    def test_has_parse_leaflet_method(self):
        assert callable(LidlLeafletScraper().parse_leaflet)

    def test_parse_leaflet_nonexistent_file_returns_empty(self, tmp_path):
        # parse_leaflet on a missing file must return [] gracefully (handled in parse_leaflet)
        scraper = LidlLeafletScraper()
        result = scraper.parse_leaflet(str(tmp_path / "does_not_exist.pdf"))
        assert result == []
