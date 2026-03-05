from .base import LeafletScraper, WebScraper
from .lidl import LidlWebScraper
from .lidl_leaflet import LidlLeafletScraper

WEB_SCRAPERS: dict[str, WebScraper] = {
    'lidl': LidlWebScraper(),
}

LEAFLET_SCRAPERS: dict[str, LeafletScraper] = {
    'lidl': LidlLeafletScraper(),
}
