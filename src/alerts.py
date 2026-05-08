"""Alert and notification system for Telegram and Discord."""

from typing import Optional

from loguru import logger

from src.config import AlertSettings, get_settings


class AlertManager:
    """Manages alerts to Telegram and Discord."""

    def __init__(self, settings: Optional[AlertSettings] = None):
        self.settings = settings or get_settings().alert
        self._telegram_client = None

    def _get_telegram_client(self):
        """Get or create Telegram client."""
        if self._telegram_client is None and self.settings.telegram_bot_token:
            try:
                from telegram import Bot
                self._telegram_client = Bot(token=self.settings.telegram_bot_token)
            except Exception as e:
                logger.error(f"Error initializing Telegram: {e}")

        return self._telegram_client

    async def send_telegram(
        self, message: str, parse_mode: str = "Markdown"
    ) -> bool:
        """Send a message to Telegram."""
        if not self.settings.telegram_bot_token or not self.settings.telegram_chat_id:
            logger.debug("Telegram not configured")
            return False

        try:
            bot = self._get_telegram_client()
            await bot.send_message(
                chat_id=self.settings.telegram_chat_id,
                text=message,
                parse_mode=parse_mode,
            )
            logger.info("Telegram alert sent")
            return True
        except Exception as e:
            logger.error(f"Error sending Telegram alert: {e}")
            return False

    async def send_discord(self, message: str, embed: Optional[dict] = None) -> bool:
        """Send a message to Discord webhook."""
        if not self.settings.discord_webhook_url:
            logger.debug("Discord webhook not configured")
            return False

        try:
            import httpx

            payload = {"content": message}
            if embed:
                payload["embeds"] = [embed]

            async with httpx.AsyncClient() as client:
                await client.post(
                    self.settings.discord_webhook_url,
                    json=payload,
                    timeout=10.0,
                )

            logger.info("Discord alert sent")
            return True
        except Exception as e:
            logger.error(f"Error sending Discord alert: {e}")
            return False

    async def send_alert(
        self,
        message: str,
        severity: str = "info",
        embed: Optional[dict] = None,
    ) -> bool:
        """Send alerts to all configured channels."""
        success = False

        # Add severity emoji
        severity_emojis = {
            "info": "ℹ️",
            "warning": "⚠️",
            "error": "🚨",
            "success": "✅",
        }
        prefix = severity_emojis.get(severity, "ℹ️")

        formatted = f"{prefix} {message}"

        # Send to Telegram
        if await self.send_telegram(formatted):
            success = True

        # Send to Discord
        if await self.send_discord(formatted, embed):
            success = True

        return success

    async def alert_scraper_blocked(self, handle: str, error: str) -> bool:
        """Alert when scraper is blocked."""
        message = f"🚨 *Scraper Blocked*\n\nHandle: @{handle}\nError: {error}"

        embed = {
            "title": "Scraper Blocked",
            "description": f"Failed to fetch @{handle}",
            "color": 16711680,  # Red
            "fields": [{"name": "Error", "value": error, "inline": False}],
        }

        return await self.send_alert(message, "error", embed)

    async def alert_signal_detected(
        self, handle: str, ticker: str, sentiment: str, confidence: float
    ) -> bool:
        """Alert when a trading signal is detected."""
        emoji = "🟢" if sentiment == "bullish" else "🔴" if sentiment == "bearish" else "⚪"
        message = f"{emoji} *Signal Detected*\n\nHandle: @{handle}\nTicker: ${ticker}\nSentiment: {sentiment}\nConfidence: {confidence:.0%}"

        color = 65280 if sentiment == "bullish" else 16711680 if sentiment == "bearish" else 8421504

        embed = {
            "title": f"Signal: {ticker}",
            "description": f"New {sentiment} signal from @{handle}",
            "color": color,
            "fields": [
                {"name": "Ticker", "value": f"${ticker}", "inline": True},
                {"name": "Sentiment", "value": sentiment.capitalize(), "inline": True},
                {"name": "Confidence", "value": f"{confidence:.0%}", "inline": True},
            ],
        }

        return await self.send_alert(message, "warning", embed)

    async def alert_scan_complete(
        self, tweet_count: int, signal_count: int, handle_count: int
    ) -> bool:
        """Alert when scan is complete."""
        message = f"✅ *Scan Complete*\n\nHandles scanned: {handle_count}\nTweets fetched: {tweet_count}\nSignals found: {signal_count}"

        embed = {
            "title": "Scan Complete",
            "description": f"Scanned {handle_count} handles",
            "color": 65280,
            "fields": [
                {"name": "Tweets", "value": str(tweet_count), "inline": True},
                {"name": "Signals", "value": str(signal_count), "inline": True},
            ],
        }

        return await self.send_alert(message, "success", embed)