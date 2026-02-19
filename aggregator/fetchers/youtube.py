"""
YouTube channel fetcher.

Resolves a channel ID / username / @handle, fetches the latest videos via
the public RSS feed, and retrieves transcripts for each video.

Usage:
    from aggregator.fetchers.youtube import fetch_channel_videos
    from datetime import datetime, timezone, timedelta

    since = datetime.now(tz=timezone.utc) - timedelta(hours=24)
    videos = fetch_channel_videos("@OpenAIDevs", since=since)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

import feedparser
import httpx
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class VideoEntry:
    """Structured representation of a single YouTube video."""

    video_id: str
    title: str
    url: str
    published_at: datetime
    description: Optional[str] = None
    transcript: Optional[str] = None


# ---------------------------------------------------------------------------
# Channel resolution
# ---------------------------------------------------------------------------

# A YouTube channel ID always starts with "UC" and is 24 characters total.
_CHANNEL_ID_RE = re.compile(r"^UC[\w-]{22}$")

_RSS_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AINewsAggregator/1.0)"}


def resolve_channel_id(channel_input: str) -> str:
    """
    Accept a channel ID (UCxxx...), a legacy username, or a handle (@name)
    and return a normalised 24-character channel ID.

    Raises:
        ValueError: If the input cannot be resolved to a valid channel ID.
    """
    channel_input = channel_input.strip()

    # 1. Already a valid channel ID — return immediately.
    if _CHANNEL_ID_RE.match(channel_input):
        return channel_input

    # 2. Handle (@name) or bare username → build the canonical YouTube URL.
    if channel_input.startswith("@"):
        url = f"https://www.youtube.com/{channel_input}"
    else:
        url = f"https://www.youtube.com/@{channel_input}"

    return _scrape_channel_id(url)


def _scrape_channel_id(page_url: str) -> str:
    """
    Fetch a YouTube channel page and extract the channel ID from the HTML.

    YouTube embeds the channel ID in a canonical <link> tag:
        <link rel="canonical" href="https://www.youtube.com/channel/UCxxx...">

    Raises:
        ValueError: If the page cannot be fetched or the ID cannot be found.
    """
    try:
        response = httpx.get(
            page_url,
            follow_redirects=True,
            headers=_HEADERS,
            timeout=10,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise ValueError(
            f"Channel page returned HTTP {exc.response.status_code}: {page_url}"
        ) from exc
    except httpx.RequestError as exc:
        raise ValueError(
            f"Network error while fetching channel page '{page_url}': {exc}"
        ) from exc

    match = re.search(r"youtube\.com/channel/(UC[\w-]{22})", response.text)
    if match:
        return match.group(1)

    raise ValueError(
        f"Could not extract a channel ID from '{page_url}'. "
        "Check that the handle or username is correct."
    )


# ---------------------------------------------------------------------------
# RSS feed — video listing
# ---------------------------------------------------------------------------

def fetch_videos(
    channel_id: str,
    since: Optional[datetime] = None,
    max_results: int = 50,
) -> list[VideoEntry]:
    """
    Fetch recent videos from a channel's public RSS feed.

    Args:
        channel_id: A resolved YouTube channel ID (UCxxx...).
        since:      Only return videos published *after* this UTC datetime.
                    Pass ``None`` to return all entries in the feed (≤ 15).
        max_results: Hard cap on the number of returned videos.

    Returns:
        A list of :class:`VideoEntry` objects, sorted newest-first.

    Raises:
        RuntimeError: If the feed cannot be parsed or returns no entries.
    """
    rss_url = _RSS_URL.format(channel_id=channel_id)

    try:
        feed = feedparser.parse(rss_url)
    except Exception as exc:
        raise RuntimeError(
            f"Unexpected error parsing RSS feed for '{channel_id}': {exc}"
        ) from exc

    if feed.bozo and not feed.entries:
        raise RuntimeError(
            f"RSS feed for channel '{channel_id}' is malformed or empty. "
            f"bozo_exception: {feed.get('bozo_exception')}"
        )

    entries: list[VideoEntry] = []

    for item in feed.entries[:max_results]:
        video_id: str = item.get("yt_videoid", "")
        title: str = item.get("title", "Untitled")
        url: str = item.get("link", f"https://www.youtube.com/watch?v={video_id}")

        # feedparser returns a time.struct_time in UTC via `published_parsed`.
        raw_time = item.get("published_parsed")
        published_at = (
            datetime(*raw_time[:6], tzinfo=timezone.utc)
            if raw_time
            else datetime.now(tz=timezone.utc)
        )

        # Apply time-window filter.
        if since is not None and published_at <= since:
            continue

        # Description: prefer media:group summary, fall back to entry summary.
        raw_description = (
            item.get("media_description")
            or item.get("summary", "")
            or ""
        )
        description = raw_description.strip() or None

        entries.append(
            VideoEntry(
                video_id=video_id,
                title=title,
                url=url,
                published_at=published_at,
                description=description,
            )
        )

    return entries


# ---------------------------------------------------------------------------
# Transcript retrieval
# ---------------------------------------------------------------------------

def get_transcript(video_id: str) -> Optional[str]:
    """
    Retrieve the transcript for a YouTube video as a clean English plain-text string.

    Only English transcripts are considered (manually created or auto-generated).
    If no English transcript exists, returns ``None`` without translation or fallback.

    Args:
        video_id: The 11-character YouTube video ID.

    Returns:
        Full transcript as a single clean English plain-text string, or ``None``.
    """
    ytt_api = YouTubeTranscriptApi()

    try:
        snippets = ytt_api.fetch(video_id, languages=["en"])
    except NoTranscriptFound:
        logger.warning("No English transcript found for video '%s'.", video_id)
        return None
    except TranscriptsDisabled:
        logger.warning("Transcripts are disabled for video '%s'.", video_id)
        return None
    except VideoUnavailable:
        logger.warning("Video '%s' is unavailable.", video_id)
        return None
    except Exception as exc:
        logger.warning("Could not fetch transcript for '%s': %s", video_id, exc)
        return None

    # Assemble a clean plain-text string from snippet objects.
    # FetchedTranscriptSnippet exposes .text as an attribute in v1.x.
    parts: list[str] = []
    for snippet in snippets:
        text = getattr(snippet, "text", None) or ""
        text = text.strip()
        if text:
            parts.append(text)

    return " ".join(parts) or None

# ---------------------------------------------------------------------------
# High-level public API
# ---------------------------------------------------------------------------

def fetch_channel_videos(
    channel_input: str,
    since: Optional[datetime] = None,
    include_transcripts: bool = True,
    max_results: int = 50,
) -> list[VideoEntry]:
    """
    Resolve a channel and return its recent videos with optional transcripts.

    This is the main entry point for the YouTube fetcher.

    Args:
        channel_input:        Channel ID (``UCxxx...``), legacy username, or
                              handle (``@name``).
        since:                Only include videos published after this UTC
                              datetime. Defaults to returning all feed entries.
        include_transcripts:  Fetch and attach transcripts to each video.
        transcript_languages: Preferred transcript language codes.
        max_results:          Maximum number of videos to return.

    Returns:
        A list of :class:`VideoEntry` objects, newest-first.
    """
    channel_id = resolve_channel_id(channel_input)
    logger.info("Resolved '%s' → channel_id=%s", channel_input, channel_id)

    videos = fetch_videos(channel_id, since=since, max_results=max_results)
    logger.info("Found %d video(s) in channel %s", len(videos), channel_id)

    if include_transcripts:
        for video in videos:
            video.transcript = get_transcript(
                video.video_id
            )
            if video.transcript:
                logger.debug(
                    "Transcript: %s", video.video_id
                )
            else:
                logger.debug("No transcript: %s", video.video_id)

    return videos


if __name__ == "__main__":
    '''since = datetime.now(tz=timezone.utc) - timedelta(days=20)
    videos = fetch_channel_videos("hibabenzahra496", since=since)
    for video in videos:
        print(video)

    idchannel = resolve_channel_id('hibabenzahra496');
    print(idchannel);

    print(get_transcript('G2Ec3h5CfA8'))'''
    videos = fetch_channel_videos('Fireship', since=datetime.now(tz=timezone.utc) - timedelta(days=17))
    for video in videos: 
        print(video)