"""
Central runner for the AI News Aggregator.

Executes all configured fetchers, passes a shared cutoff datetime into
each one, and returns a single combined list of entries.

Usage::

    from aggregator.runner import run_all_fetchers

    entries = run_all_fetchers(hours=24)

Or from the command line::

    python -m aggregator.runner
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from aggregator.config.sources import (
    NEWSLETTER_SOURCES,
    RSS_SOURCES,
    YOUTUBE_CHANNELS,
)
from aggregator.fetchers.openai_news import fetch_openai_news
from aggregator.fetchers.smol_ai import fetch_latest_smol_ai_issue
from aggregator.fetchers.youtube import fetch_channel_videos

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fetcher dispatch tables
# Map the "fetcher" key in sources.py to the actual callable.
# Add new fetchers here when new modules are created.
# ---------------------------------------------------------------------------

_RSS_FETCHERS: dict[str, Any] = {
    "openai_news": fetch_openai_news,
}

_NEWSLETTER_FETCHERS: dict[str, Any] = {
    "smol_ai": fetch_latest_smol_ai_issue,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_all_fetchers(hours: int = 24) -> list[Any]:
    """
    Execute all configured fetchers and return a unified entry list.

    Each fetcher receives the cutoff datetime so filtering happens
    inside the fetcher — no bulk fetching followed by post-hoc trimming.

    Args:
        hours: Look-back window in hours. Only entries published within
               this window are included. Defaults to 24 hours.

    Returns:
        Combined list of all fetched entries (mixed Pydantic model types).
    """
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=hours)
    logger.info("Running all fetchers with cutoff=%s (last %d hours)", cutoff.isoformat(), hours)

    all_entries: list[Any] = []

    # --- YouTube ---
    for channel in YOUTUBE_CHANNELS:
        logger.info("Fetching YouTube channel: %s", channel)
        try:
            videos = fetch_channel_videos(channel, since=cutoff)
            logger.info("  → %d video(s) from '%s'", len(videos), channel)
            all_entries.extend(videos)
        except Exception as exc:
            logger.error("YouTube fetch failed for '%s': %s", channel, exc)

    # --- RSS sources ---
    for source in RSS_SOURCES:
        name = source["name"]
        fetcher_key = source["fetcher"]
        fetcher_fn = _RSS_FETCHERS.get(fetcher_key)

        if fetcher_fn is None:
            logger.warning("No RSS fetcher registered for key '%s' (source: %s)", fetcher_key, name)
            continue

        logger.info("Fetching RSS source: %s", name)
        try:
            entries = fetcher_fn(since=cutoff)
            logger.info("  → %d entry/entries from '%s'", len(entries), name)
            all_entries.extend(entries)
        except Exception as exc:
            logger.error("RSS fetch failed for '%s': %s", name, exc)

    # --- Newsletter / digest sources ---
    for source in NEWSLETTER_SOURCES:
        name = source["name"]
        fetcher_key = source["fetcher"]
        fetcher_fn = _NEWSLETTER_FETCHERS.get(fetcher_key)

        if fetcher_fn is None:
            logger.warning("No newsletter fetcher registered for key '%s' (source: %s)", fetcher_key, name)
            continue

        logger.info("Fetching newsletter: %s", name)
        try:
            # Newsletter fetchers always return the latest issue; no since= arg.
            entries = fetcher_fn()
            logger.info("  → %d entry/entries from '%s'", len(entries), name)
            all_entries.extend(entries)
        except Exception as exc:
            logger.error("Newsletter fetch failed for '%s': %s", name, exc)

    logger.info("Total entries collected: %d", len(all_entries))
    return all_entries


# ---------------------------------------------------------------------------
# CLI test block
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)

    entries = run_all_fetchers(hours=24)
    print(f"\n{'─' * 50}")
    print(f"Total entries: {len(entries)}")
    print(f"{'─' * 50}")
    for e in entries[:20]:
        print(e)
