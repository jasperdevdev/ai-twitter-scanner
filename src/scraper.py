"""Core Twitter/X scanner with Playwright and stealth capabilities."""

import asyncio
import json
import random
import re
import time
from datetime import datetime, timedelta
from typing import Optional, Callable
from pathlib import Path

from loguru import logger
from playwright.async_api import async_playwright, Error as PlaywrightError, Page, Response, Request
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import ScannerSettings, get_settings
from src.session import SessionManager
from src.proxy import ProxyManager, IPRotation


class GraphQLInterceptor:
    """Intercept GraphQL/XHR requests to capture clean JSON data."""
    
    def __init__(self):
        self.tweet_data: dict = {}
        self.user_data: dict = {}
        self.entries: list = []
        
    def setup_interceptor(self, page: Page) -> None:
        """Set up request/response interception for GraphQL endpoints."""
        
        @page.on("response")
        async def handle_response(response: Response):
            url = response.url
            try:
                # Check for Twitter GraphQL endpoints
                if "graphql" in url and "Tweet" in url:
                    await self._handle_tweet_graphql(response)
                elif "graphql" in url and "User" in url:
                    await self._handle_user_graphql(response)
                elif "/i/api" in url:
                    await self._handle_iapi_response(response)
            except Exception as e:
                logger.debug(f"Interceptor error for {url}: {e}")
        
    async def _handle_tweet_graphql(self, response: Response) -> None:
        """Handle Tweet GraphQL responses."""
        try:
            body = await response.json()
            # Extract tweet data from GraphQL response
            if "data" in body:
                data = body.get("data", {})
                if "threaded_conversation_with_injections" in data:
                    instructions = data["threaded_conversation_with_injections"].get("instructions", [])
                    for instruction in instructions:
                        if instruction.get("type") == "TimelineAddEntries":
                            entries = instruction.get("entries", [])
                            for entry in entries:
                                if entry.get("entryId", "").startswith("tweet-"):
                                    self.entries.append(entry)
                elif "tweet" in data:
                    self.tweet_data = data["tweet"]
        except Exception:
            pass
            
    async def _handle_user_graphql(self, response: Response) -> None:
        """Handle User GraphQL responses."""
        try:
            body = await response.json()
            if "data" in body:
                self.user_data = body.get("data", {})
        except Exception:
            pass
            
    async def _handle_iapi_response(self, response: Response) -> None:
        """Handle /i/api responses."""
        try:
            body = await response.json()
            if "data" in body:
                self.entries.append(body.get("data", {}))
        except Exception:
            pass
            
    def get_tweets_from_entries(self) -> list[dict]:
        """Extract structured tweet data from intercepted entries."""
        tweets = []
        for entry in self.entries:
            content = entry.get("content", {})
            item_content = content.get("itemContent", {})
            
            # Handle different response formats
            tweet_result = item_content.get("tweet_results", {}).get("result", {})
            if not tweet_result:
                tweet_result = item_content
                
            if not tweet_result:
                continue
                
            # Extract core data
            legacy = tweet_result.get("legacy", {})
            core = tweet_result.get("core", {}).get("user_results", {}).get("result", {}).get("legacy", {})
            
            if legacy:
                # Parse engagement counts
                like_count = legacy.get("favorite_count", 0)
                retweet_count = legacy.get("retweet_count", 0)
                reply_count = legacy.get("reply_count", 0)
                
                # Detect tickers
                text = legacy.get("full_text", "")
                tickers = self._detect_tickers(text)
                
                # Get media
                media_urls = []
                media = legacy.get("entities", {}).get("media", [])
                for m in media:
                    media_urls.append(m.get("media_url_https", ""))
                    
                tweets.append({
                    "timestamp": legacy.get("created_at"),
                    "author": legacy.get("user", {}).get("screen_name", ""),
                    "text": text,
                    "likes": like_count,
                    "retweets": retweet_count,
                    "replies": reply_count,
                    "tickers": tickers,
                    "media_urls": media_urls,
                    "fetched_at": datetime.utcnow().isoformat() + "Z",
                })
                
        return tweets
        
    def _detect_tickers(self, text: str) -> list[str]:
        """Detect stock tickers in text."""
        ticker_pattern = r"\$([A-Z]{1,5})\b"
        matches = re.findall(ticker_pattern, text.upper())
        false_positives = {"A", "I", "TO", "IF", "IN", "ON", "AS", "AT", "IS", "IT", "OR", "AN", "BE", "ME", "SO"}
        return list(set(matches) - false_positives)
        
    def clear(self) -> None:
        """Clear captured data."""
        self.tweet_data = {}
        self.user_data = {}
        self.entries = []


