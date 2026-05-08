#!/usr/bin/env python3
"""Quick test script to verify the scanner works."""

import asyncio
import sys

from src.scraper import TwitterScraper
from src.config import get_settings


async def main():
    """Run a quick test scan."""
    settings = get_settings()
    print(f"Testing with handles: {settings.tracked_handles[:3]}")

    scraper = TwitterScraper()
    tweets = []

    try:
        await scraper.start()
        print("Browser started successfully")

        # Test fetch one handle
        test_handle = settings.tracked_handles[0] if settings.tracked_handles else "elonmusk"
        print(f"Fetching tweets from @{test_handle}...")

        tweets = await scraper.fetch_user_tweets(test_handle, max_tweets=5)
        print(f"Fetched {len(tweets)} tweets")

        for tweet in tweets[:3]:
            print(f"  - {tweet.get('text', '')[:80]}...")
            print(f"    Tickers: {tweet.get('tickers', [])}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    finally:
        await scraper.stop()

    return 0 if tweets else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))