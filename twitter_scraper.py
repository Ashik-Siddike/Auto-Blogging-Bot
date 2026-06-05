"""
twitter_scraper.py  —  Twitter/X Influencer Tweet Scraper (API-Free)
=====================================================================
Nitter RSS feeds ব্যবহার করে Twitter/X-এর পোস্ট বিনামূল্যে স্ক্র্যাপ করে।
কোনো Twitter API key লাগবে না।

Features:
  • Multiple Nitter instances with fallback
  • Last 24h / 48h filtering
  • Engagement metrics parsing
  • Deduplication support
"""

import feedparser
import requests
import re
import time
import random
from datetime import datetime, timezone, timedelta
from typing import Optional
import html

# ── Nitter Public Instances (Fallback chain) ─────────────────────────────────
# These are public Nitter mirrors — if one fails, we try the next
NITTER_INSTANCES = [
    "https://nitter.poast.org",
    "https://nitter.privacydev.net",
    "https://nitter.cz",
    "https://nitter.1d4.us",
    "https://nitter.kavin.rocks",
    "https://lightbrd.com",
    "https://nitter.net",
]

REQUEST_TIMEOUT = 12  # seconds per request
MAX_TWEETS_PER_HANDLE = 15  # Max tweets to fetch per handle per cycle
DEFAULT_LOOKBACK_HOURS = 48  # Look back 48 hours for fresh content


def _clean_tweet_text(raw_text: str) -> str:
    """Cleans raw tweet text by removing HTML, URLs, and extra whitespace."""
    # Unescape HTML entities
    text = html.unescape(raw_text)
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Remove Twitter URLs (t.co links)
    text = re.sub(r'https://t\.co/\S+', '', text)
    # Remove RT prefixes
    text = re.sub(r'^RT @\w+:', '', text).strip()
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _parse_tweet_date(date_str: str) -> Optional[datetime]:
    """Parses various date formats from Nitter RSS feeds."""
    formats = [
        "%a, %d %b %Y %H:%M:%S %Z",
        "%a, %d %b %Y %H:%M:%S +0000",
        "%Y-%m-%dT%H:%M:%S%z",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def _extract_tweet_id_from_url(link: str) -> str:
    """Extracts tweet ID from a Nitter/Twitter URL."""
    match = re.search(r'/status/(\d+)', link)
    if match:
        return match.group(1)
    return link  # fallback to URL itself


def _fetch_nitter_rss(handle: str, instance: str) -> Optional[list]:
    """
    Fetches tweets from a single Nitter instance for a given handle.
    Returns list of raw feed entries, or None on failure.
    """
    # Clean handle (remove @ if present)
    handle = handle.lstrip('@').strip()
    url = f"{instance.rstrip('/')}/{handle}/rss"

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; RSSBot/1.0)',
            'Accept': 'application/rss+xml, application/xml, text/xml',
        }
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)

        if resp.status_code == 200 and resp.content:
            feed = feedparser.parse(resp.content)
            if feed.entries:
                print(f"    [NITTER] ✅ {instance} → {len(feed.entries)} tweets for @{handle}")
                return feed.entries
            else:
                print(f"    [NITTER] ⚠️  {instance} → Empty feed for @{handle}")
                return None
        else:
            print(f"    [NITTER] ❌ {instance} → HTTP {resp.status_code}")
            return None

    except requests.exceptions.Timeout:
        print(f"    [NITTER] ⏱️  {instance} → Timeout")
        return None
    except Exception as e:
        print(f"    [NITTER] ❌ {instance} → Error: {e}")
        return None


def scrape_tweets(
    handle: str,
    max_tweets: int = MAX_TWEETS_PER_HANDLE,
    lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
    processed_ids: set = None,
) -> list[dict]:
    """
    Scrapes latest tweets from a Twitter/X handle using Nitter RSS.

    Args:
        handle         : Twitter handle (e.g., "@sama" or "sama")
        max_tweets     : Maximum tweets to return
        lookback_hours : Only return tweets from last N hours
        processed_ids  : Set of already-processed tweet IDs to skip

    Returns:
        List of tweet dicts:
        {
            'id': str, 'text': str, 'author': str,
            'url': str, 'timestamp': datetime,
            'likes': int, 'retweets': int,
            'is_retweet': bool
        }
    """
    if processed_ids is None:
        processed_ids = set()

    handle_clean = handle.lstrip('@').strip()
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    print(f"  [SCRAPE] Fetching tweets for @{handle_clean} (last {lookback_hours}h)...")

    entries = None
    instances_to_try = NITTER_INSTANCES.copy()
    random.shuffle(instances_to_try)  # Randomize to distribute load

    for instance in instances_to_try:
        entries = _fetch_nitter_rss(handle_clean, instance)
        if entries:
            break
        time.sleep(0.5)  # Brief pause between instance attempts

    if not entries:
        print(f"  [SCRAPE] ❌ All Nitter instances failed for @{handle_clean}")
        return []

    tweets = []
    for entry in entries:
        if len(tweets) >= max_tweets:
            break

        try:
            # Parse tweet text
            raw_text = entry.get('summary', '') or entry.get('title', '')
            text = _clean_tweet_text(raw_text)

            # Skip empty tweets
            if not text or len(text) < 20:
                continue

            # Skip retweets (they're not original content for blogging)
            is_retweet = text.startswith('RT ') or 'RT @' in raw_text[:50]
            if is_retweet:
                continue

            # Parse URL and tweet ID
            link = entry.get('link', '')
            # Convert Nitter URL to real Twitter URL
            tweet_url = re.sub(r'https?://[^/]+/', 'https://twitter.com/', link)
            tweet_id = _extract_tweet_id_from_url(link)

            # Skip already processed
            if tweet_id in processed_ids:
                continue

            # Parse date
            date_str = entry.get('published', '') or entry.get('updated', '')
            tweet_time = _parse_tweet_date(date_str) if date_str else None

            # Filter by time window
            if tweet_time and tweet_time < cutoff_time:
                continue

            # Parse engagement (Nitter puts likes/RT in the summary HTML)
            likes = 0
            retweets = 0
            likes_match = re.search(r'(\d+)\s*likes?', raw_text, re.IGNORECASE)
            rt_match = re.search(r'(\d+)\s*retweets?', raw_text, re.IGNORECASE)
            if likes_match:
                likes = int(likes_match.group(1))
            if rt_match:
                retweets = int(rt_match.group(1))

            tweets.append({
                'id': tweet_id,
                'text': text,
                'author': handle_clean,
                'url': tweet_url,
                'timestamp': tweet_time or datetime.now(timezone.utc),
                'likes': likes,
                'retweets': retweets,
                'is_retweet': False,
                'raw_html': raw_text,
            })

        except Exception as e:
            print(f"    [PARSE] Warning: {e}")
            continue

    print(f"  [SCRAPE] ✅ Got {len(tweets)} usable tweets for @{handle_clean}")
    return tweets


