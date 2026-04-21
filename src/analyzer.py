"""AI-powered sentiment and signal analysis for tweets."""

import json
from enum import Enum
from typing import Optional

from loguru import logger
from pydantic import BaseModel

from src.config import AISettings, get_settings


class Sentiment(str, Enum):
    """Sentiment classification."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    MIXED = "mixed"


class SignalType(str, Enum):
    """Signal type classification."""

    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    WATCH = "watch"
    ALERT = "alert"
    NONE = "none"


class AnalysisResult(BaseModel):
    """Result of tweet analysis."""

    sentiment: Sentiment
    signal_type: SignalType
    confidence: float
    reasoning: str
    tickers_detected: list[str]
    key_points: list[str]


class SentimentAnalyzer:
    """AI-powered sentiment analyzer using LLM."""

    def __init__(self, settings: Optional[AISettings] = None):
        self.settings = settings or get_settings().ai
        self._client = None

    def _get_client(self):
        """Get or create the AI client."""
        if self._client is None:
            if self.settings.provider == "openai":
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(
                    api_key=self.settings.api_key or None,
                )
            elif self.settings.provider == "ollama":
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(
                    base_url=self.settings.base_url or "http://localhost:11434/v1",
                    api_key="ollama",
                )
            elif self.settings.provider == "groq":
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(
                    base_url="https://api.groq.com/openai/v1",
                    api_key=self.settings.api_key,
                )

        return self._client

    async def analyze(self, tweet_text: str, tickers: list[str]) -> AnalysisResult:
        """Analyze a tweet for sentiment and signals."""
        prompt = self._build_prompt(tweet_text, tickers)

        try:
            client = self._get_client()
            response = await client.chat.completions.create(
                model=self.settings.model,
                messages=[
                    {
                        "role": "system",
                        "content": self._get_system_prompt(),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                temperature=self.settings.temperature,
                max_tokens=self.settings.max_tokens,
                response_format={"type": "json_object"},
            )

            result_json = response.choices[0].message.content
            result = json.loads(result_json)

            return AnalysisResult(
                sentiment=Sentiment(result.get("sentiment", "neutral")),
                signal_type=SignalType(result.get("signal_type", "none")),
                confidence=float(result.get("confidence", 0.5)),
                reasoning=result.get("reasoning", ""),
                tickers_detected=tickers or result.get("tickers_detected", []),
                key_points=result.get("key_points", []),
            )

        except Exception as e:
            logger.error(f"Error analyzing tweet: {e}")
            return AnalysisResult(
                sentiment=Sentiment.NEUTRAL,
                signal_type=SignalType.NONE,
                confidence=0.0,
                reasoning=f"Analysis failed: {str(e)}",
                tickers_detected=tickers,
                key_points=[],
            )

    def _build_prompt(self, tweet_text: str, tickers: list[str]) -> str:
        """Build the analysis prompt."""
        tickers_str = ", ".join([f"${t}" for t in tickers]) if tickers else "None detected"

        return f"""Analyze this tweet for financial sentiment and trading signals:

Tweet: {tweet_text}

Detected tickers: {tickers_str}

Provide a JSON response with:
- sentiment: bullish, bearish, neutral, or mixed
- signal_type: buy, sell, hold, watch, alert, or none
- confidence: 0.0-1.0 score for how strong the signal is
- reasoning: brief explanation of your analysis
- tickers_detected: list of any stock tickers mentioned (use $ prefix)
- key_points: list of 1-3 key insights from this tweet
"""

    def _get_system_prompt(self) -> str:
        """Get the system prompt for analysis."""
        return """You are a financial sentiment analysis expert specializing in
Twitter/X stock trading signals. Analyze tweets for:

1. Sentiment: Is the author bullish, bearish, neutral, or mixed about stocks?
2. Signals: Does the tweet contain buy, sell, hold, watch, or alert signals?
3. Confidence: How strong is the signal?

Consider:
- Explicit mentions like "buying", "selling", "holding"
- Keywords like "to the moon", "dump", "rip", "call", "put"
- Dollar amounts or percentages mentioned
- Stock tickers with $ prefix
- Sentiment indicators in emojis and language

Respond ONLY with valid JSON, no additional text."""


class SignalDetector:
    """Pattern-based signal detection without LLM."""

    def __init__(self):
        self.bullish_keywords = [
            "buy",
            "long",
            "call",
            "bullish",
            "to the moon",
            "moon",
            "🚀",
            " diamond hands",
            "holding",
            "accumulating",
            "adding",
            "load",
            "undervalued",
        ]
        self.bearish_keywords = [
            "sell",
            "short",
            "put",
            "bearish",
            "dump",
            "rip",
            "😢",
            "panic sell",
            "sold",
            "overvalued",
            "crash",
            "bear",
        ]
        self.neutral_keywords = [
            "watch",
            "monitor",
            "track",
            "waiting",
            "see",
            "observing",
        ]

    def detect(self, text: str, tickers: list[str]) -> AnalysisResult:
        """Detect signals using pattern matching."""
        text_lower = text.lower()

        bullish_count = sum(1 for kw in self.bullish_keywords if kw in text_lower)
        bearish_count = sum(1 for kw in self.bearish_keywords if kw in text_lower)
        neutral_count = sum(1 for kw in self.neutral_keywords if kw in text_lower)

        total = bullish_count + bearish_count + neutral_count

        if total == 0:
            return AnalysisResult(
                sentiment=Sentiment.NEUTRAL,
                signal_type=SignalType.NONE,
                confidence=0.3,
                reasoning="No clear signals detected",
                tickers_detected=tickers,
                key_points=["No specific signals found"],
            )

        if bullish_count > bearish_count:
            sentiment = Sentiment.BULLISH
            signal_type = SignalType.BUY if bullish_count > 1 else SignalType.WATCH
            confidence = min(0.9, bullish_count / total + 0.4)
        elif bearish_count > bullish_count:
            sentiment = Sentiment.BEARISH
            signal_type = SignalType.SELL if bearish_count > 1 else SignalType.WATCH
            confidence = min(0.9, bearish_count / total + 0.4)
        else:
            sentiment = Sentiment.NEUTRAL
            signal_type = SignalType.HOLD
            confidence = 0.5

        return AnalysisResult(
            sentiment=sentiment,
            signal_type=signal_type,
            confidence=round(confidence, 2),
            reasoning=f"Bullish: {bullish_count}, Bearish: {bearish_count}, Neutral: {neutral_count}",
            tickers_detected=tickers,
            key_points=[f"Detected {len(tickers)} ticker(s)"],
        )