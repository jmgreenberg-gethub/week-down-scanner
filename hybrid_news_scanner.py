#!/usr/bin/env python3
"""
Weekday Downtime News Scanner - HYBRID VERSION
Uses Reddit API + Google News RSS + Claude for analysis
"""

import os
import json
import requests
import feedparser
from datetime import datetime
from urllib.parse import quote

# ==================== CONFIGURATION ====================
CLAUDE_API_KEY = os.getenv('CLAUDE_API_KEY')
AIRTABLE_TOKEN = os.getenv('AIRTABLE_TOKEN')
AIRTABLE_BASE_ID = os.getenv('AIRTABLE_BASE_ID')
AIRTABLE_TABLE_NAME = 'tblyfNKv9fNn88Wax'

# API Endpoints
CLAUDE_API_URL = 'https://api.anthropic.com/v1/messages'
AIRTABLE_API_URL = f'https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_NAME}'

# Google News RSS Feeds (last 24 hours)
GOOGLE_RSS_FEEDS = {
    'politics': 'https://news.google.com/rss/search?q=politics+when:24h&hl=en-US&gl=US&ceid=US:en',
    'economy': 'https://news.google.com/rss/search?q=economy+when:24h&hl=en-US&gl=US&ceid=US:en',
    'tech': 'https://news.google.com/rss/search?q=technology+policy+when:24h&hl=en-US&gl=US&ceid=US:en',
    'international': 'https://news.google.com/rss/search?q=international+when:24h&hl=en-US&gl=US&ceid=US:en',
}

# Reddit Subreddits to monitor
REDDIT_SUBS = [
    'politics',
    'news', 
    'worldnews'
]

# Reddit Viral Watch - for pure engagement tracking
REDDIT_VIRAL_SUBS = [
    'all',
    'meirl',
    'facepalm',
    'WhitePeopleTwitter',
    'BlackPeopleTwitter',
    'LateStageCapitalism'
]


# ==================== REDDIT FETCHER ====================
def fetch_reddit_stories():
    """Fetch trending stories from Reddit"""
    
    print("📱 Fetching from Reddit...")
    stories = []
    
    headers = {
        'User-Agent': 'WeekdayDowntime/1.0'
    }
    
    for subreddit in REDDIT_SUBS:
        try:
            url = f'https://www.reddit.com/r/{subreddit}/hot.json?limit=10'
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            for post in data.get('data', {}).get('children', []):
                post_data = post.get('data', {})
                
                # Skip stickied posts and low-engagement posts
                if post_data.get('stickied') or post_data.get('score', 0) < 100:
                    continue
                
                stories.append({
                    'source': 'Reddit',
                    'subreddit': f"r/{subreddit}",
                    'title': post_data.get('title', ''),
                    'url': f"https://reddit.com{post_data.get('permalink', '')}",
                    'score': post_data.get('num_comments', 0),
                    'engagement': f"{post_data.get('score', 0)} upvotes, {post_data.get('num_comments', 0)} comments",
                    'category': 'Political' if subreddit == 'politics' else 'Social'
                })
            
            print(f"  ✓ Found {len([s for s in stories if s['subreddit'] == f'r/{subreddit}'])} stories from r/{subreddit}")
        
        except Exception as e:
            print(f"  ⚠️  Failed to fetch r/{subreddit}: {e}")
            continue
    
    return stories


def fetch_viral_reddit():
    """Fetch top viral posts from Reddit for 'Viral Watch' section"""
    
    print("🔥 Fetching viral content from Reddit...")
    viral_posts = []
    
    headers = {
        'User-Agent': 'WeekdayDowntime/1.0'
    }
    
    for subreddit in REDDIT_VIRAL_SUBS:
        try:
            url = f'https://www.reddit.com/r/{subreddit}/hot.json?limit=5'
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            for post in data.get('data', {}).get('children', []):
                post_data = post.get('data', {})
                
                # Skip stickied, NSFW, or very low engagement
                if post_data.get('stickied') or post_data.get('over_18') or post_data.get('score', 0) < 500:
                    continue
                
                viral_posts.append({
                    'source': 'Reddit',
                    'subreddit': f"r/{subreddit}",
                    'title': post_data.get('title', ''),
                    'url': f"https://reddit.com{post_data.get('permalink', '')}",
                    'score': post_data.get('score', 0),
                    'comments': post_data.get('num_comments', 0),
                    'engagement': f"{post_data.get('score', 0)} upvotes, {post_data.get('num_comments', 0)} comments",
                    'category': 'Culture'
                })
        
        except Exception as e:
            print(f"  ⚠️  Failed to fetch r/{subreddit}: {e}")
            continue
    
    # Sort by engagement (upvotes + comments) and get top 3
    viral_posts.sort(key=lambda x: x['score'] + x['comments'], reverse=True)
    top_viral = viral_posts[:3]
    
    print(f"  ✓ Found {len(top_viral)} viral posts")
    for post in top_viral:
        print(f"    → {post['title'][:60]}... ({post['engagement']})")
    
    return top_viral


