import os
from dotenv import load_dotenv

load_dotenv()

# ScrapingAnt API Keys (Rotation Pool)
# ScrapingAnt API Keys (Rotation Pool)
# Loaded from .env file (Comma or newline separated)
_scraping_keys_str = os.getenv("SCRAPINGANT_API_KEYS", "").replace("\n", ",")
SCRAPINGANT_API_KEYS = [k.strip() for k in _scraping_keys_str.split(",") if k.strip()]

# Gemini API Keys (Rotation Pool)
# Gemini API Keys (Rotation Pool)
# Loaded from .env file (Comma or newline separated)
# MANUAL PARSNG to handle unquoted newlines in .env
def load_multiline_gemini_keys():
    """
    Loads Gemini API keys with two strategies:
    1. Railway/Server: reads GEMINI_API_KEYS from environment variable directly
    2. Local dev: parses multi-line format from .env file
    """
    import re

    # ── Strategy 1: Environment variable (Railway, Render, etc.) ──
    env_val = os.getenv("GEMINI_API_KEYS", "").strip()
    if env_val:
        keys = []
        for part in env_val.replace("\n", ",").split(","):
            clean = part.strip()
            if (clean.startswith("AIzaSy") or clean.startswith("AQ.")) and len(clean) > 30:
                keys.append(clean)
        if keys:
            print(f"[CONFIG] Loaded {len(keys)} Gemini key(s) from environment.")
            return keys

    # ── Strategy 2: Parse .env file (local development) ──
    keys = []
    try:
        if os.path.exists(".env"):
            with open(".env", "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            match = re.search(r"GEMINI_API_KEYS=(.*?)(?:\n[A-Z_]+=|$\Z)", content, re.DOTALL)
            if match:
                raw_block = match.group(1)
                for line in raw_block.split('\n'):
                    if '#' in line:
                        line = line.split('#')[0]
                    for part in line.split(','):
                        clean_key = part.strip()
                        if (clean_key.startswith("AIzaSy") or clean_key.startswith("AQ.")) and len(clean_key) > 30:
                            keys.append(clean_key)
    except Exception as e:
        print(f"[CONFIG] Error parsing .env manually: {e}")

    return keys

GEMINI_API_KEYS = load_multiline_gemini_keys()

# Legacy single key support (for backward compatibility)
GEMINI_API_KEY = GEMINI_API_KEYS[0] if GEMINI_API_KEYS else None

# WordPress Credentials
WP_URL = os.getenv("WP_URL", "")
WP_USERNAME = os.getenv("WP_USERNAME", "")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD", "")

# n8n Webhook URL (PRODUCTION)
# Important: Production URL requires workflow to be ACTIVE in n8n dashboard
# If you get 404 error, make sure the workflow is toggled ON in n8n
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "")

# Make.com Webhook URL (For new social media automation)
MAKE_WEBHOOK_URL = os.getenv("MAKE_WEBHOOK_URL", "https://n8n.srv915514.hstgr.cloud/webhook/amazon-master-webhook")

# Niche Categories for Auto-Discovery (Used if Supabase is empty)
NICHE_KEYWORDS = {
    "watches": [
        "best budget tactical watch 2025",
        "SKMEI waterproof sports watch review",
        "CURREN luxury watch under 50",
    ],
    "gadgets": [
        "best budget wireless earbuds 2025",
        "cheap smart home devices for beginners",
    ],
    "gaming": [
        "best handheld retro gaming console 2025",
        "budget 4k game stick review",
    ]
}

# Supabase Configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Automation Key
AUTO_KEY = os.getenv("AUTO_KEY")

NEXT_API_URL = os.getenv('NEXT_API_URL', 'http://localhost:3000/api/posts')
BOT_API_SECRET = os.getenv('BOT_API_SECRET', '')

# Cloudinary Configuration for Image Composition
CLOUDINARY_URL = os.getenv('CLOUDINARY_URL', '')

# Amazon Affiliate Tag (e.g., "ashiksiddike-20" for US store)
AMAZON_AFFILIATE_TAG = os.getenv('AMAZON_AFFILIATE_TAG', 'ashiksiddike-20')
