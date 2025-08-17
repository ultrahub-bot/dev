# database.py
import sqlite3
from pathlib import Path
import logging
from typing import Optional, List, Dict, Tuple
from models import UserInfo


class DatabaseHandler:
    """SQLite database handler for Discord bot operations."""

    def __init__(self, db_name: str = "uh.db") -> None:
        """
        Initialize the DatabaseHandler and create the database if it doesn't exist.
        """
        self.db_path = Path("database") / db_name
        self.db_path.parent.mkdir(exist_ok=True)
        self.logger = logging.getLogger("database")
        self._initialize_db()

    # ==========================================================
    # ================== INTERNAL HELPERS ======================
    # ==========================================================

    def _get_connection(self) -> sqlite3.Connection:
        """Return a new SQLite connection with row access by name."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize_db(self) -> None:
        """Create database tables if they don't already exist."""
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        ID INTEGER PRIMARY KEY AUTOINCREMENT,
                        Name TEXT NOT NULL DEFAULT 'Discord_Name',
                        Admin INTEGER NOT NULL DEFAULT 0,
                        Discord_ID INTEGER NOT NULL DEFAULT 0 UNIQUE,
                        Discord_Username TEXT NOT NULL DEFAULT 'Discord Name',
                        Discord_Mention TEXT NOT NULL DEFAULT 'Discord Mention',
                        Discord_AvatarURL TEXT NOT NULL DEFAULT 'Discord Avatar Url',
                        Discord_IsBot INTEGER NOT NULL DEFAULT 0,
                        Discord_CreatedAt TEXT NOT NULL DEFAULT 'Discord_Created_At',
                        AQW_ID INTEGER NOT NULL DEFAULT 0,
                        AQW_Username TEXT NOT NULL DEFAULT 'AQW_Username'
                    )
                """)
        except Exception as e:
            self.logger.error(f"Error initializing database: {e}", exc_info=True)
            raise

    # ==========================================================
    # ================= USER OPERATIONS ========================
    # ==========================================================

    def add_user(self, discord_user) -> bool:
        """
        Add a new user with all required fields.

        Args:
            discord_user: Discord user object.

        Returns:
            bool: True if created, False if already exists or error.
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("SELECT 1 FROM users WHERE Discord_ID = ?", (discord_user.id,))
                if cursor.fetchone():
                    return False

                cursor.execute("""
                    INSERT INTO users (
                        Name, Discord_ID, Discord_Username, Discord_Mention,
                        Discord_AvatarURL, Discord_IsBot, Discord_CreatedAt,
                        AQW_ID, AQW_Username
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    getattr(discord_user, 'display_name', str(discord_user)),
                    discord_user.id,
                    str(discord_user),
                    discord_user.mention,
                    str(discord_user.display_avatar.url),
                    int(discord_user.bot),
                    discord_user.created_at.isoformat(),
                    0,
                    'AQW_Username'
                ))
                return True

        except sqlite3.IntegrityError as e:
            self.logger.warning(f"User already exists: {discord_user.id} ({e})")
            return False
        except Exception as e:
            self.logger.error(f"Error adding user {discord_user.id}: {e}", exc_info=True)
            return False

    def update_user(self, discord_id: int, **kwargs) -> bool:
        """Update user fields by Discord ID."""
        if not kwargs:
            return False

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                set_clause = ", ".join(f"{k} = ?" for k in kwargs)
                values = list(kwargs.values()) + [discord_id]
                cursor.execute(
                    f"UPDATE users SET {set_clause} WHERE Discord_ID = ?",
                    values
                )
                return cursor.rowcount > 0
        except Exception as e:
            self.logger.error(f"Error updating user {discord_id}: {e}", exc_info=True)
            return False

    def get_user(self, discord_id: int) -> Optional[Dict]:
        """Retrieve a user by Discord ID."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM users WHERE Discord_ID = ?", (discord_id,))
                result = cursor.fetchone()
                return dict(result) if result else None
        except Exception as e:
            self.logger.error(f"Error getting user {discord_id}: {e}", exc_info=True)
            return None

    def delete_user(self, discord_id: int) -> bool:
        """Delete a user by Discord ID."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM users WHERE Discord_ID = ?", (discord_id,))
                return cursor.rowcount > 0
        except Exception as e:
            self.logger.error(f"Error deleting user {discord_id}: {e}", exc_info=True)
            return False

    def list_users(self) -> List[Dict]:
        """Return all users."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM users")
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            self.logger.error(f"Error listing users: {e}", exc_info=True)
            return []

    def get_user_info(self, discord_id: int) -> UserInfo:
        """Fetch user data as a `UserInfo` object."""
        user_data = self.get_user(discord_id)
        user_info = UserInfo()
        if user_data:
            for key, value in user_data.items():
                setattr(user_info, key, value)
        return user_info

    def check_user_exists(self, discord_id: int) -> bool:
        """Check if a user exists by Discord ID."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM users WHERE Discord_ID = ?", (discord_id,))
                return cursor.fetchone() is not None
        except Exception as e:
            self.logger.error(f"Error checking user {discord_id}: {e}", exc_info=True)
            return False

    # ==========================================================
    # ================ GENERAL QUERY METHODS ===================
    # ==========================================================

    def execute_query(self, query: str, params: Tuple = ()) -> List[Dict]:
        """Execute a custom SQL query and return results."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            self.logger.error(f"Error executing query: {e}", exc_info=True)
            return []

    def get_table_columns(self, table_name: str) -> List[str]:
        """Return a list of column names for a table."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"PRAGMA table_info({table_name})")
                return [row["name"] for row in cursor.fetchall()]
        except Exception as e:
            self.logger.error(f"Error getting columns for {table_name}: {e}", exc_info=True)
            return []


# Global database instance
db = DatabaseHandler()
