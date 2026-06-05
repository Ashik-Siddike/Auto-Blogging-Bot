"""
twitter_pipeline.py  —  Twitter → Blog Full Pipeline Orchestrator
=================================================================
সম্পূর্ণ Twitter-to-Blog automation pipeline।

Flow:
  1. Supabase থেকে Twitter handles লোড
  2. Nitter RSS দিয়ে tweets scrape
  3. Gemini AI দিয়ে tweet quality score
  4. যোগ্য tweets থেকে full blog post generate
  5. Gemini Imagen দিয়ে featured image generate
  6. Next.js /api/posts-এ publish
  7. Telegram alert পাঠাও
  8. Supabase-এ tweet mark as processed

Usage:
  python twitter_pipeline.py                    # Runs for all active sites
  python twitter_pipeline.py --test             # Test mode (no publish)
  python twitter_pipeline.py --handles @sama    # Specific handles
"""

import os
import sys
import time
import re
import traceback
import requests
import json
import argparse
from datetime import datetime, timezone

# Ensure UTF-8 output on Windows terminal
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# ── Module imports ─────────────────────────────────────────────────────────────
import twitter_scraper
import twitter_blog_writer
import twitter_image_generator

from config import (
    SUPABASE_URL, SUPABASE_KEY,
    NEXT_API_URL, BOT_API_SECRET,
    GEMINI_API_KEYS,
)


# ── Default handles (fallback if Supabase has none) ───────────────────────────
DEFAULT_AI_HANDLES = [
    "sama",           # Sam Altman (OpenAI CEO)
    "AndrewYNg",      # Andrew Ng
    "karpathy",       # Andrej Karpathy
    "ylecun",         # Yann LeCun
    "demishassabis",  # DeepMind CEO
    "GoogleAI",
    "OpenAI",
    "AnthropicAI",
]

DEFAULT_TECH_HANDLES = [
    "elonmusk",
    "satyanadella",
    "sundarpichai",
    "BillGates",
]

LOOKBACK_HOURS = 48       # Look back 48 hours
MAX_BLOGS_PER_CYCLE = 5   # Max blogs to publish per pipeline run
MIN_SCORE_TO_BLOG = 6     # Min tweet quality score (1-10)


# ── Telegram Alert ─────────────────────────────────────────────────────────────

def _telegram_alert(message: str):
    """Sends a Telegram notification."""
    try:
        token = os.getenv("TELEGRAM_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        if not token or not chat_id:
            return
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception:
        pass


# ── Supabase helpers ───────────────────────────────────────────────────────────

def _supabase_get(endpoint: str) -> list:
    """Generic Supabase REST GET."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }
    try:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/{endpoint}", headers=headers, timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"[DB] Supabase GET error: {e}")
    return []


def _supabase_post(endpoint: str, payload: dict) -> bool:
    """Generic Supabase REST POST."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    try:
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/{endpoint}",
            json=payload, headers=headers, timeout=10
        )
        return r.status_code in [200, 201]
    except Exception as e:
        print(f"[DB] Supabase POST error: {e}")
    return False


def load_active_sites_twitter() -> list[dict]:
    """Loads active sites with source_type = 'twitter' from Supabase."""
    data = _supabase_get("sites?status=eq.active&source_type=eq.twitter&select=*")
    if not data:
        # Fallback: load all active sites (old schema without source_type)
        data = _supabase_get("sites?status=eq.active&select=*")
        # Filter to twitter-capable ones
        data = [s for s in data if s.get('source_type') == 'twitter' or s.get('twitter_handles')]

    print(f"[PIPELINE] Found {len(data)} active Twitter-mode site(s) in Supabase.")
    return data


