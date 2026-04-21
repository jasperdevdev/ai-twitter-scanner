"""Main CLI entry point for AI Twitter Scanner."""

import asyncio
import json
import sys
from pathlib import Path

from loguru import logger

from src.config import get_settings
from src.scraper import TwitterScraper
from src.storage import TweetStore
from src.vector_store import VectorStore
from src.analyzer import SignalDetector, SentimentAnalyzer
from src.alerts import AlertManager


def setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    logger.remove()
    log_level = "DEBUG" if verbose else "INFO"
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level=log_level,
    )

    # Also log to file
    log_dir = Path("./logs")
    log_dir.mkdir(exist_ok=True)
    logger.add(
        log_dir / "scanner_{time:YYYY-MM-DD}.log",
        rotation="1 day",
        retention="30 days",
        level="DEBUG",
    )


async def run_scan(
    handles: list[str] | None = None,
    max_tweets: int = 20,
    analyze: bool = True,
    send_alerts: bool = False,
    store: bool = True,
) -> dict:
    """Run a scan of the specified handles."""
    settings = get_settings()
    handles = handles or settings.tracked_handles

    logger.info(f"Starting scan of {len(handles)} handles")

    results = {
        "handles": handles,
        "tweets": [],
        "signals": [],
        "errors": [],
    }

    # Initialize components
    scraper = TwitterScraper()
    tweet_store = None
    vector_store = None
    analyzer = None
    alert_manager = None

    if store:
        tweet_store = TweetStore()
        tweet_store.connect()
        vector_store = VectorStore()
        vector_store.connect()

    if analyze:
        # Use faster pattern-based detector by default
        # For full AI analysis, set OPENAI_API_KEY
        if settings.ai.api_key:
            analyzer = SentimentAnalyzer()
            logger.info("Using AI-powered sentiment analysis")
        else:
            analyzer = SignalDetector()
            logger.info("Using pattern-based signal detection")

    if send_alerts:
        alert_manager = AlertManager()

    try:
        # Start the scraper
        await scraper.start()

        # Fetch tweets from all handles
        all_tweets = await scraper.fetch_feed(handles, max_tweets)
        results["tweets"] = all_tweets

        logger.info(f"Fetched {len(all_tweets)} tweets")

        # Analyze tweets for signals
        if analyze and analyzer:
            for tweet in all_tweets:
                tickers = tweet.get("tickers", [])

                if not tickers:
                    continue

                if isinstance(analyzer, SentimentAnalyzer):
                    analysis = await analyzer.analyze(tweet.get("text", ""), tickers)
                else:
                    analysis = analyzer.detect(tweet.get("text", ""), tickers)

                if analysis.confidence >= settings.alert.alert_threshold:
                    signal = {
                        "tweet": tweet,
                        "tickers": tickers,
                        "sentiment": analysis.sentiment.value,
                        "signal_type": analysis.signal_type.value,
                        "confidence": analysis.confidence,
                        "reasoning": analysis.reasoning,
                    }
                    results["signals"].append(signal)

                    # Send alert if confidence is high
                    if send_alerts and alert_manager and analysis.confidence >= 0.8:
                        for ticker in tickers:
                            await alert_manager.alert_signal_detected(
                                tweet.get("author", ""),
                                ticker,
                                analysis.sentiment.value,
                                analysis.confidence,
                            )

        logger.info(f"Found {len(results['signals'])} signals")

        # Store results
        if store and tweet_store:
            stored = tweet_store.store_tweets(all_tweets)
            logger.info(f"Stored {stored} tweets in database")

        # Send completion alert
        if send_alerts and alert_manager:
            await alert_manager.alert_scan_complete(
                len(all_tweets),
                len(results["signals"]),
                len(handles),
            )

    except Exception as e:
        logger.error(f"Scan error: {e}")
        results["errors"].append(str(e))

    finally:
        # Cleanup
        await scraper.stop()
        if tweet_store:
            tweet_store.close()
        if vector_store:
            vector_store.close()

    return results


async def watch_handle(handle: str, max_tweets: int = 50) -> dict:
    """Watch a single handle continuously."""
    logger.info(f"Watching @{handle}")

    settings = get_settings()
    scraper = TwitterScraper()

    results = {}

    try:
        await scraper.start()
        tweets = await scraper.fetch_user_tweets(handle, max_tweets)
        results["tweets"] = tweets
        results["handle"] = handle

    except Exception as e:
        logger.error(f"Error watching @{handle}: {e}")
        results["error"] = str(e)

    finally:
        await scraper.stop()

    return results


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="AI Twitter Scanner - Financial Sentiment Monitor"
    )
    parser.add_argument(
        "--handles",
        nargs="+",
        help="Handles to scan (default: from config)",
    )
    parser.add_argument(
        "--max-tweets",
        type=int,
        default=20,
        help="Max tweets per handle (default: 20)",
    )
    parser.add_argument(
        "--no-analyze",
        action="store_true",
        help="Skip sentiment analysis",
    )
    parser.add_argument(
        "--no-alerts",
        action="store_true",
        help="Skip sending alerts",
    )
    parser.add_argument(
        "--no-store",
        action="store_true",
        help="Skip storing in database",
    )
    parser.add_argument(
        "--watch",
        help="Watch a single handle continuously",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Output file for results (JSON)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output",
    )

    args = parser.parse_args()

    setup_logging(args.verbose)

    if args.watch:
        results = asyncio.run(watch_handle(args.watch, args.max_tweets))
    else:
        results = asyncio.run(
            run_scan(
                handles=args.handles,
                max_tweets=args.max_tweets,
                analyze=not args.no_analyze,
                send_alerts=not args.no_alerts,
                store=not args.no_store,
            )
        )

    # Output results
    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2, default=str)
        logger.info(f"Results written to {args.output}")
    else:
        print(json.dumps(results, indent=2, default=str))

    return 0 if not results.get("errors") else 1


if __name__ == "__main__":
    sys.exit(main())