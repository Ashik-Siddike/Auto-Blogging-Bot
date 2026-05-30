import time
from bot.scraper import get_latest_tweets
from bot.ai_generator import generate_seo_article
from bot.db_manager import get_active_sources, is_tweet_processed, save_blog_post

def run_bot():
    print("🚀 Starting Auto Blog Management System Bot...")
    
    sources = get_active_sources()
    if not sources:
        print("No active sources found in database. Exiting.")
        return
        
    for source in sources:
        handle = source.get('twitter_handle')
        niche = source.get('niche')
        source_id = source.get('id')
        
        print(f"\n🔍 Processing source: @{handle} (Niche: {niche})")
        
        tweets = get_latest_tweets(handle, limit=3)
        if not tweets:
            print(f"No tweets found for @{handle}.")
            continue
            
        for tweet in tweets:
            tweet_id = tweet['id']
            tweet_url = tweet['url']
            tweet_content = tweet['content']
            
            print(f"Checking tweet ID: {tweet_id}")
            
            if is_tweet_processed(tweet_id):
                print(f"Tweet {tweet_id} already processed. Skipping.")
                continue
                
            print(f"✍️ Generating AI article for tweet {tweet_id}...")
            # To avoid rate limits, wait a few seconds before hitting Gemini
            time.sleep(2)
            
            article_data = generate_seo_article(tweet_content, niche)
            
            if article_data:
                success = save_blog_post(source_id, tweet_id, tweet_url, article_data)
                if success:
                    print(f"✅ Successfully created and saved blog post for tweet {tweet_id}!")
                else:
                    print(f"❌ Failed to save blog post to database.")
            else:
                print(f"❌ AI Generation failed for tweet {tweet_id}.")
                
    print("\n🏁 Auto Blog Bot finished execution.")

if __name__ == "__main__":
    run_bot()
