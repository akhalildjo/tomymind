"""Placeholder entry point for the mymind-importer service.

Kept intentionally inert until PR #2 wires the NATS consumer in. The
container stays alive so `docker compose up importer` can be validated
end-to-end (build, signal handling, healthchecks) before any business
logic exists.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    log = logging.getLogger("mymind_importer")
    log.info("mymind-importer placeholder running (no business logic yet)")
    asyncio.run(_park(log))


async def _park(log: logging.Logger) -> None:
    stop = asyncio.Event()
    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
    except (NotImplementedError, ValueError):
        # Signal handlers via the event loop aren't available on Windows /
        # non-main threads. The container only runs on Linux so this branch
        # is a safety net for local imports during tests.
        pass
    log.info("waiting for SIGINT/SIGTERM; NATS consumer arrives in a follow-up PR")
    await stop.wait()
    log.info("shutdown signal received, exiting")


if __name__ == "__main__":
    main()
