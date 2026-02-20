"""
OpenAI News RSS fetcher.

Fetches recent posts from https://openai.com/news/rss.xml and filters
them by a configurable datetime cutoff.

Usage::

    from aggregator.fetchers.openai_news import fetch_openai_news
    from datetime import datetime, timezone, timedelta

    since = datetime.now(timezone.utc) - timedelta(days=1)
    entries = fetch_openai_news(since=since)
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from typing import Optional

import feedparser
from bs4 import BeautifulSoup
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_FEED_URL = "https://openai.com/news/rss.xml"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class OpenAINewsEntry(BaseModel):
    """A single post from the OpenAI News RSS feed."""

    post_id: str          # The post URL used as a stable identifier.
    title: str
    url: str
    published_at: datetime
    content: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_html(raw: str) -> str:
    """Remove HTML tags and normalise whitespace for LLM consumption."""
    text = BeautifulSoup(raw, "html.parser").get_text(separator=" ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _parse_pubdate(item: feedparser.FeedParserDict) -> datetime:
    """
    Return a timezone-aware UTC datetime for a feed item.

    Tries ``published_parsed`` (UTC ``time.struct_time`` from feedparser)
    first, then parses the raw ``published`` RFC-2822 string, then falls
    back to *now*.
    """
    raw_time = item.get("published_parsed")
    if raw_time is not None:
        return datetime(*raw_time[:6], tzinfo=timezone.utc)

    raw_str: str = item.get("published", "")
    if raw_str:
        try:
            return parsedate_to_datetime(raw_str).astimezone(timezone.utc)
        except Exception:
            pass

    logger.warning("Could not parse pubDate for OpenAI News item; using current time.")
    return datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_openai_news(since: Optional[datetime] = None) -> list[OpenAINewsEntry]:
    """
    Fetch recent posts from the OpenAI News RSS feed.

    The feed is assumed to be sorted **newest first**. Iteration stops as
    soon as an entry older than *since* is encountered, so only the head of
    the feed is ever processed.

    Args:
        since: Only return entries published *after* this UTC datetime.
               Pass ``None`` to return all entries in the feed.

    Returns:
        A list of :class:`OpenAINewsEntry` objects, ordered newest-first.
        Returns an empty list if the feed is unavailable or empty.
    """
    try:
        feed = feedparser.parse(_FEED_URL)
    except Exception as exc:
        logger.error("Unexpected error parsing OpenAI News RSS feed: %s", exc)
        return []

    if not feed.entries:
        logger.warning("OpenAI News RSS feed is empty or could not be fetched.")
        return []

    entries: list[OpenAINewsEntry] = []

    for item in feed.entries:
        url: str = item.get("link", "")
        title: str = item.get("title", "Untitled").strip()
        published_at: datetime = _parse_pubdate(item)

        # Stop early — RSS is newest-first, so everything from here is older.
        if since is not None and published_at <= since:
            break

        raw_content: str = item.get("summary", "") or ""
        content: Optional[str] = _strip_html(raw_content) if raw_content else None

        entries.append(
            OpenAINewsEntry(
                post_id=url,
                title=title,
                url=url,
                published_at=published_at,
                content=content,
            )
        )

    logger.info("Fetched %d OpenAI News entry/entries.", len(entries))
    return entries

if __name__ == "__main__":
    entries = fetch_openai_news(since=datetime.now(timezone.utc) - timedelta(days=1))
    if entries:
        print(entries[0].content)