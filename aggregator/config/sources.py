"""
Central source configuration for the AI News Aggregator.

This is the ONLY place where source URLs and channel identifiers
should be defined. Add new sources here — no other file needs
to change.
"""

# ---------------------------------------------------------------------------
# YouTube channels
# Accepts channel IDs (UCxxx...), @handles, or legacy usernames.
# ---------------------------------------------------------------------------

YOUTUBE_CHANNELS: list[str] = [
    "@Fireship"
]

# ---------------------------------------------------------------------------
# RSS news sources
# Each entry maps a human-readable name to its fetcher key and feed URL.
# The runner uses "fetcher" to dispatch to the correct fetch function.
# ---------------------------------------------------------------------------

RSS_SOURCES: list[dict] = [
    {
        "name": "openai_news",
        "url": "https://openai.com/news/rss.xml",
        "fetcher": "openai_news",
    },
]

# ---------------------------------------------------------------------------
# Newsletter / digest sources
# These fetchers always return the latest issue (no since= filtering).
# ---------------------------------------------------------------------------

NEWSLETTER_SOURCES: list[dict] = [
    {
        "name": "smol_ai",
        "url": "https://news.smol.ai/rss.xml",
        "fetcher": "smol_ai",
    },
]
