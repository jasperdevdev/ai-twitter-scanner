"""Database storage for tweets - PostgreSQL and ChromaDB."""

from datetime import datetime
from typing import Optional

from loguru import logger
from psycopg2 import OperationalError, connect
from psycopg2.extras import RealDictCursor

from src.config import DatabaseSettings, get_settings


class TweetStore:
    """PostgreSQL storage for structured tweet data."""

    def __init__(self, settings: Optional[DatabaseSettings] = None):
        self.settings = settings or get_settings().database
        self._conn = None

    def connect(self) -> None:
        """Establish database connection."""
        try:
            self._conn = connect(
                host=self.settings.postgres_host,
                port=self.settings.postgres_port,
                dbname=self.settings.postgres_db,
                user=self.settings.postgres_user,
                password=self.settings.postgres_password,
            )
            logger.info("Connected to PostgreSQL")
            self._init_schema()
        except OperationalError as e:
            logger.warning(f"Could not connect to PostgreSQL: {e}")
            self._conn = None

    def _init_schema(self) -> None:
        """Initialize the database schema."""
        if not self._conn:
            return

        schema = """
        CREATE TABLE IF NOT EXISTS tweets (
            id SERIAL PRIMARY KEY,
            tweet_id VARCHAR(64) UNIQUE,
            author VARCHAR(64) NOT NULL,
            text TEXT,
            timestamp TIMESTAMP,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            likes INTEGER DEFAULT 0,
            retweets INTEGER DEFAULT 0,
            replies INTEGER DEFAULT 0,
            has_media BOOLEAN DEFAULT FALSE,
            has_video BOOLEAN DEFAULT FALSE,
            raw_json JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS tickers (
            id SERIAL PRIMARY KEY,
            tweet_id VARCHAR(64),
            ticker VARCHAR(16) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tweet_id) REFERENCES tweets(tweet_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_tweets_author ON tweets(author);
        CREATE INDEX IF NOT EXISTS idx_tweets_timestamp ON tweets(timestamp);
        CREATE INDEX IF NOT EXISTS idx_tickers_ticker ON tickers(ticker);
        CREATE INDEX IF NOT EXISTS idx_tickers_tweet ON tickers(tweet_id);
        """

        try:
            with self._conn.cursor() as cur:
                cur.execute(schema)
            self._conn.commit()
            logger.info("Database schema initialized")
        except Exception as e:
            logger.error(f"Error initializing schema: {e}")

    def store_tweet(self, tweet: dict) -> bool:
        """Store a single tweet."""
        if not self._conn:
            return False

        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO tweets (
                        tweet_id, author, text, timestamp, likes, retweets, replies,
                        has_media, has_video, raw_json
                    ) VALUES (
                        %(tweet_id)s, %(author)s, %(text)s, %(timestamp)s,
                        %(likes)s, %(retweets)s, %(replies)s, %(has_media)s,
                        %(has_video)s, %(raw_json)s
                    )
                    ON CONFLICT (tweet_id) DO UPDATE
                    SET text = EXCLUDED.text,
                        likes = EXCLUDED.likes,
                        retweets = EXCLUDED.retweets,
                        replies = EXCLUDED.replies
                    """,
                    {
                        "tweet_id": f"{tweet['author']}_{tweet['timestamp']}",
                        "author": tweet.get("author", ""),
                        "text": tweet.get("text", ""),
                        "timestamp": datetime.fromisoformat(
                            tweet["timestamp"].replace("Z", "+00:00")
                        )
                        if tweet.get("timestamp")
                        else None,
                        "likes": tweet.get("likes", 0),
                        "retweets": tweet.get("retweets", 0),
                        "replies": tweet.get("replies", 0),
                        "has_media": bool(tweet.get("media_urls", [])),
                        "has_video": "video_present" in tweet.get("media_urls", []),
                        "raw_json": tweet,
                    },
                )

                # Store tickers
                for ticker in tweet.get("tickers", []):
                    cur.execute(
                        """
                        INSERT INTO tickers (tweet_id, ticker)
                        VALUES (%(tweet_id)s, %(ticker)s)
                        ON CONFLICT DO NOTHING
                        """,
                        {
                            "tweet_id": f"{tweet['author']}_{tweet['timestamp']}",
                            "ticker": ticker.upper(),
                        },
                    )

            self._conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error storing tweet: {e}")
            self._conn.rollback()
            return False

    def store_tweets(self, tweets: list[dict]) -> int:
        """Store multiple tweets, return count stored."""
        stored = 0
        for tweet in tweets:
            if self.store_tweet(tweet):
                stored += 1
        return stored

    def get_tweets_by_author(
        self, author: str, limit: int = 100
    ) -> list[dict]:
        """Get tweets by author."""
        if not self._conn:
            return []

        try:
            with self._conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM tweets
                    WHERE author = %(author)s
                    ORDER BY timestamp DESC
                    LIMIT %(limit)s
                    """,
                    {"author": author, "limit": limit},
                )
                return cur.fetchall()
        except Exception as e:
            logger.error(f"Error fetching tweets: {e}")
            return []

    def get_tweets_by_ticker(
        self, ticker: str, limit: int = 100
    ) -> list[dict]:
        """Get tweets containing a specific ticker."""
        if not self._conn:
            return []

        try:
            with self._conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT t.* FROM tweets t
                    JOIN tickers tk ON t.tweet_id = tk.tweet_id
                    WHERE tk.ticker = %(ticker)s
                    ORDER BY t.timestamp DESC
                    LIMIT %(limit)s
                    """,
                    {"ticker": ticker.upper(), "limit": limit},
                )
                return cur.fetchall()
        except Exception as e:
            logger.error(f"Error fetching tweets: {e}")
            return []

    def close(self) -> None:
        """Close connection."""
        if self._conn:
            self._conn.close()
            self._conn = None