def load_handles_for_site(site_id: str, site_config: dict) -> list[str]:
    """
    Returns Twitter handles for a site.
    Priority: site.twitter_handles field → Supabase twitter_handles table → defaults
    """
    # 1. From site config field (JSON array or comma-separated string)
    raw_handles = site_config.get('twitter_handles', [])
    if isinstance(raw_handles, str):
        raw_handles = [h.strip() for h in raw_handles.split(',') if h.strip()]
    if raw_handles:
        print(f"  [HANDLES] Loaded {len(raw_handles)} handles from site config.")
        return [h.lstrip('@') for h in raw_handles]

    # 2. From Supabase twitter_handles table
    db_handles = twitter_scraper.get_handles_from_supabase(site_id=site_id)
    if db_handles:
        print(f"  [HANDLES] Loaded {len(db_handles)} handles from Supabase table.")
        return db_handles

    # 3. Default fallback based on niche
    niche = (site_config.get('niche') or '').lower()
    if any(w in niche for w in ['ai', 'tech', 'artificial']):
        print(f"  [HANDLES] Using default AI handles.")
        return DEFAULT_AI_HANDLES
    else:
        print(f"  [HANDLES] Using default Tech handles.")
        return DEFAULT_AI_HANDLES + DEFAULT_TECH_HANDLES


def publish_to_site(blog: dict, site_config: dict, dry_run: bool = False) -> str | None:
    """
    Publishes blog post to the Next.js site via /api/posts endpoint.
    Returns post URL on success, None on failure.
    """
    # Get the API URL — prefer site-specific, then env var
    api_url = (
        site_config.get('api_url')
        or site_config.get('nextjs_api_url')
        or NEXT_API_URL
        or "https://auto-blogging-site.vercel.app/api/posts"
    )
    secret = site_config.get('bot_api_secret') or BOT_API_SECRET or ""
    site_url = site_config.get('url') or site_config.get('domain') or "https://auto-blogging-site.vercel.app"

    if dry_run:
        print(f"  [DRY RUN] Would publish: {blog['title']}")
        print(f"  [DRY RUN] API URL: {api_url}")
        return f"{site_url}/post/{blog['slug']}"

    payload = {
        "title": blog['title'],
        "slug": blog['slug'],
        "content": blog['content'],
        "imageUrl": blog.get('image_url', ''),
        "summary": blog.get('summary', ''),
        "category": blog.get('category', 'Tech'),
        "tags": blog.get('tags', []),
        "read_time": blog.get('read_time', '5 min read'),
        "faqs": blog.get('faqs', []),
        "source_tweet_url": blog.get('source_tweet_url', ''),
        "source_author": blog.get('source_author', ''),
    }

    headers = {
        "Content-Type": "application/json",
        "x-bot-api-secret": secret,
    }

    for attempt in range(3):
        try:
            print(f"  [PUBLISH] Sending to {api_url} (attempt {attempt+1}/3)...")
            r = requests.post(api_url, json=payload, headers=headers, timeout=20)

            if r.status_code in [200, 201]:
                slug = r.json().get('slug', blog['slug'])
                post_url = f"{site_url.rstrip('/')}/post/{slug}"
                print(f"  [PUBLISH] ✅ Published: {post_url}")
                # Ping Google sitemap
                try:
                    requests.get(
                        f"https://www.google.com/ping?sitemap={site_url.rstrip('/')}/sitemap.xml",
                        timeout=5
                    )
                except Exception:
                    pass
                return post_url
            else:
                print(f"  [PUBLISH] ❌ HTTP {r.status_code}: {r.text[:200]}")

        except requests.exceptions.RequestException as e:
            print(f"  [PUBLISH] Network error: {e}")

        if attempt < 2:
            time.sleep(2 ** attempt * 3)

    return None


# ── Main Pipeline ──────────────────────────────────────────────────────────────

