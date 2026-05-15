from ._base import BaseScraper
from .x import XScraper

_REGISTRY: dict[str, type[BaseScraper]] = {
    XScraper.name: XScraper,
}


def available_scrapers() -> list[str]:
    return sorted(_REGISTRY)


def get_scraper(name: str) -> BaseScraper:
    key = name.lower()
    if key not in _REGISTRY:
        raise ValueError(
            f"Unknown source '{name}'. Available: {', '.join(available_scrapers())}"
        )
    return _REGISTRY[key]()


__all__ = ["BaseScraper", "available_scrapers", "get_scraper"]
