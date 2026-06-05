"""
twitter_image_generator.py  —  AI-Powered Featured Image Generator
===================================================================
Google Gemini Imagen API দিয়ে blog-এর জন্য featured image generate করে।
Social Media Growing Bot-এর মতো একই Imagen system ব্যবহার করে।

Pipeline:
  Blog Title + Category → Gemini → Image Prompt → Imagen → Cloudinary → CDN URL

Fallback chain:
  1. Gemini Imagen (Primary)
  2. Pillow gradient image with title text (Fallback)
  3. Category-specific placeholder (Final fallback)
"""

import io
import os
import sys
import re
import math
import random
import base64
import time
import requests

import cloudinary
import cloudinary.uploader
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from config import CLOUDINARY_URL, GEMINI_API_KEYS

# ── Bootstrap Cloudinary ───────────────────────────────────────────────────────
if CLOUDINARY_URL:
    cloudinary.config(url=CLOUDINARY_URL)

# ── Design Tokens (matching image_composer.py aesthetic) ─────────────────────
CANVAS_W, CANVAS_H = 1200, 630  # Open Graph / Blog hero ratio
FALLBACK_GRADIENTS = {
    "ai":          [(15, 23, 42),   (30, 41, 59)],   # Deep Navy
    "tech":        [(17, 24, 39),   (31, 41, 55)],   # Dark Slate
    "crypto":      [(23, 16, 43),   (45, 26, 80)],   # Deep Purple
    "finance":     [(14, 35, 20),   (22, 101, 52)],  # Dark Green
    "health":      [(30, 14, 45),   (88, 28, 135)],  # Violet
    "default":     [(13, 27, 42),   (28, 48, 74)],   # Ocean Blue
}


# ── Gemini Imagen Core ────────────────────────────────────────────────────────

def _build_image_prompt(title: str, category: str = "", niche: str = "") -> str:
    """
    Generates a detailed Imagen prompt from blog title + category.
    Uses a Gemini text call to create a vivid, accurate image prompt.
    """
    context = category or niche or "technology"
    prompt = f"""Create a detailed image generation prompt for a professional blog featured image.

Blog Title: "{title}"
Category/Niche: {context}

Write a single, detailed prompt (2-3 sentences) describing a stunning, 
professional, high-quality featured image for this blog post. 
The image should:
- Be photorealistic or high-quality digital art
- Convey the topic visually without any text
- Use dramatic lighting, depth, and professional composition
- Be suitable as a blog hero image (16:9 aspect ratio)
- Have rich colors and professional aesthetics

Output ONLY the image prompt, nothing else. No quotes, no labels."""

    try:
        from google import genai
        key = GEMINI_API_KEYS[0] if GEMINI_API_KEYS else None
        if not key:
            raise ValueError("No Gemini key")

        client = genai.Client(api_key=key)
        preferred_models = [
            'gemini-2.5-flash',
            'gemini-1.5-flash',
            'gemini-1.5-pro',
            'gemini-2.0-flash',
            'gemini-1.0-pro',
            'gemini-pro',
        ]
        
        response = None
        last_error = None
        for model_name in preferred_models:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                if response and response.text:
                    break
            except Exception as model_err:
                last_error = model_err
                continue
                
        if not response or not response.text:
            if last_error:
                raise last_error
            raise ValueError("Empty response from Gemini")

        image_prompt = response.text.strip()
        print(f"  [IMAGEN] Generated prompt: {image_prompt[:100]}...")
        return image_prompt

    except Exception as e:
        print(f"  [IMAGEN] Prompt generation failed: {e}. Using default.")
        # Fallback: generic prompt
        return (
            f"Professional blog featured image about {title[:60]}. "
            f"Dramatic cinematic lighting, dark background with vibrant accent colors, "
            f"ultra-high-quality digital art, 16:9 composition, no text."
        )


def generate_with_imagen(title: str, category: str = "", niche: str = "") -> bytes | None:
    """
    Calls Gemini Imagen API to generate an image.
    Returns raw PNG bytes on success, None on failure.
    """
    image_prompt = _build_image_prompt(title, category, niche)

    # Try each Gemini key in rotation
    for i, api_key in enumerate(GEMINI_API_KEYS):
        try:
            print(f"  [IMAGEN] Generating with Gemini Imagen (key {i+1}/{len(GEMINI_API_KEYS)})...")
            from google import genai
            from google.genai import types as genai_types

            client = genai.Client(api_key=api_key)

            response = client.models.generate_images(
                model="imagen-3.0-generate-002",
                prompt=image_prompt,
                config=genai_types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio="16:9",
                    safety_filter_level="block_only_high",
                    person_generation="dont_allow",
                ),
            )

            if response.generated_images:
                img_bytes = response.generated_images[0].image.image_bytes
                print(f"  [IMAGEN] ✅ Image generated successfully!")
                return img_bytes

        except Exception as e:
            print(f"  [IMAGEN] Key {i+1} error: {e}")
            if i < len(GEMINI_API_KEYS) - 1:
                time.sleep(2)
                continue
            break

    print("  [IMAGEN] ⚠️  All Gemini keys exhausted. Falling back to Pillow.")
    return None


