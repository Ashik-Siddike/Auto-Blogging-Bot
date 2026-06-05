"""
twitter_blog_writer.py  —  Tweet → Premium Blog Post AI Writer
==============================================================
Gemini AI দিয়ে একটা tweet-কে বিস্তারিত, SEO-optimized blog post-এ রূপান্তর করে।

Features:
  • Tweet quality scoring (1-10) — শুধু ভালো tweet-ই ব্লগে যাবে
  • 600-1200 শব্দের প্রিমিয়াম HTML blog post generate
  • Auto SEO: title, meta description, slug, tags, read time
  • FAQ generation for rich snippets
  • Gemini API key rotation (same as ai_writer.py)
"""

import re
import json
import time
import random
from typing import Optional
from config import GEMINI_API_KEYS

# ── Blog Quality Threshold ────────────────────────────────────────────────────
MIN_BLOG_SCORE = 6  # Tweets scoring below this are skipped (out of 10)

# ── Gemini Key Rotation ────────────────────────────────────────────────────────
_key_index = 0


def _get_key() -> str:
    """Returns current Gemini API key."""
    if not GEMINI_API_KEYS:
        raise ValueError("No Gemini API keys configured!")
    return GEMINI_API_KEYS[_key_index % len(GEMINI_API_KEYS)]


def _next_key():
    """Rotates to next Gemini API key."""
    global _key_index
    _key_index = (_key_index + 1) % len(GEMINI_API_KEYS)
    print(f"  [AI] Rotated to Gemini key {_key_index + 1}/{len(GEMINI_API_KEYS)}")


def _call_gemini(prompt: str, max_retries: int = 5) -> Optional[str]:
    """
    Calls Gemini API with automatic key rotation and model fallback.
    Returns response text or None.
    """
    from google import genai

    preferred_models = [
        'gemini-2.5-flash',
        'gemini-1.5-flash',
        'gemini-1.5-pro',
        'gemini-2.0-flash',
        'gemini-1.0-pro',
        'gemini-pro',
    ]

    def is_quota_error(error):
        error_str = str(error).lower()
        quota_indicators = [
            "429", "quota exceeded", "quota", "resource exhausted",
            "rate limit", "permission denied", "403", "billing", "credit"
        ]
        return any(indicator in error_str for indicator in quota_indicators)

    # Try up to max_retries times, rotating key each time
    for attempt in range(max_retries):
        try:
            key = _get_key()
            client = genai.Client(api_key=key)
            
            response = None
            last_error = None
            
            for model_name in preferred_models:
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                    )
                    if response and response.text:
                        return response.text.strip()
                except Exception as model_err:
                    if is_quota_error(model_err):
                        raise model_err  # Raise to trigger key rotation
                    last_error = model_err
                    continue
            
            if last_error:
                raise last_error

        except Exception as e:
            print(f"  [AI] Gemini error with key {attempt+1}/{len(GEMINI_API_KEYS)}: {e}")
            _next_key()  # Rotate immediately to the next key in the pool
            time.sleep(2)  # Short delay before retrying with new key

    return None


# ── Tweet Quality Scoring ──────────────────────────────────────────────────────

