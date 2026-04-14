import feedparser
import requests
import logging
import json
import os
from datetime import datetime, timezone
from config import RSS_FEEDS, ALPHA_VANTAGE_API_KEY, SEEN_ARTICLES_FILE, MAX_ARTICLES_PER_RUN

logger = logging.getLogger(__name__)


def _load_seen() -> set:
    if not os.path.exists(SEEN_ARTICLES_FILE):
        return set()
    try:
        with open(SEEN_ARTICLES_FILE) as f:
            data = json.load(f)
        return set(data.get("ids", []))
    except Exception:
        return set()


def _save_seen(seen: set):
    # Keep only the 2000 most recent to prevent unbounded growth
    ids = list(seen)[-2000:]
    with open(SEEN_ARTICLES_FILE, "w") as f:
        json.dump({"ids": ids}, f)


def _article_id(entry) -> str:
    return entry.get("id") or entry.get("link") or entry.get("title", "")


def fetch_rss_articles() -> list[dict]:
    seen = _load_seen()
    articles = []

    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                aid = _article_id(entry)
                if not aid or aid in seen:
                    continue

                published = entry.get("published", "") or entry.get("updated", "")
                summary = entry.get("summary", "") or entry.get("description", "")
                # Strip HTML tags from summary
                if "<" in summary:
                    import re
                    summary = re.sub(r"<[^>]+>", "", summary)

                articles.append({
                    "id": aid,
                    "title": entry.get("title", "").strip(),
                    "summary": summary[:500].strip(),
                    "source": feed.feed.get("title", feed_url),
                    "link": entry.get("link", ""),
                    "published": published,
                })
        except Exception as e:
            logger.warning(f"Failed to fetch RSS feed {feed_url}: {e}")

    logger.info(f"Fetched {len(articles)} new RSS articles")
    return articles[:MAX_ARTICLES_PER_RUN]


def fetch_alpha_vantage_news() -> list[dict]:
    if not ALPHA_VANTAGE_API_KEY:
        return []

    seen = _load_seen()
    url = (
        "https://www.alphavantage.co/query"
        "?function=NEWS_SENTIMENT"
        "&topics=financial_markets,earnings,ipo,mergers_and_acquisitions"
        f"&apikey={ALPHA_VANTAGE_API_KEY}"
        "&limit=50"
        "&sort=LATEST"
    )

    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning(f"Alpha Vantage news fetch failed: {e}")
        return []

    articles = []
    for item in data.get("feed", []):
        aid = item.get("url", "")
        if not aid or aid in seen:
            continue

        # Build ticker sentiment string for context
        ticker_sentiments = []
        for ts in item.get("ticker_sentiment", [])[:5]:
            ticker_sentiments.append(
                f"{ts['ticker']} ({ts['ticker_sentiment_label']}, score: {ts['ticker_sentiment_score']})"
            )

        summary = item.get("summary", "")[:500]
        if ticker_sentiments:
            summary += f" | Ticker sentiment: {', '.join(ticker_sentiments)}"

        articles.append({
            "id": aid,
            "title": item.get("title", ""),
            "summary": summary,
            "source": item.get("source", "Alpha Vantage"),
            "link": aid,
            "published": item.get("time_published", ""),
        })

    logger.info(f"Fetched {len(articles)} new Alpha Vantage articles")
    return articles


def fetch_all_news() -> list[dict]:
    articles = fetch_rss_articles() + fetch_alpha_vantage_news()
    # Deduplicate by id
    seen_ids = set()
    unique = []
    for a in articles:
        if a["id"] not in seen_ids:
            seen_ids.add(a["id"])
            unique.append(a)
    return unique[:MAX_ARTICLES_PER_RUN]


def mark_articles_seen(articles: list[dict]):
    seen = _load_seen()
    for a in articles:
        seen.add(a["id"])
    _save_seen(seen)