# ==================== GOOGLE NEWS RSS FETCHER ====================
def fetch_google_news():
    """Fetch stories from Google News RSS feeds"""
    
    print("📰 Fetching from Google News RSS...")
    stories = []
    
    for category, feed_url in GOOGLE_RSS_FEEDS.items():
        try:
            feed = feedparser.parse(feed_url)
            
            for entry in feed.entries[:8]:  # Get top 8 from each category
                stories.append({
                    'source': 'Google News',
                    'category_tag': category,
                    'title': entry.get('title', ''),
                    'url': entry.get('link', ''),
                    'published': entry.get('published', ''),
                    'summary': entry.get('summary', '')[:200] if entry.get('summary') else '',
                    'category': category.capitalize()
                })
            
            print(f"  ✓ Found {len([s for s in stories if s['category_tag'] == category])} stories from {category}")
        
        except Exception as e:
            print(f"  ⚠️  Failed to fetch {category}: {e}")
            continue
    
    return stories


# ==================== CLAUDE ANALYSIS ====================
def analyze_with_claude(reddit_stories, news_stories, viral_posts):
    """Send all stories to Claude for ranking and analysis"""
    
    print(f"\n🤖 Analyzing {len(reddit_stories) + len(news_stories)} stories with Claude...")
    
    headers = {
        'x-api-key': CLAUDE_API_KEY,
        'anthropic-version': '2023-06-01',
        'content-type': 'application/json'
    }
    
    # Format Reddit stories for Claude
    reddit_text = "REDDIT TRENDING POSTS:\n"
    for i, story in enumerate(reddit_stories[:15], 1):
        reddit_text += f"{i}. [{story['subreddit']}] {story['title']}\n"
        reddit_text += f"   Engagement: {story['engagement']}\n"
        reddit_text += f"   URL: {story['url']}\n\n"
    
    # Format Google News stories for Claude
    news_text = "GOOGLE NEWS ARTICLES:\n"
    for i, story in enumerate(news_stories[:30], 1):
        news_text += f"{i}. [{story['category_tag']}] {story['title']}\n"
        if story.get('summary'):
            news_text += f"   Summary: {story['summary']}\n"
        news_text += f"   URL: {story['url']}\n\n"
    
    # Format viral posts
    viral_text = "\n--- VIRAL WATCH (These 3 are already selected for pure virality) ---\n"
    for i, post in enumerate(viral_posts, 1):
        viral_text += f"{i}. [{post['subreddit']}] {post['title']}\n"
        viral_text += f"   {post['engagement']}\n"
        viral_text += f"   URL: {post['url']}\n\n"
    
    
    prompt = f"""You are a content curator for a political satire show (Daily Show/Last Week Tonight style) targeting 18-35 year olds.

Below are trending Reddit posts and Google News articles from the last 24 hours. Analyze ALL of them and return the TOP 13 stories ranked by comedy potential and editorial fit.

{reddit_text}

{news_text}

{viral_text}

NOTE: The 3 viral watch posts listed above are ALREADY SELECTED for pure engagement. You do NOT need to rank them. Just focus on selecting the best 13 editorial stories from the Reddit/Google News lists above.

EDITORIAL PRIORITIES (Daily Show style):
1. POLITICAL HYPOCRISY - Politicians contradicting themselves, getting caught
2. POLICY IMPACT - Healthcare, economy, housing, student debt, climate
3. CORPORATE ACCOUNTABILITY - Tech scandals, monopolies, worker exploitation
4. GOVERNMENT DYSFUNCTION - Bureaucratic absurdity, wasteful spending
5. INTERNATIONAL NEWS - Foreign policy blunders, global conflicts
6. SYSTEMIC ISSUES - Inequality, corruption, institutional failures

SCORING CRITERIA:
- HIGH (80-100): Clear hypocrisy/contradiction, affects millions, has quotable moment
- MEDIUM (60-79): Important policy, corporate scandal, international significance  
- LOW (40-59): Newsworthy but niche

CRITICAL RULES:
1. **IGNORE THE SOURCE** - Don't favor Reddit or Google News. Judge ONLY on story substance.
2. **Reddit engagement ≠ quality** - High upvotes might just mean it's clickbait. Focus on editorial merit.
3. **Prefer credible news stories** - If both Reddit and Google News cover the same event, prefer the Google News version (better sourcing).
4. **Substance > Virality** - A healthcare policy affecting 40M people > a viral celebrity drama with 10K upvotes.
5. **Mix sources** - Aim for a balanced mix of Reddit and Google News in your top 13, not all from one source.

For EACH of the top 13 stories, provide:
- rank (1-13, based on Daily Show editorial fit, NOT platform)
- headline (sharp Daily Show-style headline, under 12 words - WRITE YOUR OWN, don't copy)
- original_source (Reddit or Google News)
- summary (2-3 sentences explaining: what happened, why it matters, who's affected - WRITE YOUR OWN synthesis)
- viral_score (1-100, based on editorial criteria above)
- trending_reason (why this is newsworthy RIGHT NOW - IGNORE Reddit upvotes, focus on actual news hook)
- comedy_angle (the satirical hook: hypocrisy, absurdity, who to skewer, the "can you believe this?" moment)
- category (Political/Economic/Social/Tech/International)
- source_url (the URL from the original story)

RETURN ONLY A JSON ARRAY. No explanations, no markdown, no code blocks. Just [ ... ] with the 13 stories."""

    payload = {
        'model': 'claude-sonnet-4-20250514',
        'max_tokens': 6000,
        'messages': [
            {
                'role': 'user',
                'content': prompt
            }
        ]
    }
    
    response = requests.post(CLAUDE_API_URL, headers=headers, json=payload, timeout=90)
    
    if response.status_code != 200:
        print(f"❌ Claude API Error: {response.status_code}")
        print(f"Response: {response.text[:500]}")
    
    response.raise_for_status()
    
    # Parse response
    data = response.json()
    content_blocks = data.get('content', [])
    
    json_text = None
    for block in content_blocks:
        if block.get('type') == 'text':
            json_text = block.get('text', '')
            break
    
    if not json_text:
        raise ValueError("No text content from Claude")
    
    print(f"📝 Claude response preview: {json_text[:200]}...")
    
    # Clean and parse JSON
    json_text = json_text.strip()
    
    # Remove markdown if present
    if '```json' in json_text:
        json_text = json_text.split('```json')[1].split('```')[0]
    elif '```' in json_text:
        json_text = json_text.split('```')[1].split('```')[0]
    
    # Extract JSON array
    import re
    json_match = re.search(r'\[.*\]', json_text, re.DOTALL)
    if json_match:
        json_text = json_match.group(0)
    else:
        print(f"❌ Could not find JSON array: {json_text[:500]}")
        raise ValueError("No valid JSON array from Claude")
    
    stories = json.loads(json_text.strip())
    print(f"✅ Claude ranked {len(stories)} stories")
    
    return stories


