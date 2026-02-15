#!/usr/bin/env python3
"""
Weekday Downtime News Scanner
Automated daily news aggregation using Claude API and Airtable
"""

import os
import json
import requests
from datetime import datetime

# ==================== CONFIGURATION ====================
# These will be set as GitHub Secrets (environment variables)
CLAUDE_API_KEY = os.getenv('CLAUDE_API_KEY')
AIRTABLE_TOKEN = os.getenv('AIRTABLE_TOKEN')
AIRTABLE_BASE_ID = os.getenv('AIRTABLE_BASE_ID')
AIRTABLE_TABLE_NAME = 'Daily%Stories'  # Your table name

# API Endpoints
CLAUDE_API_URL = 'https://api.anthropic.com/v1/messages'
AIRTABLE_API_URL = f'https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_NAME}'


# ==================== CLAUDE API CALL ====================
def fetch_news_from_claude():
    """Call Claude API with web search to get trending news stories"""
    
    headers = {
        'x-api-key': CLAUDE_API_KEY,
        'anthropic-version': '2023-06-01',
        'content-type': 'application/json'
    }
    
    prompt = """Search the web for trending news from the last 12-24 hours. Return exactly 5 stories ranked by viral potential for a comedy news show targeting 18-35 year olds. Today is {today}.

Scoring: HIGH priority for stories trending on Twitter/X/Reddit/TikTok in last 12 hours, stories with absurdity/hypocrisy, stories affecting 18-35 year olds. SKIP stories requiring extensive background.

For each story: rank (1-5), headline (under 12 words), summary (2-3 sentences), viral_score (1-100), trending_reason (why it's viral now), comedy_angle (the joke hook), category (Political/Economic/Social/Tech/Culture), sources (array of 2 news URLs).

RETURN ONLY THE JSON ARRAY. DO NOT include any text before or after the array. DO NOT use markdown code blocks. DO NOT explain your reasoning. Your response must be ONLY valid JSON starting with [ and ending with ]. Nothing else.""".format(
        today=datetime.now().strftime('%B %d, %Y')
    )
    
    payload = {
        'model': 'claude-sonnet-4-20250514',
        'max_tokens': 3000,
        'system': 'You are a JSON API. Return only valid JSON arrays. Never include explanatory text, markdown formatting, or preamble. Your entire response must be parseable JSON starting with [ or {.',
        'tools': [
            {
                'type': 'web_search_20250305',
                'name': 'web_search'
            }
        ],
        'messages': [
            {
                'role': 'user',
                'content': prompt
            }
        ]
    }
    
    print("📡 Calling Claude API with web search...")
    response = requests.post(CLAUDE_API_URL, headers=headers, json=payload, timeout=120)
    response.raise_for_status()
    
    # Parse Claude response
    data = response.json()
    
    # Extract the final text content (last item in content array)
    content_blocks = data.get('content', [])
    
    # Find the text block (it's the last one after all tool uses)
    json_text = None
    for block in reversed(content_blocks):
        if block.get('type') == 'text':
            json_text = block.get('text', '')
            break
    
    if not json_text:
        raise ValueError("No text content found in Claude response")
    
    print(f"📝 Raw response preview: {json_text[:200]}...")
    
    # Clean up the JSON text - remove any markdown, explanatory text, etc.
    json_text = json_text.strip()
    
    # Remove markdown code blocks if present
    if '```json' in json_text:
        json_text = json_text.split('```json')[1].split('```')[0]
    elif '```' in json_text:
        json_text = json_text.split('```')[1].split('```')[0]
    
    # Find the JSON array - look for [ ... ] pattern
    import re
    json_match = re.search(r'\[.*\]', json_text, re.DOTALL)
    if json_match:
        json_text = json_match.group(0)
    else:
        print(f"❌ Could not find JSON array in response: {json_text[:500]}")
        raise ValueError("No valid JSON array found in Claude response")
    
    json_text = json_text.strip()
    
    # Parse the JSON
    try:
        stories = json.loads(json_text)
        print(f"✅ Successfully fetched {len(stories)} stories from Claude")
        return stories
    except json.JSONDecodeError as e:
        print(f"❌ JSON parsing failed. Response was: {json_text[:500]}")
        raise ValueError(f"Failed to parse JSON: {e}")


# ==================== AIRTABLE API CALL ====================
def send_to_airtable(stories):
    """Send stories to Airtable"""
    
    headers = {
        'Authorization': f'Bearer {AIRTABLE_TOKEN}',
        'Content-Type': 'application/json'
    }
    
    today = datetime.now().strftime('%Y-%m-%d')
    
    for story in stories:
        # Map story data to Airtable fields
        record = {
            'fields': {
                'Date': today,
                'Rank': story.get('rank'),
                'Headline': story.get('headline'),
                'Summary': story.get('summary'),
                'Viral Score': story.get('viral_score'),
                'Why Trending': story.get('trending_reason'),
                'Comedy Angle': story.get('comedy_angle'),
                'Category': story.get('category'),
                'Source 1': story.get('sources', [None])[0] if len(story.get('sources', [])) > 0 else None,
                'Source 2': story.get('sources', [None])[1] if len(story.get('sources', [])) > 1 else None,
                'Status': 'To Review'
            }
        }
        
        # Remove None values
        record['fields'] = {k: v for k, v in record['fields'].items() if v is not None}
        
        print(f"📤 Sending story #{story.get('rank')}: {story.get('headline')[:50]}...")
        response = requests.post(AIRTABLE_API_URL, headers=headers, json=record)
        response.raise_for_status()
        print(f"✅ Story #{story.get('rank')} added to Airtable")
    
    print(f"\n🎉 All {len(stories)} stories successfully added to Airtable!")


# ==================== MAIN EXECUTION ====================
def main():
    """Main execution function"""
    
    print("=" * 60)
    print("🗞️  WEEKDAY DOWNTIME NEWS SCANNER")
    print("=" * 60)
    print(f"⏰ Running at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # Validate environment variables
    if not CLAUDE_API_KEY:
        raise ValueError("CLAUDE_API_KEY environment variable not set")
    if not AIRTABLE_TOKEN:
        raise ValueError("AIRTABLE_TOKEN environment variable not set")
    if not AIRTABLE_BASE_ID:
        raise ValueError("AIRTABLE_BASE_ID environment variable not set")
    
    try:
        # Step 1: Fetch news from Claude
        stories = fetch_news_from_claude()
        
        # Step 2: Send to Airtable
        send_to_airtable(stories)
        
        print("\n" + "=" * 60)
        print("✅ NEWS SCAN COMPLETE!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        raise


if __name__ == '__main__':
    main()
