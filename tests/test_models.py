from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from tomymind.models import BookmarkItem, FetchResult


class TestBookmarkItem:
    """Exercise the pydantic model end to end so a pydantic upgrade that
    changes alias handling, HttpUrl coercion/serialization or default-factory
    behaviour fails loudly here instead of silently corrupting the output JSON
    or the URLs pushed to mymind."""

    def test_construct_by_field_name(self) -> None:
        item = BookmarkItem(source_item_id="123", url="https://x.com/jack/status/123")
        assert item.source_item_id == "123"
        assert str(item.url) == "https://x.com/jack/status/123"
        # Mutable defaults must come from independent factories.
        assert item.suggested_tags == []
        assert item.raw_metadata == {}

    def test_construct_by_alias(self) -> None:
        item = BookmarkItem.model_validate(
            {
                "sourceItemId": "123",
                "url": "https://x.com/jack/status/123",
                "suggestedTags": ["x", "reading"],
                "rawMetadata": {"capturedFrom": "bookmarks"},
            }
        )
        assert item.source_item_id == "123"
        assert item.suggested_tags == ["x", "reading"]
        assert item.raw_metadata == {"capturedFrom": "bookmarks"}

    def test_dump_by_alias_is_camel_case(self) -> None:
        item = BookmarkItem(
            source_item_id="123",
            url="https://x.com/jack/status/123",
            suggested_tags=["x"],
            raw_metadata={"capturedFrom": "bookmarks"},
        )
        dumped = item.model_dump(by_alias=True)
        assert set(dumped) == {"sourceItemId", "url", "suggestedTags", "rawMetadata"}
        assert dumped["sourceItemId"] == "123"
        assert dumped["suggestedTags"] == ["x"]
        assert dumped["rawMetadata"] == {"capturedFrom": "bookmarks"}

    def test_httpurl_rejects_non_url(self) -> None:
        with pytest.raises(ValidationError):
            BookmarkItem(source_item_id="123", url="not-a-url")

    def test_httpurl_path_keeps_no_trailing_slash(self) -> None:
        # XSource builds canonical URLs as https://x.com/<user>/status/<id> and
        # both the output JSON and push.py rely on that exact string. pydantic's
        # HttpUrl must not append a trailing slash to a URL that already has a
        # path (a behaviour that has shifted between pydantic versions before).
        item = BookmarkItem(source_item_id="123", url="https://x.com/jack/status/123")
        assert str(item.url) == "https://x.com/jack/status/123"

    def test_json_roundtrip_preserves_fields(self) -> None:
        item = BookmarkItem(
            source_item_id="123",
            url="https://x.com/jack/status/123",
            suggested_tags=["x"],
            raw_metadata={"capturedFrom": "bookmarks"},
        )
        restored = BookmarkItem.model_validate_json(item.model_dump_json(by_alias=True))
        assert restored == item


class TestFetchResult:
    def test_dump_by_alias_shape(self) -> None:
        item = BookmarkItem(source_item_id="1", url="https://x.com/jack/status/1")
        result = FetchResult(source="x", item_count=1, items=[item])
        dumped = result.model_dump(by_alias=True)
        assert dumped["source"] == "x"
        assert dumped["itemCount"] == 1
        assert "fetchedAt" in dumped
        assert dumped["items"][0]["sourceItemId"] == "1"

    def test_fetched_at_defaults_to_aware_utc(self) -> None:
        result = FetchResult(source="x", item_count=0, items=[])
        assert result.fetched_at.tzinfo is not None
        assert result.fetched_at.utcoffset() == timedelta(0)
        # Sanity: the default is "now", not some epoch placeholder.
        assert abs((datetime.now(UTC) - result.fetched_at).total_seconds()) < 60

    def test_json_roundtrip(self) -> None:
        item = BookmarkItem(source_item_id="1", url="https://x.com/jack/status/1")
        result = FetchResult(source="x", item_count=1, items=[item])
        restored = FetchResult.model_validate_json(result.model_dump_json(by_alias=True))
        assert restored == result
