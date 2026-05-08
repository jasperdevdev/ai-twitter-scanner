"""Vector storage using ChromaDB for semantic search."""

from typing import Optional

from loguru import logger

from src.config import DatabaseSettings, get_settings


class VectorStore:
    """ChromaDB vector storage for tweet embeddings."""

    def __init__(self, settings: Optional[DatabaseSettings] = None):
        self.settings = settings or get_settings().database
        self._client = None
        self._collection = None
        self._initialized = False

    def connect(self) -> None:
        """Initialize ChromaDB client."""
        try:
            import chromadb
            from chromadb.config import Settings

            self._client = chromadb.PersistentClient(
                path=str(self.settings.chroma_persist_dir),
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True,
                ),
            )

            self._collection = self._client.get_or_create_collection(
                "tweets",
                metadata={"description": "Tweet embeddings for semantic search"},
            )

            self._initialized = True
            logger.info("Connected to ChromaDB")
        except ImportError:
            logger.warning("ChromaDB not installed, vector search unavailable")
        except Exception as e:
            logger.error(f"Error connecting to ChromaDB: {e}")

    def add_tweet(
        self, tweet_id: str, text: str, metadata: dict
    ) -> bool:
        """Add a tweet to the vector store."""
        if not self._initialized:
            return False

        try:
            # Use simple text as embedding (ChromaDB handles embedding)
            # For production, use sentence-transformers or OpenAI embeddings
            self._collection.add(
                documents=[text],
                ids=[tweet_id],
                metadatas=[metadata],
            )
            return True
        except Exception as e:
            logger.error(f"Error adding to vector store: {e}")
            return False

    def search(
        self, query: str, n_results: int = 10, filter_metadata: Optional[dict] = None
    ) -> list[dict]:
        """Search for similar tweets."""
        if not self._initialized:
            return []

        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=n_results,
                where=filter_metadata,
            )

            # Format results
            formatted = []
            if results.get("ids"):
                for i, doc_id in enumerate(results["ids"][0]):
                    formatted.append({
                        "id": doc_id,
                        "text": results["documents"][0][i],
                        "metadata": results["metadatas"][0][i],
                        "distance": results["distances"][0][i] if "distances" in results else None,
                    })

            return formatted
        except Exception as e:
            logger.error(f"Error searching vector store: {e}")
            return []

    def get_by_ticker(self, ticker: str, limit: int = 20) -> list[dict]:
        """Get tweets for a specific ticker."""
        return self.search(
            query=f"${ticker.upper()}",
            n_results=limit,
            filter_metadata={"ticker": ticker.upper()},
        )

    def close(self) -> None:
        """Close the client."""
        self._client = None
        self._initialized = False