def run_twitter_pipeline(
    site_config: dict,
    handles_override: list[str] = None,
    dry_run: bool = False,
    max_blogs: int = MAX_BLOGS_PER_CYCLE,
) -> dict:
    """
    Runs the complete Twitter → Blog pipeline for a single site.

    Returns:
        {'blogs_published': int, 'blogs_skipped': int, 'errors': int}
    """
    site_name = site_config.get('name', 'Unknown Site')
    site_id = site_config.get('id')
    niche = site_config.get('niche') or site_config.get('niche_prompt', 'technology')
    language = site_config.get('language', 'English')

    print(f"\n{'=' * 60}")
    print(f"[PIPELINE] 🐦 Twitter Pipeline for: {site_name}")
    print(f"[PIPELINE] Niche: {niche} | Language: {language}")
    print(f"{'=' * 60}")

    stats = {'blogs_published': 0, 'blogs_skipped': 0, 'errors': 0}

    # ── Step 1: Get Handles ────────────────────────────────────────────────
    handles = handles_override or load_handles_for_site(site_id, site_config)
    if not handles:
        print("[PIPELINE] ❌ No Twitter handles found. Exiting.")
        return stats

    print(f"[PIPELINE] 📋 Processing {len(handles)} handle(s): {', '.join('@'+h for h in handles[:5])}")

    # ── Step 2: Get Processed Tweet IDs (deduplication) ────────────────────
    processed_ids = twitter_scraper.get_processed_tweet_ids(site_id=site_id)
    print(f"[PIPELINE] 🔄 Already processed: {len(processed_ids)} tweets (dedup cache)")

    # ── Step 3: Scrape Tweets ──────────────────────────────────────────────
    all_tweets = twitter_scraper.scrape_multiple_handles(
        handles=handles,
        max_per_handle=10,
        lookback_hours=LOOKBACK_HOURS,
        processed_ids=processed_ids,
    )

    if not all_tweets:
        print("[PIPELINE] ⚠️  No new tweets found in the last 48h.")
        return stats

    print(f"[PIPELINE] 📊 Found {len(all_tweets)} fresh tweets to analyze.")

    # ── Step 4: Score & Filter Tweets ─────────────────────────────────────
    blog_candidates = []
    print(f"\n[PIPELINE] 🧠 Scoring tweets for blog potential...")

    for tweet in all_tweets[:20]:  # Analyze at most 20 tweets per cycle
        try:
            score_result = twitter_blog_writer.score_tweet_for_blog(tweet, niche=niche)
            score = score_result.get('score', 0)

            print(f"  Score {score}/10 | @{tweet['author']}: {tweet['text'][:60]}...")

            if score_result.get('should_blog', False) and score >= MIN_SCORE_TO_BLOG:
                blog_candidates.append({
                    'tweet': tweet,
                    'score': score,
                    'topic': score_result.get('topic', ''),
                    'category': score_result.get('category', 'Tech'),
                })
            else:
                stats['blogs_skipped'] += 1

            time.sleep(0.5)  # Polite rate limiting

        except Exception as e:
            print(f"  [SCORE] Error: {e}")
            stats['errors'] += 1
            continue

    # Sort by score (best first)
    blog_candidates.sort(key=lambda x: x['score'], reverse=True)
    print(f"\n[PIPELINE] ✅ {len(blog_candidates)} tweet(s) qualify for blog posts.")

    if not blog_candidates:
        print("[PIPELINE] No qualifying tweets. Try lowering MIN_SCORE or adding more handles.")
        return stats

    # ── Step 5: Generate & Publish Blogs ──────────────────────────────────
    for candidate in blog_candidates[:max_blogs]:
        if stats['blogs_published'] >= max_blogs:
            break

        tweet = candidate['tweet']
        topic = candidate['topic']
        category = candidate['category']

        print(f"\n[PIPELINE] ✍️  Writing blog #{stats['blogs_published']+1}: '{topic[:60]}'")

        try:
            # 5a. Generate blog content
            blog = twitter_blog_writer.generate_blog_from_tweet(
                tweet=tweet,
                topic=topic,
                category=category,
                niche=niche,
                site_name=site_name,
                language=language,
            )

            if not blog:
                print("  [PIPELINE] ❌ Blog generation failed. Skipping.")
                stats['errors'] += 1
                continue

            # 5b. Generate AI featured image (Gemini Imagen → Cloudinary)
            print("  [PIPELINE] 🖼️  Generating featured image with Gemini Imagen...")
            image_url = twitter_image_generator.generate_blog_image(
                title=blog['title'],
                category=blog.get('category', category),
                niche=niche,
                site_name=site_name,
                slug=blog.get('slug', ''),
            )
            blog['image_url'] = image_url

            # 5c. Publish to site
            post_url = publish_to_site(blog, site_config, dry_run=dry_run)

            if post_url:
                stats['blogs_published'] += 1

                # 5d. Mark tweet as processed (prevent republishing)
                twitter_scraper.mark_tweet_processed(tweet['id'], site_id=site_id)

                # 5e. Supabase log entry
                _supabase_post("twitter_publish_log", {
                    "site_id": site_id,
                    "tweet_id": tweet['id'],
                    "tweet_author": tweet.get('author', ''),
                    "blog_title": blog['title'],
                    "blog_url": post_url,
                    "image_url": image_url,
                    "score": candidate['score'],
                    "published_at": datetime.now(timezone.utc).isoformat(),
                })

                print(f"  [PIPELINE] ✅ Published: {post_url}")
                print(f"  [PIPELINE] 📸 Image: {image_url[:60] if image_url else 'No image'}")

                # 5f. Generate Social Captions & Trigger Make.com Webhook
                webhook_url = site_config.get('make_webhook_url') or site_config.get('n8n_webhook')
                if webhook_url and not dry_run:
                    print("  [PIPELINE] 📱 Generating social captions for Make.com cross-posting...")
                    try:
                        social_captions = twitter_blog_writer.generate_social_captions_for_blog(
                            title=blog['title'],
                            summary=blog.get('summary', ''),
                            blog_url=post_url,
                            niche=niche
                        )
                        
                        import make_handler
                        make_payload = {
                            "title":            blog['title'],
                            "url":              post_url,
                            "imageUrl":         image_url,
                            "pinterestImageUrl": image_url,
                            "amazonUrl":        "", # Standard blogs have no amazon links
                            "keyword":          blog.get('tags', [category])[0] if blog.get('tags') else 'Tech',
                            "brand":            "Blog",
                            "fb_content":       social_captions.get('fb_content', ''),
                            "pin_title":        social_captions.get('pin_title', ''),
                            "pin_desc":         social_captions.get('pin_desc', ''),
                            "ig_content":       social_captions.get('ig_content', ''),
                            "linkedin_content": social_captions.get('linkedin_content', ''),
                        }
                        
                        print("  [PIPELINE] 🚀 Triggering Make.com social media cross-poster...")
                        make_success = make_handler.send_to_make_webhook(make_payload, webhook_url=webhook_url)
                        if make_success:
                            print("  [PIPELINE] ✅ Make.com social cross-posting completed.")
                        else:
                            print("  [PIPELINE] ⚠️ Make.com webhook trigger failed.")
                            
                    except Exception as social_err:
                        print(f"  [PIPELINE] ⚠️ Failed to execute social sharing flow: {social_err}")
                else:
                    if not webhook_url:
                        print("  [PIPELINE] Make.com webhook not configured for this site. Skipping social sharing.")
                    else:
                        print("  [PIPELINE] Dry-run enabled. Skipping social sharing.")

            else:
                stats['errors'] += 1
                print("  [PIPELINE] ❌ Publish failed.")

            # Polite delay between articles
            if stats['blogs_published'] < max_blogs:
                delay = 8
                print(f"  [PIPELINE] ⏱️  Waiting {delay}s before next article...")
                time.sleep(delay)

        except Exception as e:
            err_msg = traceback.format_exc()
            print(f"  [PIPELINE] 🚨 Error: {e}\n{err_msg}")
            stats['errors'] += 1
            continue

    return stats


