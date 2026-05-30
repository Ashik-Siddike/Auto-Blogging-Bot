import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

url: str = os.getenv("SUPABASE_URL")
key: str = os.getenv("SUPABASE_SERVICE_KEY")

if not url or not key:
    raise ValueError("Missing Supabase credentials in .env file.")

supabase: Client = create_client(url, key)

def get_active_sources():
    """
    Fetches all active Twitter handles to scrape from the database.
    """
    try:
        response = supabase.table("blog_sources").select("*").eq("is_active", True).execute()
        return response.data
    except Exception as e:
        print(f"Error fetching sources: {e}")
        return []

def is_tweet_processed(tweet_id):
    """
    Checks if a tweet has already been converted into a blog post.
    """
    try:
        response = supabase.table("blog_posts").select("id").eq("original_tweet_id", str(tweet_id)).execute()
        return len(response.data) > 0
    except Exception as e:
        print(f"Error checking if tweet processed: {e}")
        return False

def save_blog_post(source_id, tweet_id, tweet_url, article_data):
    """
    Saves the generated SEO article into the database.
    """
    try:
        data = {
            "source_id": source_id,
            "original_tweet_id": str(tweet_id),
            "original_tweet_url": tweet_url,
            "title": article_data['title'],
            "content_html": article_data['content_html'],
            "seo_keywords": article_data['seo_keywords'],
            "meta_description": article_data['meta_description'],
            "status": "published" # or "draft" depending on preference
        }
        
        response = supabase.table("blog_posts").insert(data).execute()
        print(f"Successfully saved blog post: {article_data['title']}")
        return True
    except Exception as e:
        print(f"Error saving blog post: {e}")
        return False

if __name__ == "__main__":
    # Test connection
    sources = get_active_sources()
    print(f"Found {len(sources)} active sources.")
