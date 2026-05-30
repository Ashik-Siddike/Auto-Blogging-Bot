import requests
from bs4 import BeautifulSoup
import time
import random

# A list of public Nitter instances to rotate through in case one is down
NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.cz",
    "https://nitter.privacydev.net",
    "https://nitter.poast.org"
]

def get_latest_tweets(handle, limit=5):
    """
    Fetches the latest tweets for a given Twitter handle using Nitter RSS feeds.
    This avoids the need for official Twitter API keys and handles rate limits.
    """
    for instance in NITTER_INSTANCES:
        rss_url = f"{instance}/{handle}/rss"
        try:
            # Rotate user agents to prevent blocking
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = requests.get(rss_url, headers=headers, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'xml')
                items = soup.find_all('item')
                
                tweets = []
                for item in items[:limit]:
                    title = item.title.text if item.title else ""
                    # Ignore retweets and replies for high-quality blogs
                    if title.startswith("RT by") or title.startswith("R to"):
                        continue
                        
                    link = item.link.text if item.link else ""
                    description = item.description.text if item.description else ""
                    pub_date = item.pubDate.text if item.pubDate else ""
                    
                    # Extract the tweet ID from the URL (e.g., https://twitter.com/handle/status/123456789)
                    tweet_id = link.split('/')[-1].split('#')[0] if link else str(random.randint(1000, 9999))
                    
                    # Clean up the Nitter link to a real Twitter link for reference
                    real_link = link.replace(instance, "https://twitter.com")
                    
                    tweets.append({
                        'id': tweet_id,
                        'url': real_link,
                        'content': title + "\n\n" + description,
                        'pub_date': pub_date
                    })
                
                if tweets:
                    return tweets
        except Exception as e:
            print(f"Failed to fetch from {instance} for {handle}: {e}")
            continue
            
    print(f"Could not fetch tweets for {handle} from any instance.")
    return []

if __name__ == "__main__":
    # Test the scraper
    print(get_latest_tweets("OpenAI", limit=2))
