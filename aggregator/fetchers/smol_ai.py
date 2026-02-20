"""
Smol AI news digest fetcher.

Reads the daily digest from https://news.smol.ai/rss.xml and returns
the FIRST (most recent) item as a single :class:`SmolAIEntry`.

Usage::

    from aggregator.fetchers.smol_ai import fetch_latest_smol_ai_issue

    entries = fetch_latest_smol_ai_issue()
    if entries:
        print(entries[0].content)
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

import feedparser
from bs4 import BeautifulSoup
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_FEED_URL = "https://news.smol.ai/rss.xml"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class SmolAIEntry(BaseModel):
    """A single daily issue from the Smol AI news digest."""

    post_id: str          # The issue URL used as a stable identifier.
    title: str
    url: str
    published_at: datetime
    content: Optional[str] = None


# ---------------------------------------------------------------------------
# HTML cleaning
# ---------------------------------------------------------------------------

def _strip_html(raw: str) -> str:
    """
    Remove HTML tags from *raw* and return normalised plain text.

    Uses BeautifulSoup to handle malformed markup gracefully, then
    collapses runs of whitespace so the result is LLM-friendly.
    """
    text = BeautifulSoup(raw, "html.parser").get_text(separator=" ")
    # Collapse multiple spaces / newlines into a single space.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

def _parse_pubdate(item: feedparser.FeedParserDict) -> datetime:
    """
    Return a timezone-aware UTC datetime for the feed item.

    Tries ``published_parsed`` (a ``time.struct_time`` in UTC produced by
    feedparser) first, then falls back to parsing the raw ``published``
    string, then falls back to *now*.
    """
    raw_time = item.get("published_parsed")
    if raw_time is not None:
        return datetime(*raw_time[:6], tzinfo=timezone.utc)

    raw_str: str = item.get("published", "")
    if raw_str:
        try:
            dt = parsedate_to_datetime(raw_str)
            return dt.astimezone(timezone.utc)
        except Exception:
            pass

    logger.warning("Could not parse pubDate for Smol AI item; using current time.")
    return datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_latest_smol_ai_issue() -> list[SmolAIEntry]:
    """
    Fetch the most recent daily digest from Smol AI.

    Parses the RSS feed and reads **only the first item** (the latest issue).

    Returns:
        A list containing one :class:`SmolAIEntry`, or an empty list if the
        feed is unavailable or contains no items.
    """
    try:
        feed = feedparser.parse(_FEED_URL)
    except Exception as exc:
        logger.error("Unexpected error parsing Smol AI RSS feed: %s", exc)
        return []

    if not feed.entries:
        logger.warning("Smol AI RSS feed is empty or could not be fetched.")
        return []

    # Only process the first (most recent) item.
    item = feed.entries[0]

    url: str = item.get("link", "")
    title: str = item.get("title", "Untitled")
    published_at: datetime = _parse_pubdate(item)

    # Content priority: content:encoded → description → None.
    raw_content: str = ""
    content_list = item.get("content", [])
    if content_list:
        # feedparser surfaces <content:encoded> as entries[n].content[0].value
        raw_content = content_list[0].get("value", "")

    if not raw_content:
        raw_content = item.get("summary", "") or ""

    content: Optional[str] = _strip_html(raw_content) if raw_content else None

    entry = SmolAIEntry(
        post_id=url,
        title=title,
        url=url,
        published_at=published_at,
        content=content,
    )

    logger.info(
        "Fetched Smol AI issue: '%s' published at %s (%d chars of content)",
        title,
        published_at.date(),
        len(content) if content else 0,
    )

    return [entry]

if __name__ == "__main__":
    entries = fetch_latest_smol_ai_issue()
    if entries and entries[0].content:
        lines = entries[0].content.splitlines()
        print("\n".join(lines[:50]))