# ── Pillow Fallback Image ─────────────────────────────────────────────────────

def _load_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    """Tries to load a system font, falls back to Pillow default."""
    paths_bold = [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/calibrib.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    paths_reg = [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibri.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for p in (paths_bold if bold else paths_reg):
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _build_gradient(size, color_top, color_bottom):
    """Creates a vertical gradient background."""
    w, h = size
    img = Image.new("RGB", size)
    pixels = img.load()
    r1, g1, b1 = color_top
    r2, g2, b2 = color_bottom
    for y in range(h):
        t = y / h
        pixels_row = (
            int(r1 + (r2 - r1) * t),
            int(g1 + (g2 - g1) * t),
            int(b1 + (b2 - b1) * t),
        )
        for x in range(w):
            pixels[x, y] = pixels_row
    return img


def _wrap_text(text: str, font, max_width: int, draw) -> list[str]:
    """Wraps text to fit within max_width pixels."""
    words = text.split()
    lines = []
    current_line = []

    for word in words:
        test_line = ' '.join(current_line + [word])
        bbox = draw.textbbox((0, 0), test_line, font=font)
        if bbox[2] <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(' '.join(current_line))
            current_line = [word]

    if current_line:
        lines.append(' '.join(current_line))

    return lines


def generate_pillow_fallback(title: str, category: str = "", site_name: str = "Blog") -> bytes:
    """
    Generates a premium-looking blog featured image using only Pillow.
    Used as fallback when Imagen API fails.
    """
    # Determine color scheme by category
    cat_lower = (category or "").lower()
    if any(w in cat_lower for w in ["ai", "artificial", "machine", "gpt", "llm"]):
        colors = FALLBACK_GRADIENTS["ai"]
    elif any(w in cat_lower for w in ["crypto", "bitcoin", "ethereum", "nft"]):
        colors = FALLBACK_GRADIENTS["crypto"]
    elif any(w in cat_lower for w in ["finance", "money", "invest", "stock"]):
        colors = FALLBACK_GRADIENTS["finance"]
    elif any(w in cat_lower for w in ["health", "medical", "wellness"]):
        colors = FALLBACK_GRADIENTS["health"]
    elif any(w in cat_lower for w in ["tech", "software", "code", "dev"]):
        colors = FALLBACK_GRADIENTS["tech"]
    else:
        colors = FALLBACK_GRADIENTS["default"]

    img = _build_gradient((CANVAS_W, CANVAS_H), colors[0], colors[1])

    # Add noise/texture overlay
    overlay = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    draw_ov = ImageDraw.Draw(overlay)
    for _ in range(300):
        x = random.randint(0, CANVAS_W)
        y = random.randint(0, CANVAS_H)
        r = random.randint(1, 3)
        alpha = random.randint(10, 40)
        draw_ov.ellipse([x, y, x+r, y+r], fill=(255, 255, 255, alpha))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    # Draw geometric accent lines
    draw = ImageDraw.Draw(img)
    accent = (99, 102, 241)  # Indigo accent
    for offset in [0, 3, 6]:
        draw.line([(0, 120 + offset), (CANVAS_W, 120 + offset)],
                  fill=accent + (255,) if offset == 0 else (50, 50, 150), width=1)
    for offset in [0, 3, 6]:
        draw.line([(0, CANVAS_H - 120 - offset), (CANVAS_W, CANVAS_H - 120 - offset)],
                  fill=accent + (255,) if offset == 0 else (50, 50, 150), width=1)

    # Category badge
    if category:
        badge_font = _load_font(22, bold=True)
        cat_text = f"  {category.upper()}  "
        bbox = draw.textbbox((0, 0), cat_text, font=badge_font)
        bw = bbox[2] - bbox[0]
        pad = 16
        badge_x = (CANVAS_W - bw - pad * 2) // 2
        badge_y = 150
        draw.rounded_rectangle(
            [badge_x, badge_y, badge_x + bw + pad * 2, badge_y + 44],
            radius=22, fill=(99, 102, 241),
        )
        draw.text((badge_x + pad, badge_y + 12), cat_text, font=badge_font, fill=(255, 255, 255))

    # Title text (centered, wrapped)
    title_font = _load_font(54, bold=True)
    max_title_w = int(CANVAS_W * 0.85)
    lines = _wrap_text(title[:120], title_font, max_title_w, draw)
    lines = lines[:3]  # Max 3 lines

    total_text_h = len(lines) * 70
    start_y = (CANVAS_H - total_text_h) // 2 + 20

    for i, line in enumerate(lines):
        y_pos = start_y + i * 70
        bbox = draw.textbbox((0, 0), line, font=title_font)
        x_pos = (CANVAS_W - (bbox[2] - bbox[0])) // 2

        # Shadow
        draw.text((x_pos + 3, y_pos + 3), line, font=title_font, fill=(0, 0, 0, 180))
        # Main text
        draw.text((x_pos, y_pos), line, font=title_font, fill=(255, 255, 255))

    # Site name watermark (bottom)
    wm_font = _load_font(24, bold=True)
    wm_text = f"● {site_name}"
    draw.text((40, CANVAS_H - 50), wm_text, font=wm_font, fill=(255, 255, 255, 140))

    # Encode to bytes
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90, optimize=True)
    buf.seek(0)
    return buf.read()


# ── Main Public API ───────────────────────────────────────────────────────────

def generate_blog_image(
    title: str,
    category: str = "",
    niche: str = "",
    site_name: str = "Auto Blog",
    slug: str = "",
) -> str:
    """
    Generates a featured image for a blog post and uploads to Cloudinary.

    Pipeline:
    1. Try Google Flow automation (via Playwright browser automation with saved session cookies)
    2. Fallback to Gemini Imagen API -> get AI-generated image
    3. Fallback to Pillow gradient card / image
    4. Upload to Cloudinary -> return CDN URL
    """
    print(f"\n[IMG_GEN] Generating featured image for: '{title[:60]}...'")
    img_bytes = None

    # ── Step 1: Try Google Flow browser automation ──
    try:
        # Check if browser agent module is available
        sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "social-mediya-growing-agent"))
        from flow_generator import generate_google_flow_image
        
        # Build beautiful prompt specifically styled for flow
        flow_prompt = _build_image_prompt(title, category, niche)
        print(f"  [IMG_GEN] Attempting Google Flow automation with prompt: {flow_prompt[:100]}...")
        
        temp_flow_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scratch", f"temp_flow_{int(time.time())}.png")
        os.makedirs(os.path.dirname(temp_flow_path), exist_ok=True)
        
        # Call Google Flow automation
        generate_google_flow_image(
            prompt_text=flow_prompt,
            output_path=temp_flow_path,
            aspect_ratio="16:9"
        )
        
        if os.path.exists(temp_flow_path):
            with open(temp_flow_path, "rb") as f:
                img_bytes = f.read()
            print("  [IMG_GEN] ✅ Google Flow image successfully generated!")
            # Clean up temp file
            try:
                os.remove(temp_flow_path)
            except Exception:
                pass
    except Exception as e:
        print(f"  [IMG_GEN] Google Flow image generation bypassed/failed: {e}")

    # ── Step 2: Fallback to Gemini Imagen ───────────────────────────────────────────
    if not img_bytes:
        print("  [IMG_GEN] Falling back to Gemini Imagen API...")
        img_bytes = generate_with_imagen(title, category, niche)

    # ── Step 3: Fallback to Pillow ──────────────────────────────────────────
    if not img_bytes:
        print("  [IMG_GEN] Falling back to Pillow image...")
        img_bytes = generate_pillow_fallback(title, category, site_name)

    if not img_bytes:
        print("  [IMG_GEN] ❌ Image generation completely failed.")
        return ""

    # ── Step 4: Upload to Cloudinary ───────────────────────────────────────
    if not CLOUDINARY_URL:
        print("  [IMG_GEN] Cloudinary not configured. Skipping upload.")
        return ""

    try:
        # Create a unique public_id from slug or title
        safe_id = re.sub(r'[^a-z0-9]+', '-', (slug or title).lower())[:60].strip('-')
        public_id = f"blog-images/{safe_id}-{abs(hash(title)) % 10000}"

        result = cloudinary.uploader.upload(
            io.BytesIO(img_bytes),
            folder="auto-blog/featured",
            public_id=public_id,
            overwrite=True,
            resource_type="image",
            transformation=[
                {"width": 1200, "height": 630, "crop": "fill", "gravity": "center"},
                {"quality": "auto:good"},
                {"fetch_format": "auto"},
            ],
        )
        cdn_url = result.get("secure_url", "")
        if cdn_url:
            print(f"  [IMG_GEN] ✅ Image uploaded to Cloudinary: {cdn_url}")
        return cdn_url

    except Exception as e:
        print(f"  [IMG_GEN] ❌ Cloudinary upload failed: {e}")
        return ""


# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("🖼️  Image Generator — Quick Test")
    print("=" * 50)

    url = generate_blog_image(
        title="Google's Gemini 2.0 Flash: The Fastest AI Model Yet",
        category="AI",
        niche="artificial intelligence",
        site_name="AI Updates Blog",
        slug="google-gemini-2-flash",
    )
    print(f"\n✅ Final URL: {url}")