# ==================== AIRTABLE SENDER ====================
def send_to_airtable(stories, viral_posts):
    """Send stories to Airtable"""
    
    print(f"\n📤 Sending to Airtable...")
    
    headers = {
        'Authorization': f'Bearer {AIRTABLE_TOKEN}',
        'Content-Type': 'application/json'
    }
    
    today = datetime.now().strftime('%Y-%m-%d')
    success_count = 0
    
    # Send the 13 editorial picks
    for story in stories:
        if not story.get('headline'):
            print(f"  ⚠️  Skipping story #{story.get('rank', '?')} - missing headline")
            continue
        
        record = {
            'fields': {
                'Date': today,
                'Rank': story.get('rank', 0),
                'Headline': story.get('headline', 'Untitled')[:255],
                'Summary': story.get('summary', '')[:5000],
                'Viral Score': story.get('viral_score', 50),
                'Why Trending': story.get('trending_reason', '')[:5000],
                'Comedy Angle': story.get('comedy_angle', '')[:5000],
                'Category': story.get('category', 'Other'),
                'Source 1': story.get('source_url', ''),
                'Status': 'To Review',
                'Notes': f"Source: {story.get('original_source', 'Unknown')}"
            }
        }
        
        # Remove None values
        record['fields'] = {k: v for k, v in record['fields'].items() if v is not None}
        
        try:
            print(f"  → Story #{story.get('rank')}: {story.get('headline', '')[:50]}...")
            response = requests.post(AIRTABLE_API_URL, headers=headers, json=record)
            response.raise_for_status()
            print(f"  ✓ Added")
            success_count += 1
        except Exception as e:
            print(f"  ✗ Failed: {str(e)}")
            continue
    
    # Send the 3 viral watch posts
    print(f"\n🔥 Adding Viral Watch posts...")
    for i, post in enumerate(viral_posts, 14):  # Start at rank 14
        record = {
            'fields': {
                'Date': today,
                'Rank': i,
                'Headline': f"🔥 VIRAL: {post['title'][:200]}",
                'Summary': f"Trending on {post['subreddit']} with {post['engagement']}. Pure virality pick - not editorial selection.",
                'Viral Score': 100,
                'Why Trending': f"Top post on {post['subreddit']} - massive social media engagement",
                'Comedy Angle': "Use this to stay culturally relevant or find unexpected angles",
                'Category': post.get('category', 'Culture'),
                'Source 1': post['url'],
                'Status': 'Viral Watch',
                'Notes': f"Source: Reddit Viral Watch | {post['subreddit']}"
            }
        }
        
        try:
            print(f"  → Viral #{i}: {post['title'][:50]}...")
            response = requests.post(AIRTABLE_API_URL, headers=headers, json=record)
            response.raise_for_status()
            print(f"  ✓ Added")
            success_count += 1
        except Exception as e:
            print(f"  ✗ Failed: {str(e)}")
            continue
    
    print(f"\n🎉 Successfully added {success_count}/{len(stories) + len(viral_posts)} total stories!")
    print(f"   📰 Editorial: {len(stories)} stories")
    print(f"   🔥 Viral Watch: {len(viral_posts)} posts")


