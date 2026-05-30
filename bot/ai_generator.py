import os
import google.generativeai as genai
from dotenv import load_dotenv
import re

load_dotenv()

# Configure Gemini API
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Use the latest model
model = genai.GenerativeModel('gemini-1.5-pro')

def generate_seo_article(tweet_content, niche):
    """
    Takes a raw tweet and uses Gemini to generate a high-quality, SEO-optimized, 
    human-readable blog post in HTML format.
    """
    
    prompt = f"""
    You are an expert SEO Content Writer, Copywriter, and Subject Matter Expert in the {niche} niche.
    
    I have a raw social media post (tweet) with some initial information. I want you to expand this into a 
    comprehensive, highly engaging, and 100% SEO-optimized blog article.
    
    The article must strictly bypass AI detectors. To do this:
    - Use high burstiness (mix short, punchy sentences with longer, complex ones).
    - Use high perplexity (use uncommon but accurate vocabulary, avoid predictable AI phrases like "In conclusion", "It is important to note").
    - Write with a conversational, expert, and slightly opinionated human tone.
    
    Raw Information (Tweet):
    "{tweet_content}"
    
    Requirements:
    1. Title: Create a catchy, click-worthy, H1-level SEO title (DO NOT wrap it in <h1> tags, just output it at the very top as plain text).
    2. Body: Write a detailed article (at least 600-800 words) formatted in raw HTML.
    3. Structure: Use proper <h2> and <h3> tags for subheadings. Use bullet points <ul><li> where appropriate to improve readability.
    4. Formatting: Use <strong> and <em> tags to emphasize key points. Do NOT output markdown (like **bold**), ONLY output raw HTML tags for the body.
    5. SEO Keywords: At the very end of the output, add a section starting exactly with "SEO_KEYWORDS:" followed by a comma-separated list of 5-7 long-tail keywords.
    6. Meta Description: Below the keywords, add a section starting exactly with "META_DESCRIPTION:" followed by a compelling 150-character meta description.
    
    Output Format (Strictly follow this):
    [CATCHY TITLE HERE]
    ---
    [HTML BODY HERE]
    ---
    SEO_KEYWORDS: [keyword1, keyword2, ...]
    ---
    META_DESCRIPTION: [meta description here]
    """
    
    try:
        response = model.generate_content(prompt)
        text = response.text
        
        # Parse the output
        parts = text.split('---')
        if len(parts) >= 4:
            title = parts[0].strip()
            html_content = parts[1].strip()
            
            keywords_part = parts[2].strip()
            seo_keywords = keywords_part.replace('SEO_KEYWORDS:', '').strip()
            
            meta_part = parts[3].strip()
            meta_description = meta_part.replace('META_DESCRIPTION:', '').strip()
            
            # Basic cleanup if the AI includes markdown wrappers
            html_content = re.sub(r'```html\n?', '', html_content)
            html_content = re.sub(r'```', '', html_content).strip()
            
            return {
                'title': title,
                'content_html': html_content,
                'seo_keywords': seo_keywords,
                'meta_description': meta_description
            }
        else:
            print("Failed to parse Gemini output structure.")
            print(f"Raw Output: {text}")
            return None
            
    except Exception as e:
        print(f"Error generating content with Gemini: {e}")
        return None

if __name__ == "__main__":
    # Test the AI Generator (Requires GEMINI_API_KEY in .env)
    test_tweet = "Just released a new open-source tool for programmatic SEO. It uses Next.js and Supabase to auto-generate 1000s of pages."
    result = generate_seo_article(test_tweet, "Web Development & SEO")
    if result:
        print(f"Title: {result['title']}")
        print(f"Keywords: {result['seo_keywords']}")
        print("Success!")