def scrape_multiple_handles(
    handles: list[str],
    max_per_handle: int = 10,
    lookback_hours: int = 48,
    processed_ids: set = None,
) -> list[dict]:
    """
    Scrapes tweets from multiple handles and returns combined, sorted list.

    Args:
        handles       : List of Twitter handles
        max_per_handle: Max tweets per handle
        lookback_hours: Lookback window in hours
        processed_ids : Already-processed tweet IDs to skip

    Returns:
        Combined list sorted by timestamp (newest first)
    """
    if processed_ids is None:
        processed_ids = set()

    all_tweets = []

    for handle in handles:
        try:
            tweets = scrape_tweets(
                handle=handle,
                max_tweets=max_per_handle,
                lookback_hours=lookback_hours,
                processed_ids=processed_ids,
            )
            all_tweets.extend(tweets)
            # Polite delay between handles
            time.sleep(random.uniform(1.5, 3.0))
        except Exception as e:
            print(f"  [SCRAPE] Error for @{handle}: {e}")
            continue

    # Sort by timestamp (newest first)
    all_tweets.sort(key=lambda t: t['timestamp'], reverse=True)

    print(f"\n[SCRAPE] Total: {len(all_tweets)} tweets from {len(handles)} handles.")
    return all_tweets


def get_handles_from_supabase(site_id: str = None) -> list[str]:
    """
    Fetches active Twitter handles from Supabase twitter_handles table.

    Args:
        site_id: Optional site ID to filter handles per site

    Returns:
        List of handle strings (without @)
    """
    try:
        from config import SUPABASE_URL, SUPABASE_KEY
        if not SUPABASE_URL or not SUPABASE_KEY:
            return []

        url = f"{SUPABASE_URL}/rest/v1/twitter_handles?is_active=eq.true&select=handle"
        if site_id:
            url += f"&site_id=eq.{site_id}"

        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
        }
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return [row['handle'] for row in data if row.get('handle')]
        else:
            print(f"[HANDLES] Supabase error: {resp.status_code}")
            return []
    except Exception as e:
        print(f"[HANDLES] Error fetching handles: {e}")
        return []


def get_processed_tweet_ids(site_id: str = None) -> set:
    """
    Fetches already-processed tweet IDs from Supabase to prevent duplicates.
    """
    try:
        from config import SUPABASE_URL, SUPABASE_KEY
        if not SUPABASE_URL or not SUPABASE_KEY:
            return set()

        url = f"{SUPABASE_URL}/rest/v1/processed_tweets?select=tweet_id"
        if site_id:
            url += f"&site_id=eq.{site_id}"
        # Only last 7 days
        from datetime import date
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        url += f"&processed_at=gte.{cutoff}"

        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
        }
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            return {row['tweet_id'] for row in resp.json()}
        return set()
    except Exception as e:
        print(f"[TWEETS] Error fetching processed IDs: {e}")
        return set()


def mark_tweet_processed(tweet_id: str, site_id: str = None):
    """Marks a tweet as processed in Supabase."""
    try:
        from config import SUPABASE_URL, SUPABASE_KEY
        if not SUPABASE_URL or not SUPABASE_KEY:
            return

        url = f"{SUPABASE_URL}/rest/v1/processed_tweets"
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "tweet_id": tweet_id,
            "site_id": site_id,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }
        requests.post(url, json=payload, headers=headers, timeout=10)
    except Exception as e:
        print(f"[TWEETS] Error marking tweet processed: {e}")


# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("🐦 Twitter Scraper — Quick Test")
    print("=" * 50)

    test_handles = ["sama", "AndrewYNg", "karpathy"]
    tweets = scrape_multiple_handles(test_handles, max_per_handle=3, lookback_hours=72)

    for i, t in enumerate(tweets[:5], 1):
        print(f"\n[{i}] @{t['author']} | {t['timestamp'].strftime('%Y-%m-%d %H:%M')}")
        print(f"     {t['text'][:150]}...")
        print(f"     ❤️ {t['likes']} | 🔁 {t['retweets']}")
