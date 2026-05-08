"""Tests for AI Twitter Scanner."""

import pytest
from src.analyzer import SignalDetector, SentimentAnalyzer
from src.proxy import IPRotation
from src.config import get_settings


class TestSignalDetector:
    """Tests for pattern-based signal detection."""

    def test_bullish_detection(self):
        """Test detection of bullish signals."""
        detector = SignalDetector()

        result = detector.detect(
            "Just bought more $AAPL, to the moon! 🚀",
            ["AAPL"]
        )

        assert result.sentiment.value == "bullish"
        assert result.confidence > 0.5

    def test_bearish_detection(self):
        """Test detection of bearish signals."""
        detector = SignalDetector()

        result = detector.detect(
            "Selling all my $TSLA, this is a dump",
            ["TSLA"]
        )

        assert result.sentiment.value == "bearish"
        assert result.confidence > 0.3

    def test_neutral_no_signal(self):
        """Test neutral when no clear signal."""
        detector = SignalDetector()

        result = detector.detect(
            "Watching $NVDA for now, will decide later",
            ["NVDA"]
        )

        assert result.confidence < 0.8

    def test_ticker_extraction(self):
        """Test ticker extraction from text."""
        detector = SignalDetector()

        result = detector.detect(
            "Big move coming for $AMD and $INTC",
            ["AMD", "INTC"]
        )

        assert "AMD" in result.tickers_detected
        assert "INTC" in result.tickers_detected


class TestIPRotation:
    """Tests for IP/User-Agent rotation."""

    def test_get_user_agent(self):
        """Test getting user agent."""
        rotation = IPRotation()
        ua = rotation.get_user_agent()

        assert ua is not None
        assert "Mozilla" in ua

    def test_random_user_agent(self):
        """Test random user agent."""
        rotation = IPRotation()

        # Should return different agents over time
        uas = set()
        for _ in range(10):
            uas.add(rotation.get_random_user_agent())

        assert len(uas) > 1


class TestConfig:
    """Tests for configuration."""

    def test_default_settings(self):
        """Test default settings loaded."""
        settings = get_settings()

        assert settings is not None
        assert settings.scanner is not None

    def test_tracked_handles(self):
        """Test default tracked handles."""
        settings = get_settings()

        assert len(settings.tracked_handles) > 0
        assert "elonmusk" in settings.tracked_handles


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Test scraper can be initialized."""
    from src.scraper import TwitterScraper

    scraper = TwitterScraper()

    assert scraper is not None
    assert scraper.settings is not None