class TwitterScraper:
    """Main scraper class for Twitter/X."""

    def __init__(self, settings: Optional[ScannerSettings] = None):
        self.settings = settings or get_settings().scanner
        self.twitter_settings = get_settings().twitter
        self.browser = None
        self.context = None
        self.page = None
        self.playwright = None
        self._session_active = False
        self.session_manager = None
        self.proxy_manager = None
        self.ip_rotation = None
        self.interceptor = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()

    async def start(self) -> None:
        """Initialize the browser and context."""
        logger.info("Starting Twitter scraper...")
        self.playwright = await async_playwright().start()

        # Initialize managers
        self.session_manager = SessionManager()
        self.proxy_manager = ProxyManager()
        self.ip_rotation = IPRotation()
        self.interceptor = GraphQLInterceptor()

        # Get proxy if enabled
        proxy_url = None
        if self.proxy_manager.settings.enabled:
            proxy_url = await self.proxy_manager.get_proxy()
            if proxy_url:
                logger.info(f"Using proxy: {proxy_url}")

        # Launch browser with stealth settings
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-accelerated-2d-canvas",
            "--disable-gpu",
        ]

        if self.settings.headless:
            launch_args.append("--headless=new")

        self.browser = await self.playwright.chromium.launch(
            headless=self.settings.headless,
            args=launch_args,
            slow_mo=50 if not self.settings.headless else 0,
            proxy={"server": proxy_url} if proxy_url else None,
        )
        logger.info("Browser launched with stealth settings")

        # Create context with stealth properties
        user_agent = self.ip_rotation.get_random_user_agent()
        self.context = await self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=user_agent,
            locale="en-US",
            timezone_id="America/New_York",
            permissions=["geolocation", "notifications"],
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )

        # Try to load saved session
        if self.session_manager:
            self.session_manager.apply_session(self.context)

        # Apply stealth plugin for anti-detection
        await self._apply_stealth_scripts()

        self.page = await self.context.new_page()
        
        # Set up GraphQL interceptor for cleaner data extraction
        self.interceptor.setup_interceptor(self.page)
        
        self._session_active = True
        logger.info("Twitter scraper started successfully")

    async def stop(self) -> None:
        """Clean up resources."""
        logger.info("Stopping Twitter scraper...")
        self._session_active = False

        # Save session before closing
        if self.session_manager and self.context:
            self.session_manager.save_session(self.context)

        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

        logger.info("Twitter scraper stopped")

    async def _apply_stealth_scripts(self) -> None:
        """Apply stealth scripts to avoid detection."""
        try:
            await self.context.add_init_script(
                """
                // Hide webdriver property
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                // Fake plugins
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                // Fake languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en']
                });
                // Handle permissions query
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
                // Override chrome runtime
                if (window.chrome) {
                    window.chrome.runtime = { connect: () => {}, sendMessage: () => {} };
                }
                // Mask automation flags
                window.navigator.permissions = {
                    query: window.navigator.permissions.query,
                    "query": window.navigator.permissions.query
                };
                """
            )
            logger.info("Applied stealth scripts")
        except Exception as e:
            logger.warning(f"Could not apply stealth scripts: {e}")

    async def _human_delay(self) -> None:
        """Apply random human-like delay between actions."""
        delay = random.uniform(self.settings.min_delay, self.settings.max_delay)
        await asyncio.sleep(delay)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def fetch_user_tweets(
        self, username: str, max_tweets: int = 20
    ) -> list[dict]:
        """Fetch tweets from a user's profile using GraphQL interception."""
        if not self._session_active:
            await self.start()

        tweets = []
        url = f"https://x.com/{username}"

        logger.info(f"Fetching tweets from @{username}")

        try:
            # Clear previous interceptor data
            if self.interceptor:
                self.interceptor.clear()
                
            await self.page.goto(
                url,
                wait_until="networkidle",
                timeout=self.settings.timeout,
            )

            await self._human_delay()

            # First try: Get tweets from intercepted GraphQL responses
            if self.interceptor:
                graphql_tweets = self.interceptor.get_tweets_from_entries()
                if graphql_tweets:
                    logger.info(f"Extracted {len(graphql_tweets)} tweets via GraphQL interception")
                    return graphql_tweets[:max_tweets]
            
            # Fallback: Use DOM parsing with stable selectors
            try:
                await self.page.wait_for_selector(
                    '[data-testid="cellInnerDiv"]',
                    timeout=10000,
                )
            except PlaywrightError:
                logger.warning(f"No tweets found for @{username}")
                return tweets

            # Extract tweet data using multiple strategies
            tweet_elements = await self.page.locator(
                '[data-testid="cellInnerDiv"]'
            ).all()

            for elem in tweet_elements[:max_tweets]:
                try:
                    tweet_data = await self._extract_tweet_data(elem, username)
                    if tweet_data:
                        tweets.append(tweet_data)
                except Exception as e:
                    logger.debug(f"Error extracting tweet: {e}")
                    continue

            logger.info(f"Extracted {len(tweets)} tweets from @{username}")

        except PlaywrightError as e:
            logger.error(f"Error fetching @{username}: {e}")
            raise

        return tweets

    async def fetch_tweet_by_url(self, tweet_url: str) -> Optional[dict]:
        """Fetch a single tweet by URL using GraphQL interception."""
        if not self._session_active:
            await self.start()
            
        if self.interceptor:
            self.interceptor.clear()
            
        logger.info(f"Fetching tweet: {tweet_url}")
        
        try:
            await self.page.goto(
                tweet_url,
                wait_until="networkidle",
                timeout=self.settings.timeout,
            )
            
            await self._human_delay()
            
            # Try GraphQL interception first
            if self.interceptor:
                graphql_tweets = self.interceptor.get_tweets_from_entries()
                if graphql_tweets:
                    return graphql_tweets[0]
                    
            # Fallback to DOM parsing
            # Extract from page URL (format: https://x.com/user/status/ID)
            parts = tweet_url.split("/status/")
            if len(parts) == 2:
                tweet_id = parts[1].split("?")[0]
                
                try:
                    article = await self.page.wait_for_selector(
                        f'[data-testid="tweet-{tweet_id}"]',
                        timeout=5000,
                    )
                    if article:
                        return await self._extract_tweet_data(article, "")
                except PlaywrightError:
                    pass
                    
            # Generic fallback
            cell = self.page.locator('[data-testid="cellInnerDiv"]').first
            if await cell.count() > 0:
                return await self._extract_tweet_data(await cell.first, "")
                
        except Exception as e:
            logger.error(f"Error fetching tweet {tweet_url}: {e}")
            
        return None

    async def _extract_tweet_data(
        self, element, username: str
    ) -> Optional[dict]:
        """Extract structured data from a tweet element."""
        try:
            # Get tweet text
            text_elem = element.locator('[data-testid="tweetText"]')
            text = await text_elem.inner_text() if await text_elem.count() > 0 else ""

            # Get time posted
            time_elem = element.locator("time")
            datetime_str = (
                await time_elem.get_attribute("datetime")
                if await time_elem.count() > 0
                else None
            )

            # Get engagement stats
            like_elem = element.locator('[data-testid="tweetLikeCount"]')
            like_text = (
                await like_elem.inner_text() if await like_elem.count() > 0 else "0"
            )

            retweet_elem = element.locator('[data-testid="tweetRetweetCount"]')
            retweet_text = (
                await retweet_elem.inner_text()
                if await retweet_elem.count() > 0
                else "0"
            )

            reply_elem = element.locator('[data-testid="tweetReplyCount"]')
            reply_text = (
                await reply_elem.inner_text() if await reply_elem.count() > 0 else "0"
            )

            # Parse engagement counts
            likes = self._parse_count(like_text)
            retweets = self._parse_count(retweet_text)
            replies = self._parse_count(reply_text)

            # Detect tickers
            tickers = self._detect_tickers(text)

            # Get media URLs if present
            media_urls = []
            media_container = element.locator('[data-testid="tweetPhoto"]')
            if await media_container.count() > 0:
                images = media_container.locator("img")
                count = await images.count()
                for i in range(count):
                    src = await images.nth(i).get_attribute("src")
                    if src:
                        media_urls.append(src)

            # Get video if present
            video_container = element.locator('[data-testid="videoPlayer"]')
            if await video_container.count() > 0:
                media_urls.append("video_present")

            return {
                "timestamp": datetime_str,
                "author": username,
                "text": text,
                "likes": likes,
                "retweets": retweets,
                "replies": replies,
                "tickers": tickers,
                "media_urls": media_urls,
                "fetched_at": datetime.utcnow().isoformat() + "Z",
            }

        except Exception as e:
            logger.debug(f"Error extracting tweet data: {e}")
            return None

    def _parse_count(self, text: str) -> int:
        """Parse a count string like '1.2K' or '1.2M' to integer."""
        if not text:
            return 0

        text = text.strip().replace(",", "")

        multipliers = {"K": 1000, "M": 1000000, "B": 1000000000}
        for suffix, mult in multipliers.items():
            if suffix in text:
                try:
                    return int(float(text.replace(suffix, "")) * mult)
                except ValueError:
                    return 0

        try:
            return int(text)
        except ValueError:
            return 0

    def _detect_tickers(self, text: str) -> list[str]:
        """Detect stock tickers in text."""
        # Common patterns: $AAPL, $TSLA, $MSFT, etc.
        ticker_pattern = r"\$([A-Z]{1,5})\b"
        matches = re.findall(ticker_pattern, text.upper())

        # Filter out common false positives
        false_positives = {"A", "I", "TO", "IF", "IN", "ON", "AS", "AT", "IS", "IT", "OR", "AN", "BE", "ME", "SO"}
        return list(set(matches) - false_positives)

    async def fetch_feed(
        self, handles: list[str], max_tweets_per_handle: int = 20
    ) -> list[dict]:
        """Fetch tweets from multiple handles."""
        all_tweets = []

        for handle in handles:
            try:
                tweets = await self.fetch_user_tweets(handle, max_tweets_per_handle)
                all_tweets.extend(tweets)
                await self._human_delay()
            except Exception as e:
                logger.error(f"Error fetching {handle}: {e}")
                continue

        # Sort by timestamp
        all_tweets.sort(
            key=lambda x: x.get("timestamp", ""), reverse=True
        )

        return all_tweets


