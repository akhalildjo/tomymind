from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


def utcnow() -> datetime:
    return datetime.now(UTC)


class BookmarkItem(BaseModel):
    """One bookmark discovered on a source. Stable shape across sources."""

    model_config = ConfigDict(populate_by_name=True)

    source_item_id: str = Field(alias="sourceItemId")
    url: HttpUrl
    suggested_tags: list[str] = Field(default_factory=list, alias="suggestedTags")
    raw_metadata: dict[str, Any] = Field(default_factory=dict, alias="rawMetadata")


class FetchResult(BaseModel):
    """Full output of one source fetch run. Serialized as JSON in output/."""

    model_config = ConfigDict(populate_by_name=True)

    source: str
    fetched_at: datetime = Field(default_factory=utcnow, alias="fetchedAt")
    item_count: int = Field(alias="itemCount")
    items: list[BookmarkItem]
