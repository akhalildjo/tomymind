"""Push scraped bookmarks into mymind via POST /objects.

Reads `output/<source>_bookmarks.json` produced by `tomymind scrape`,
skips IDs already in the local ledger `output/.pushed_<source>.json`,
sends the rest to mymind. The ledger is rewritten after every successful
POST so Ctrl+C is safe -- the next run resumes exactly where we stopped.

Cross-mymind dedup (URLs already in mymind from previous imports) is
NOT done client-side. The native server-side dedup (200 OK on duplicate
URL) is our safety net -- it costs the same credits as a real create
but at least never produces duplicate objects.
"""

from __future__ import annotations

import json
from pathlib import Path

from .errors import SessionError
from .models import ScrapeResult
from .mymind_client import DEFAULT_BASE_URL, MymindClient, MymindCreds


def load_ledger(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return set(json.loads(path.read_text(encoding="utf-8")))


def save_ledger(path: Path, ids: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(ids), indent=2), encoding="utf-8")


async def run_push(
    source: str,
    creds: MymindCreds,
    input_path: Path,
    ledger_path: Path,
    *,
    base_url: str | None = None,
) -> tuple[int, int, int]:
    """Push pending bookmarks. Returns (created, existed, failed) counts."""
    if not input_path.exists():
        raise SessionError(
            f"Aucun bookmark scrapé pour '{source}' à {input_path}. "
            f"Lance d'abord : tomymind scrape {source}"
        )

    result = ScrapeResult.model_validate_json(input_path.read_text(encoding="utf-8"))
    already_pushed = load_ledger(ledger_path)
    pending = [it for it in result.items if it.source_item_id not in already_pushed]

    print(
        f"  {len(result.items)} scrapés, {len(already_pushed)} déjà pushés, "
        f"{len(pending)} à envoyer."
    )
    if not pending:
        return 0, 0, 0

    created = existed = failed = 0
    async with MymindClient(creds, base_url=base_url or DEFAULT_BASE_URL) as client:
        for i, item in enumerate(pending, start=1):
            response = await client.create_object(
                url=str(item.url),
                tags=item.suggested_tags or [source],
            )

            if response.status == 201:
                created += 1
                tag = "NEW    "
            elif response.status == 200:
                existed += 1
                tag = "EXISTED"
            else:
                failed += 1
                tag = f"FAIL{response.status:3d}"

            line = f"  [{i:>4}/{len(pending)}] {tag} {item.url}"
            if response.detail and response.status not in (200, 201):
                line += f"  -- {response.detail[:80]}"
            print(line)

            if response.status in (200, 201):
                already_pushed.add(item.source_item_id)
                save_ledger(ledger_path, already_pushed)

    print(f"\n  Done. {created} créés, {existed} déjà chez mymind, {failed} échecs.")
    return created, existed, failed
