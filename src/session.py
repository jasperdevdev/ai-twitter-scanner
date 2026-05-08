"""Session and cookie management for persistent authentication."""

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from loguru import logger

from src.config import get_settings


class SessionManager:
    """Manages browser session persistence (cookies, localStorage)."""

    def __init__(self, session_file: Optional[Path] = None):
        self.settings = get_settings().twitter
        self.session_file = session_file or Path("./data/session.json")
        self.session_file.parent.mkdir(parents=True, exist_ok=True)

    def save_session(self, context) -> bool:
        """Save browser context cookies and storage state."""
        try:
            # Extract cookies
            cookies = asyncio.get_event_loop().run_until_complete(
                context.cookies()
            )

            # Extract localStorage (requires page)
            local_storage = {}
            # Note: Full localStorage extraction requires page script execution

            session_data = {
                "cookies": cookies,
                "local_storage": local_storage,
                "saved_at": datetime.utcnow().isoformat() + "Z",
            }

            with open(self.session_file, "w") as f:
                json.dump(session_data, f, indent=2)

            logger.info(f"Session saved to {self.session_file}")
            return True

        except Exception as e:
            logger.error(f"Error saving session: {e}")
            return False

    def load_session(self) -> Optional[dict]:
        """Load saved session data."""
        if not self.session_file.exists():
            logger.debug("No saved session found")
            return None

        try:
            # Check if session is recent enough (24 hours)
            with open(self.session_file) as f:
                session_data = json.load(f)

            saved_at = datetime.fromisoformat(session_data["saved_at"].replace("Z", "+00:00"))
            if datetime.utcnow() - saved_at > timedelta(hours=24):
                logger.info("Session expired, will create new one")
                return None

            logger.info(f"Loaded session from {self.session_file}")
            return session_data

        except Exception as e:
            logger.error(f"Error loading session: {e}")
            return None

    def apply_session(self, context) -> bool:
        """Apply saved session to browser context."""
        session_data = self.load_session()
        if not session_data:
            return False

        try:
            # Apply cookies
            asyncio.get_event_loop().run_until_complete(
                context.add_cookies(session_data.get("cookies", []))
            )
            logger.info("Session applied successfully")
            return True

        except Exception as e:
            logger.error(f"Error applying session: {e}")
            return False

    def clear_session(self) -> None:
        """Delete saved session."""
        if self.session_file.exists():
            self.session_file.unlink()
            logger.info("Session cleared")

    def is_authenticated(self, context) -> bool:
        """Check if context appears to be authenticated."""
        # Quick check - could navigate to home and check for login UI
        return False  # Placeholder - requires page navigation