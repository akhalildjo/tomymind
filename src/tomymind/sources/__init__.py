from ._base import BaseSource
from .x import XSource

_REGISTRY: dict[str, type[BaseSource]] = {
    XSource.name: XSource,
}


def available_sources() -> list[str]:
    return sorted(_REGISTRY)


def get_source(name: str) -> BaseSource:
    key = name.lower()
    if key not in _REGISTRY:
        raise ValueError(f"Unknown source '{name}'. Available: {', '.join(available_sources())}")
    return _REGISTRY[key]()


__all__ = ["BaseSource", "available_sources", "get_source"]