class TwitterAPI:
    """Twitter/X GraphQL API client for cleaner data extraction."""

    def __init__(self):
        self.settings = get_settings().scanner
        self.browser = None
        self.context = None
        self.page = None
        self.interceptor = GraphQLInterceptor()

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()

    async def start(self) -> None:
        """Initialize the browser."""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        self.context = await self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        )
        self.page = await self.context.new_page()
        self.interceptor.setup_interceptor(self.page)

    async def stop(self) -> None:
        """Clean up."""
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def fetch_user_tweets(self, username: str, max_tweets: int = 20) -> list[dict]:
        """Fetch tweets using GraphQL interception."""
        self.interceptor.clear()
        
        url = f"https://x.com/{username}"
        await self.page.goto(url, wait_until="networkidle", timeout=30000)
        
        # Wait for GraphQL responses to populate
        await asyncio.sleep(2)
        
        return self.interceptor.get_tweets_from_entries()[:max_tweets]
    
    async def fetch_single_tweet(self, tweet_id: str) -> Optional[dict]:
        """Fetch a single tweet by ID using GraphQL."""
        self.interceptor.clear()
        
        url = f"https://x.com/i/status/{tweet_id}"
        await self.page.goto(url, wait_until="networkidle", timeout=30000)
        
        await asyncio.sleep(2)
        
        tweets = self.interceptor.get_tweets_from_entries()
        return tweets[0] if tweets else None