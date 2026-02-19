#!/usr/bin/env python3
"""
Weekday Downtime News Scanner - Google News RSS Only
Simple, fast, and reliable
"""

import os
import json
import requests
import feedparser
from datetime import datetime

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
    'healthcare': 'https://news.google.com/rss/search?q=healthcare+when:24h&hl=en-US&gl=US&ceid=US:en',
    'tech_policy': 'https://news.google.com/rss/search?q=technology+policy+when:24h&hl=en-US&gl=US&ceid=US:en',
    'international': 'https://news.google.com/rss/search?q=international+when:24h&hl=en-US&gl=US&ceid=US:en',
    'middle_east': 'https://news.google.com/rss/search?q=middle+east+when:24h&hl=en-US&gl=US&ceid=US:en',
}


# ==================== GOOGLE NEWS RSS FETCHER ====================
def fetch_google_news():
    """Fetch stories from Google News RSS feeds"""
    
    print("📰 Fetching from Google News RSS...")
    stories = []
    
    for category, feed_url in GOOGLE_RSS_FEEDS.items():
        try:
            feed = feedparser.parse(feed_url)
            
            for entry in feed.entries[:6]:  # Get top 6 from each category
                stories.append({
                    'category_tag': category,
                    'title': entry.get('title', ''),
                    'url': entry.get('link', ''),
                    'published': entry.get('published', ''),
                    'summary': entry.get('summary', '')[:300] if entry.get('summary') else ''
                })
            
            print(f"  ✓ Found {len([s for s in stories if s['category_tag'] == category])} stories from {category}")
        
        except Exception as e:
            print(f"  ⚠️  Failed to fetch {category}: {e}")
            continue
    
    return stories


# ==================== CLAUDE ANALYSIS ====================
def analyze_with_claude(news_stories):
    """Send stories to Claude for ranking"""
    
    print(f"\n🤖 Analyzing {len(news_stories)} stories with Claude...")
    
    headers = {
        'x-api-key': CLAUDE_API_KEY,
        'anthropic-version': '2023-06-01',
        'content-type': 'application/json'
    }
    
    # Format stories for Claude
    news_text = "NEWS ARTICLES FROM LAST 24 HOURS:\n\n"
    for i, story in enumerate(news_stories, 1):
        news_text += f"{i}. [{story['category_tag']}] {story['title']}\n"
        if story.get('summary'):
            news_text += f"   {story['summary'][:200]}\n"
        news_text += f"   URL: {story['url']}\n\n"
    
    prompt = f"""You are curating stories for a political satire show (Daily Show style) targeting 18-35 year olds.

{news_text}

Analyze these stories and select the TOP 13 ranked by comedy potential and Daily Show editorial fit.

PRIORITIES:
1. Political hypocrisy - contradictions, getting caught
2. Policy impact - healthcare, economy, housing, climate
3. Corporate accountability - tech scandals, monopolies
4. Government dysfunction - bureaucratic absurdity
5. International news - foreign policy, conflicts
6. Systemic issues - inequality, corruption

SCORING:
- HIGH (80-100): Clear hypocrisy, affects millions, quotable
- MEDIUM (60-79): Important policy, corporate scandal
- LOW (40-59): Newsworthy but niche

CRITICAL - DEDUPLICATION:
- If multiple articles cover the SAME EVENT, select ONLY the best one
- Example: If 3 articles about "Senator's crypto scandal", pick the most detailed/quotable one
- Ensure your 13 stories cover 13 DIFFERENT topics/events
- Variety is key - don't cluster on one theme

For each of the top 13 stories:
- rank (1-13, #1 = most Daily Show worthy)
- headline (sharp, under 12 words, YOUR OWN Daily Show style headline)
- summary (2-3 sentences: what happened, why it matters, who's affected - YOUR OWN words)
- viral_score (1-100)
- trending_reason (why newsworthy NOW)
- comedy_angle (satirical hook: hypocrisy, absurdity, who to skewer)
- category (Political/Economic/Social/Tech/International)
- source_url (from original story)

RETURN ONLY JSON ARRAY. No markdown, no explanations. Just [ ... ]"""

    payload = {
        'model': 'claude-haiku-4-5-20251001',
        'max_tokens': 5000,
        'messages': [
            {
                'role': 'user',
                'content': prompt
            }
        ]
    }
    
    response = requests.post(CLAUDE_API_URL, headers=headers, json=payload, timeout=120)
    
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
        raise ValueError("No text from Claude")
    
    print(f"📝 Claude response preview: {json_text[:150]}...")
    
    # Clean JSON
    json_text = json_text.strip()
    
    if '```json' in json_text:
        json_text = json_text.split('```json')[1].split('```')[0]
    elif '```' in json_text:
        json_text = json_text.split('```')[1].split('```')[0]
    
    import re
    json_match = re.search(r'\[.*\]', json_text, re.DOTALL)
    if json_match:
        json_text = json_match.group(0)
    else:
        raise ValueError("No JSON array from Claude")
    
    stories = json.loads(json_text.strip())
    print(f"✅ Claude ranked {len(stories)} stories")
    
    return stories


# ==================== AIRTABLE SENDER ====================
def send_to_airtable(stories):
    """Send stories to Airtable"""
    
    print(f"\n📤 Sending {len(stories)} stories to Airtable...")
    
    headers = {
        'Authorization': f'Bearer {AIRTABLE_TOKEN}',
        'Content-Type': 'application/json'
    }
    
    today = datetime.now().strftime('%Y-%m-%d')
    success_count = 0
    
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
                'Notes': 'Source: Google News RSS'
            }
        }
        
        record['fields'] = {k: v for k, v in record['fields'].items() if v is not None}
        
        try:
            headline_preview = story.get('headline', '')[:50]
            print(f"  → #{story.get('rank')}: {headline_preview}...")
            response = requests.post(AIRTABLE_API_URL, headers=headers, json=record)
            response.raise_for_status()
            print(f"  ✓ Added")
            success_count += 1
        except Exception as e:
            print(f"  ✗ Failed: {str(e)[:100]}")
            continue
    
    print(f"\n🎉 Successfully added {success_count}/{len(stories)} stories!")


# ==================== MAIN ====================
def main():
    """Main execution"""
    
    print("=" * 70)
    print("🗞️  WEEKDAY DOWNTIME NEWS SCANNER")
    print("=" * 70)
    print(f"⏰ Running at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    if not CLAUDE_API_KEY:
        raise ValueError("CLAUDE_API_KEY not set")
    if not AIRTABLE_TOKEN:
        raise ValueError("AIRTABLE_TOKEN not set")
    if not AIRTABLE_BASE_ID:
        raise ValueError("AIRTABLE_BASE_ID not set")
    
    try:
        # Step 1: Fetch from Google News RSS
        news_stories = fetch_google_news()
        print(f"✅ Total stories fetched: {len(news_stories)}\n")
        
        # Step 2: Analyze with Claude
        ranked_stories = analyze_with_claude(news_stories)
        
        # Step 3: Send to Airtable
        send_to_airtable(ranked_stories)
        
        print("\n" + "=" * 70)
        print("✅ NEWS SCAN COMPLETE!")
        print(f"📊 Analyzed {len(news_stories)} stories")
        print(f"🎯 Selected {len(ranked_stories)} for review")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == '__main__':
    main()
