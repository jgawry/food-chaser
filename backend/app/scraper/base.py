from abc import ABC, abstractmethod


class LeafletScraper(ABC):
    store_name: str  # class-level constant, set by each subclass

    @abstractmethod
    def parse_leaflet(self, pdf_path: str) -> list[dict]:
        """Parse a store leaflet PDF. Returns list of deal dicts compatible with save_deals()."""
        ...


class WebScraper(ABC):
    store_name: str  # class-level constant, set by each subclass

    @abstractmethod
    def scrape(self) -> list[dict]:
        """Scrape deals from store website. Returns list of deal dicts compatible with save_deals()."""
        ...
