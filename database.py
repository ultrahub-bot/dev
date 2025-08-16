# database.py
import sqlite3
from pathlib import Path
import logging
from typing import Optional, List, Dict, Tuple
from models import UserInfo

class DatabaseHandler:
    """Simple SQLite database handler for Discord bot operations."""

    def __init__(self, db_name: str = "uh.db"):
        """
        Initializes the DatabaseHandler and creates the database if it doesn't exist.

        Args:
            db_name (str): Name of the SQLite database file.
        """
        self.db_path = Path("database") / db_name
        self.db_path.parent.mkdir(exist_ok=True)
        self.logger = logging.getLogger("database")
        self._initialize_db()

    def _get_connection(self) -> sqlite3.Connection:
        """
        Creates and returns a new SQLite connection.

        Returns:
            sqlite3.Connection: SQLite connection object.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize_db(self):
        """
        Initializes the database and creates the 'users' table if it does not exist.
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    ID INTEGER NOT NULL UNIQUE PRIMARY KEY AUTOINCREMENT,
                    Name TEXT NOT NULL DEFAULT 'Name',
                    Admin INTEGER NOT NULL DEFAULT 0,
                    Discord_ID INTEGER NOT NULL DEFAULT 0,
                    Discord_Username TEXT NOT NULL DEFAULT 'Discord Name',
                    Discord_Mention TEXT NOT NULL DEFAULT 'Discord Mention',
                    Discord_IsBot INTEGER NOT NULL DEFAULT 0,
                    Discord_CreatedAt TEXT NOT NULL DEFAULT 'Discord_Created_At',
                    AQW_ID INTEGER NOT NULL DEFAULT 0 UNIQUE,
                    AQW_Username TEXT NOT NULL DEFAULT 'AQW_Username'
                )
            """)
            conn.commit()
        except Exception as e:
            self.logger.error(f"Error initializing database: {e}")
            raise
        finally:
            conn.close()

    # ==========================================================
    # ================= USER OPERATIONS ========================
    # ==========================================================

                    
    def add_user(self, discord_user) -> bool:
        """
        Adds a new user to the database with complete Discord info.

        Args:
            discord_user: Discord User or Member object

        Returns:
            bool: True if user was added, False if user already exists or error occurred.
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO users (
                    Discord_ID, 
                    Discord_Username,
                    Discord_Mention,
                    Discord_IsBot,
                    Discord_CreatedAt,
                    Name
                ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    discord_user.id,
                    str(discord_user),
                    discord_user.mention,
                    int(discord_user.bot),
                    discord_user.created_at.isoformat(),
                    getattr(discord_user, 'display_name', str(discord_user))
                )
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            self.logger.warning(f"User {discord_user.id} already exists")
            return False
        except Exception as e:
            self.logger.error(f"Error adding user: {e}")
            return False
        finally:
            conn.close()             

    def get_user(self, discord_id: int) -> Optional[Dict]:
        """
        Retrieves a user from the database by Discord ID.

        Args:
            discord_id (int): Discord user ID.

        Returns:
            Optional[Dict]: User data as a dictionary, or None if not found.
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM users WHERE discord_id = ?",
                (discord_id,)
            )
            result = cursor.fetchone()
            return dict(result) if result else None
        except Exception as e:
            self.logger.error(f"Error getting user: {e}")
            return None
        finally:
            conn.close()

    def update_user(self, discord_id: int, **kwargs) -> bool:
        """
        Updates user information in the database.

        Args:
            discord_id (int): Discord user ID.
            **kwargs: Fields to update (e.g., username, last_seen).

        Returns:
            bool: True if user was updated, False otherwise.
        """
        if not kwargs:
            return False
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            set_clause = ", ".join(f"{k} = ?" for k in kwargs)
            values = list(kwargs.values()) + [discord_id]
            cursor.execute(
                f"UPDATE users SET {set_clause} WHERE discord_id = ?",
                values
            )
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            self.logger.error(f"Error updating user: {e}")
            return False
        finally:
            conn.close()

    def delete_user(self, discord_id: int) -> bool:
        """
        Deletes a user from the database by Discord ID.

        Args:
            discord_id (int): Discord user ID.

        Returns:
            bool: True if user was deleted, False otherwise.
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM users WHERE discord_id = ?",
                (discord_id,)
            )
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            self.logger.error(f"Error deleting user: {e}")
            return False
        finally:
            conn.close()
            
    def list_users(self) -> List[Dict]:
        """
        Lists all users in the database.

        Returns:
            List[Dict]: List of all users as dictionaries.
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users")
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            self.logger.error(f"Error listing users: {e}")
            return []
        finally:
            conn.close()

    def get_user_info(self, discord_id: int) -> UserInfo:  # Added self parameter
        """
        Fetches user data from database and returns as UserInfo object
        
        Args:
            discord_id: The Discord user ID to look up
            
        Returns:
            UserInfo: An object containing all the user's information
        """
        user_data = self.get_user(discord_id)  # Use self.get_user instead of db.get_user
        user_info = UserInfo()
        if user_data:
            for key, value in user_data.items():
                setattr(user_info, key, value)        
        return user_info

    # ==========================================================
    # ================ GENERAL QUERY METHODS ===================
    # ==========================================================

    def execute_query(self, query: str, params: Tuple = ()) -> List[Dict]:
        """
        Executes a custom SQL query and returns the results.

        Args:
            query (str): SQL query string.
            params (Tuple): Parameters for the SQL query.

        Returns:
            List[Dict]: List of result rows as dictionaries.
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            self.logger.error(f"Error executing query: {e}")
            return []
        finally:
            conn.close()

    def get_table_columns(self, table_name: str) -> List[str]:
        """
        Returns a list of column names for the given table.

        Args:
            table_name (str): Name of the table.

        Returns:
            List[str]: List of column names.
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = [row["name"] for row in cursor.fetchall()]
            return columns
        except Exception as e:
            self.logger.error(f"Error getting columns for table {table_name}: {e}")
            return []
        finally:
            conn.close()

# Initialize a global database instance
db = DatabaseHandler()