def score_tweet_for_blog(tweet: dict, niche: str = "") -> dict:
    """
    Scores a tweet on blogworthiness (1-10) and decides if it should become a blog.

    Returns:
    {
        'score': int,        # 1-10 (higher = better blog candidate)
        'should_blog': bool, # True if score >= MIN_BLOG_SCORE
        'topic': str,        # Suggested blog topic/angle
        'reason': str,       # Why this score
    }
    """
    text = tweet.get('text', '')
    author = tweet.get('author', '')
    likes = tweet.get('likes', 0)
    retweets = tweet.get('retweets', 0)

    prompt = f"""You are a professional content strategist for a {niche or 'technology'} blog.

Evaluate this tweet for blog content potential:

Tweet by @{author}:
"{text}"

Engagement: {likes} likes, {retweets} retweets

Score this tweet from 1-10 for blog potential based on:
- Information value (is there real substance to expand on?)
- Timeliness (is it about a trending/important topic?)
- Uniqueness (is it a fresh perspective or announcement?)
- Expandability (can this become a 600-1000 word blog post?)
- Relevance to {niche or 'technology/AI'} niche

Respond ONLY with valid JSON (no markdown, no code blocks):
{{
  "score": <number 1-10>,
  "should_blog": <true/false>,
  "topic": "<suggested blog post title>",
  "reason": "<1 sentence why this score>",
  "category": "<one of: AI, Tech, Crypto, Finance, Science, Health, Business>"
}}"""

    response = _call_gemini(prompt)
    if not response:
        return {"score": 0, "should_blog": False, "topic": "", "reason": "AI unavailable", "category": "Tech"}

    try:
        # Extract JSON from response
        json_match = re.search(r'\{[^{}]+\}', response, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            result['should_blog'] = result.get('score', 0) >= MIN_BLOG_SCORE
            return result
    except (json.JSONDecodeError, KeyError) as e:
        print(f"  [SCORE] JSON parse error: {e} | Response: {response[:200]}")

    # Fallback scoring based on engagement
    score = 3
    if likes > 500 or retweets > 100:
        score = 7
    elif likes > 100 or retweets > 20:
        score = 5

    return {
        "score": score,
        "should_blog": score >= MIN_BLOG_SCORE,
        "topic": f"Analysis: {text[:60]}...",
        "reason": "Scored by engagement metrics (AI unavailable)",
        "category": "Tech"
    }


# ── Blog Content Generator ─────────────────────────────────────────────────────

def generate_blog_from_tweet(
    tweet: dict,
    topic: str = "",
    category: str = "Tech",
    niche: str = "",
    site_name: str = "Auto Blog",
    language: str = "English",
) -> Optional[dict]:
    """
    Generates a complete, SEO-optimized blog post from a tweet.

    Args:
        tweet    : Tweet dict from twitter_scraper
        topic    : Suggested blog topic (from score_tweet_for_blog)
        category : Blog category
        niche    : Site niche (e.g., "AI tools", "cryptocurrency")
        site_name: Site name for content customization
        language : Output language

    Returns:
        {
            'title': str,
            'slug': str,
            'content': str,       # Full HTML blog content
            'summary': str,       # 150-160 char meta description
            'tags': list[str],
            'category': str,
            'read_time': str,
            'faqs': list[dict],   # [{question, answer}]
        }
        or None on failure
    """
    tweet_text = tweet.get('text', '')
    author = tweet.get('author', '')
    tweet_url = tweet.get('url', '')
    tweet_date = tweet.get('timestamp')
    date_str = tweet_date.strftime('%B %d, %Y') if tweet_date else 'recently'

    blog_title = topic or f"Breaking: {tweet_text[:80]}..."

    prompt = f"""You are an expert content writer for a {niche or 'technology'} blog called "{site_name}".

TASK: Write a comprehensive, engaging, SEO-optimized blog post based on this tweet.

SOURCE TWEET by @{author} (posted {date_str}):
"{tweet_text}"

Tweet URL: {tweet_url}

BLOG REQUIREMENTS:
- Title: "{blog_title}" (or improve it if you have a better angle)
- Length: 600-1000 words
- Language: {language}
- Category: {category}
- Niche/Topic: {niche or 'technology'}
- Tone: Professional, engaging, informative
- Format: HTML (use h2, h3, p, ul, li, strong tags)

CONTENT STRUCTURE:
1. Introduction (2-3 paragraphs) — what happened, why it matters
2. Main Analysis (3-4 sections with h2 headings) — expand the tweet's info with context, background, implications
3. Expert Perspective section — what this means for the industry
4. Practical Takeaways (bullet list)
5. Conclusion — wrap up with future outlook

SEO REQUIREMENTS:
- Include primary keyword naturally in first 100 words
- Use related semantic keywords throughout
- Add internal transition phrases
- Include a "What This Means For You" section

TWEET ATTRIBUTION:
- Reference the original tweet naturally in the intro
- Don't just copy the tweet — expand it with additional context and analysis

Respond ONLY with valid JSON (no markdown, no code blocks):
{{
  "title": "<optimized blog title>",
  "slug": "<url-friendly-slug>",
  "meta_description": "<150-160 char SEO description>",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "content": "<full HTML blog content>",
  "summary": "<2-3 sentence post summary>"
}}"""

    print(f"  [WRITER] Generating blog post for topic: '{blog_title[:60]}'...")
    response = _call_gemini(prompt)

    if not response:
        print("  [WRITER] ❌ Blog generation failed.")
        return None

    try:
        # Extract JSON
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if not json_match:
            raise ValueError("No JSON found in response")

        data = json.loads(json_match.group())

        # Validate required fields
        if not data.get('title') or not data.get('content'):
            raise ValueError("Missing required fields: title or content")

        # Calculate read time
        word_count = len(re.sub(r'<[^>]+>', '', data.get('content', '')).split())
        read_time = max(1, round(word_count / 200))

        # Generate FAQs
        faqs = generate_faqs_for_blog(data['title'], niche)

        return {
            'title': data.get('title', blog_title),
            'slug': _generate_slug(data.get('slug') or data.get('title', '')),
            'content': data.get('content', ''),
            'summary': data.get('summary') or data.get('meta_description', ''),
            'meta_description': data.get('meta_description', ''),
            'tags': data.get('tags', [category]),
            'category': category,
            'read_time': f"{read_time} min read",
            'faqs': faqs,
            'source_tweet_url': tweet_url,
            'source_author': f"@{author}",
        }

    except (json.JSONDecodeError, ValueError) as e:
        print(f"  [WRITER] Parse error: {e}. Trying plain text fallback...")

        # Plain text fallback — extract what we can
        return _build_fallback_blog(tweet, blog_title, category, niche, response)


def _build_fallback_blog(tweet: dict, title: str, category: str, niche: str, ai_text: str) -> dict:
    """Fallback blog builder when JSON parsing fails."""
    text = tweet.get('text', '')
    author = tweet.get('author', '')

    # Use whatever the AI generated as raw content, wrapped in HTML
    content = f"""
<h2>Overview</h2>
<p>@{author} recently shared important insights on {niche or 'technology'}:</p>
<blockquote style="border-left: 4px solid #6366f1; padding-left: 1rem; margin: 1.5rem 0; color: #64748b;">
  <p>"{text}"</p>
  <cite>— @{author}</cite>
</blockquote>

<h2>Analysis</h2>
{ai_text[:2000] if ai_text else '<p>This development represents a significant moment in the industry.</p>'}

<h2>Key Takeaways</h2>
<ul>
<li>Stay updated with the latest developments in {niche or 'this space'}</li>
<li>Follow @{author} for more expert insights</li>
<li>Share your thoughts in the comments below</li>
</ul>
"""

    return {
        'title': title,
        'slug': _generate_slug(title),
        'content': content,
        'summary': f"@{author} shares insights on {niche or 'technology'}. {text[:120]}",
        'meta_description': f"{title[:155]}",
        'tags': [category, niche or 'tech', 'analysis'],
        'category': category,
        'read_time': '3 min read',
        'faqs': [],
        'source_tweet_url': tweet.get('url', ''),
        'source_author': f"@{author}",
    }


# ── FAQ Generator ──────────────────────────────────────────────────────────────

def generate_faqs_for_blog(title: str, niche: str = "") -> list[dict]:
    """Generates 3-5 FAQ pairs for rich snippet schema."""
    prompt = f"""Generate 3-4 FAQ (Frequently Asked Questions) pairs for a blog post titled:
"{title}"

Topic/Niche: {niche or 'technology'}

Each question should be something a reader might genuinely ask.
Answers should be 1-3 sentences, informative, and direct.

Respond ONLY with valid JSON array:
[
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}}
]"""

    response = _call_gemini(prompt)
    if not response:
        return []

    try:
        json_match = re.search(r'\[.*\]', response, re.DOTALL)
        if json_match:
            faqs = json.loads(json_match.group())
            return [f for f in faqs if f.get('question') and f.get('answer')]
    except Exception:
        pass

    return []


# ── Slug Generator ─────────────────────────────────────────────────────────────

def _generate_slug(text: str) -> str:
    """Converts title to URL-friendly slug."""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    slug = slug[:80].rstrip("-")
    # Add timestamp suffix to ensure uniqueness
    import time as _time
    suffix = str(int(_time.time()))[-6:]
    return f"{slug}-{suffix}"


def generate_social_captions_for_blog(title: str, summary: str, blog_url: str, niche: str = "") -> dict:
    """
    Uses Gemini to generate highly-optimized, platform-specific social media captions for a blog post.
    Returns a dict with keys: fb_content, ig_content, pin_title, pin_desc, linkedin_content
    """
    FALLBACK = {
        "fb_content": f"🔥 {title}\n\n📝 New blog post is live!\n✅ Read full article here → {blog_url}\n\n#Blog #News #{niche or 'Tech'}",
        "ig_content": f"🔥 {title}\n\n📝 New blog post is live! Click the link in our bio to read the full analysis!\n\n#Blog #News #LatestUpdates #{niche or 'Tech'}",
        "pin_title": f"New Article: {title}",
        "pin_desc": f"{title} — Read the complete article on our blog! {blog_url}\n\n#Blog #News #LatestUpdates",
        "linkedin_content": f"🔎 Just published: {title}\n\nRead the full article → {blog_url}\n\n#Blog #Professional #Updates",
    }

    prompt = f"""You are an expert social media copywriter.
Generate platform-optimized social media content for this blog post:
Title: {title}
Summary: {summary}
Blog Link: {blog_url}
Niche: {niche}

Return ONLY a valid JSON object (no markdown, no extra text) with these exact keys:
{{
  "fb_content": "Conversational, engaging Facebook post. 2-3 short paragraphs. Include emojis. End with CTA to click the blog link. Include 3-5 relevant hashtags.",
  "ig_content": "Visual, emoji-rich Instagram caption with line breaks. 15-20 hashtags. End with 'Link in bio!'. Do NOT include the actual URL.",
  "pin_title": "SEO-friendly Pinterest pin title under 100 characters.",
  "pin_desc": "Pinterest description under 500 characters. Include the blog URL naturally. Add 5-8 hashtags.",
  "linkedin_content": "Professional, value-driven LinkedIn post. 2-3 paragraphs. Include the blog URL. 3-5 professional hashtags."
}}"""

    max_attempts = len(GEMINI_API_KEYS) * 2
    for attempt in range(max_attempts):
        try:
            response = _call_gemini(prompt)
            if not response:
                raise ValueError("No response from Gemini")
                
            raw = response.strip()
            raw = re.sub(r'```(?:json)?\s*', '', raw)
            raw = re.sub(r'```\s*', '', raw).strip()

            start = raw.find('{')
            end = raw.rfind('}') + 1
            if start == -1 or end == 0:
                raise ValueError("No JSON found in response.")

            captions = json.loads(raw[start:end])
            for key in FALLBACK:
                if key not in captions or not captions[key]:
                    captions[key] = FALLBACK[key]

            print("  [AI:social] ✅ Social captions generated successfully.")
            return captions

        except Exception as e:
            print(f"  [AI:social] Error (attempt {attempt+1}): {e}. Rotating key...")
            _next_key()
            time.sleep(1)

    print("  [AI:social] All retries exhausted. Using fallback captions.")
    return FALLBACK


# ── Quick Test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("✍️  Blog Writer — Quick Test")
    print("=" * 50)

    test_tweet = {
        'id': '1234567890',
        'text': "We just released Gemini 2.0 Ultra — our most capable model yet. It scores 91.3% on MMLU, beats GPT-4o on every benchmark, and costs 70% less per token. Game changer for enterprise AI.",
        'author': 'sama',
        'url': 'https://twitter.com/sama/status/1234567890',
        'timestamp': None,
        'likes': 15420,
        'retweets': 3201,
    }

    print("\n1. Scoring tweet...")
    score_result = score_tweet_for_blog(test_tweet, niche="AI")
    print(f"   Score: {score_result['score']}/10 | Should blog: {score_result['should_blog']}")
    print(f"   Topic: {score_result['topic']}")

    if score_result['should_blog']:
        print("\n2. Generating blog post...")
        blog = generate_blog_from_tweet(
            tweet=test_tweet,
            topic=score_result['topic'],
            category=score_result.get('category', 'AI'),
            niche="artificial intelligence",
            site_name="AI Updates",
        )
        if blog:
            print(f"   Title: {blog['title']}")
            print(f"   Slug: {blog['slug']}")
            print(f"   Tags: {blog['tags']}")
            print(f"   Read time: {blog['read_time']}")
            print(f"   FAQs: {len(blog['faqs'])}")
            print(f"   Content length: {len(blog['content'])} chars")