# ==================== MAIN ====================
def main():
    """Main execution"""
    
    print("=" * 70)
    print("🗞️  WEEKDAY DOWNTIME NEWS SCANNER - HYBRID VERSION")
    print("=" * 70)
    print(f"⏰ Running at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # Validate environment variables
    if not CLAUDE_API_KEY:
        raise ValueError("CLAUDE_API_KEY not set")
    if not AIRTABLE_TOKEN:
        raise ValueError("AIRTABLE_TOKEN not set")
    if not AIRTABLE_BASE_ID:
        raise ValueError("AIRTABLE_BASE_ID not set")
    
    try:
        # Step 1: Fetch from Reddit (editorial)
        reddit_stories = fetch_reddit_stories()
        print(f"✅ Total Reddit stories: {len(reddit_stories)}\n")
        
        # Step 2: Fetch from Google News RSS
        news_stories = fetch_google_news()
        print(f"✅ Total Google News stories: {len(news_stories)}\n")
        
        # Step 3: Fetch viral content
        viral_posts = fetch_viral_reddit()
        print(f"✅ Total Viral Watch posts: {len(viral_posts)}\n")
        
        # Step 4: Analyze with Claude (editorial picks only)
        ranked_stories = analyze_with_claude(reddit_stories, news_stories, viral_posts)
        
        # Step 5: Send to Airtable (editorial + viral)
        send_to_airtable(ranked_stories, viral_posts)
        
        print("\n" + "=" * 70)
        print("✅ NEWS SCAN COMPLETE!")
        print(f"📊 Analyzed {len(reddit_stories) + len(news_stories)} stories")
        print(f"🎯 Selected {len(ranked_stories)} editorial picks")
        print(f"🔥 Added {len(viral_posts)} viral watch posts")
        print(f"📋 Total in Airtable: {len(ranked_stories) + len(viral_posts)} stories")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == '__main__':
    main()
