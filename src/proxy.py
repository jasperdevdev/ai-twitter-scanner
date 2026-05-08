"""Proxy rotation and IP management for stealth scraping."""

import asyncio
import random
import time
from typing import Optional

from loguru import logger

from src.config import get_settings


class ProxyManager:
    """Manages proxy rotation to avoid rate limiting and bans."""

    def __init__(self):
        self.settings = get_settings().proxy
        self.current_proxy: Optional[str] = None
        self.rotation_count = 0
        self._last_rotation = 0

    async def get_proxy(self) -> Optional[str]:
        """Get a proxy URL for the next request."""
        if not self.settings.enabled:
            return None

        # Check if we need to rotate
        now = time.time()
        if now - self._last_rotation < self.settings.rotation_interval:
            return self.current_proxy

        # Rotate IP
        self.current_proxy = await self._fetch_new_proxy()
        self._last_rotation = now
        self.rotation_count += 1

        if self.current_proxy:
            logger.info(f"Rotated to new proxy (count: {self.rotation_count})")
        else:
            logger.warning("Proxy rotation failed, continuing without proxy")

        return self.current_proxy

    async def _fetch_new_proxy(self) -> Optional[str]:
        """Fetch a new proxy from the configured service."""
        if not self.settings.api_key or not self.settings.proxy_url:
            logger.warning("Proxy configured but credentials missing")
            return None

        try:
            import httpx

            # Example proxy API integration
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self.settings.proxy_url,
                    headers={"Authorization": f"Bearer {self.settings.api_key}"},
                    timeout=30.0,
                )

                if response.status_code == 200:
                    data = response.json()
                    return data.get("proxy_url")

        except Exception as e:
            logger.error(f"Error fetching proxy: {e}")

        return None

    async def check_proxy_health(self, proxy: str) -> bool:
        """Check if a proxy is working."""
        if not proxy:
            return False

        try:
            import httpx

            async with httpx.AsyncClient(proxies={"http": proxy, "https": proxy}) as client:
                response = await client.get(
                    "https://httpbin.org/ip",
                    timeout=10.0,
                )
                return response.status_code == 200

        except Exception:
            return False

    def record_failure(self, proxy: Optional[str] = None) -> None:
        """Record a failed request to potentially rotate sooner."""
        # If we hit rate limits, force rotation on next request
        if proxy and proxy == self.current_proxy:
            logger.warning("Proxy marked as failing, will rotate")
            self._last_rotation = 0

    def get_stats(self) -> dict:
        """Get proxy rotation statistics."""
        return {
            "enabled": self.settings.enabled,
            "rotation_count": self.rotation_count,
            "current_proxy": self.current_proxy,
            "seconds_since_last_rotation": int(time.time() - self._last_rotation),
        }


class IPRotation:
    """Simple IP rotation without dedicated proxy service."""

    def __init__(self):
        self.settings = get_settings().scanner
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
        ]
        self._ua_index = 0

    def get_user_agent(self) -> str:
        """Get a user agent string (rotates with each call)."""
        ua = self.user_agents[self._ua_index]
        self._ua_index = (self._ua_index + 1) % len(self.user_agents)
        return ua

    def get_random_user_agent(self) -> str:
        """Get a random user agent string."""
        return random.choice(self.user_agents)


def create_proxy_manager() -> ProxyManager:
    """Factory to create appropriate proxy manager."""
    return ProxyManager()