def run_all_twitter_sites(
    dry_run: bool = False,
    handles_override: list[str] = None,
    max_blogs_per_site: int = MAX_BLOGS_PER_CYCLE,
):
    """
    Runs Twitter pipeline for ALL active Twitter-mode sites in Supabase.
    Called by GitHub Actions via run_single_cycle.py
    """
    print("\n🚀 Twitter Auto-Blogging Pipeline Started")
    print(f"   Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"   Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print("=" * 60)

    sites = load_active_sites_twitter()

    if not sites:
        print("[PIPELINE] No Twitter-mode sites found in Supabase.")
        print("[PIPELINE] Creating default single-site run with env config...")

        # Fallback: run with a default site config from env vars
        default_site = {
            'id': None,
            'name': os.getenv('SITE_NAME', 'Auto Blog'),
            'url': os.getenv('SITE_URL', 'https://auto-blogging-site.vercel.app'),
            'niche': os.getenv('SITE_NICHE', 'AI and Technology'),
            'language': os.getenv('SITE_LANGUAGE', 'English'),
            'api_url': NEXT_API_URL or 'https://auto-blogging-site.vercel.app/api/posts',
            'bot_api_secret': BOT_API_SECRET,
            'twitter_handles': handles_override or DEFAULT_AI_HANDLES,
        }
        sites = [default_site]

    total_published = 0
    total_errors = 0

    for site in sites:
        try:
            stats = run_twitter_pipeline(
                site_config=site,
                handles_override=handles_override,
                dry_run=dry_run,
                max_blogs=max_blogs_per_site,
            )
            total_published += stats.get('blogs_published', 0)
            total_errors += stats.get('errors', 0)

            # Telegram report per site
            site_msg = (
                f"🐦 <b>Twitter Pipeline: {site.get('name', 'Site')}</b>\n"
                f"✅ Published: {stats['blogs_published']} blogs\n"
                f"⏭️ Skipped: {stats['blogs_skipped']} tweets\n"
                f"❌ Errors: {stats['errors']}"
            )
            _telegram_alert(site_msg)

        except Exception as e:
            err = traceback.format_exc()
            print(f"[PIPELINE] 🚨 Site error: {e}\n{err}")
            _telegram_alert(f"🚨 <b>Pipeline Error</b>: {site.get('name', '?')}\n<code>{str(e)[:200]}</code>")
            total_errors += 1
            continue

    # Final summary
    print(f"\n{'=' * 60}")
    print(f"[PIPELINE] 🏁 DONE | Published: {total_published} | Errors: {total_errors}")
    print(f"{'=' * 60}")

    _telegram_alert(
        f"✅ <b>Twitter Pipeline Complete!</b>\n"
        f"Sites processed: {len(sites)}\n"
        f"Total blogs published: {total_published}\n"
        f"Going back to sleep 💤"
    )

    return total_published


# ── CLI Entry Point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Twitter → Auto-Blog Pipeline")
    parser.add_argument("--test", action="store_true", help="Dry run — no publishing")
    parser.add_argument("--handles", nargs="+", help="Twitter handles to scrape (e.g., @sama karpathy)")
    parser.add_argument("--max-blogs", type=int, default=MAX_BLOGS_PER_CYCLE, help="Max blogs to publish per run")
    parser.add_argument("--niche", type=str, default="", help="Override niche for test run")
    args = parser.parse_args()

    # Clean handles
    handles = None
    if args.handles:
        handles = [h.lstrip('@').strip() for h in args.handles]
        print(f"[CLI] Using custom handles: {handles}")

    if args.test:
        print("⚠️  DRY RUN MODE — No posts will actually be published")

    run_all_twitter_sites(
        dry_run=args.test,
        handles_override=handles,
        max_blogs_per_site=args.max_blogs,
    )
