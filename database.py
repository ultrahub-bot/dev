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
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL DEFAULT 'Discord_Name',
                        is_admin BOOLEAN NOT NULL DEFAULT 0,
                        discord_id INTEGER NOT NULL UNIQUE,
                        discord_username TEXT NOT NULL DEFAULT 'Discord Name',
                        discord_mention TEXT NOT NULL DEFAULT 'Discord Mention',
                        discord_avatar_url TEXT NOT NULL DEFAULT 'Discord Avatar Url',
                        discord_is_bot BOOLEAN NOT NULL DEFAULT 0,
                        discord_created_at TEXT NOT NULL DEFAULT 'Discord_Created_At',
                        aqw_id INTEGER NOT NULL DEFAULT 0,
                        aqw_username TEXT NOT NULL DEFAULT 'AQW_Username'
                    );

                    CREATE TABLE IF NOT EXISTS bosses (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL DEFAULT 'Boss_Name',
                        party_size INTEGER NOT NULL,
                        map TEXT NOT NULL DEFAULT 'otto',
                        difficulty INTEGER NOT NULL DEFAULT 0,
                        hp INTEGER NOT NULL DEFAULT 0,
                        level INTEGER NOT NULL DEFAULT 0,
                        tips TEXT NOT NULL DEFAULT 'None',
                        wiki_url TEXT NOT NULL DEFAULT 'Wiki_URL',
                        guide_url TEXT NOT NULL DEFAULT 'Guide_URL',
                        thumbnail_url TEXT NOT NULL DEFAULT 'Thumbnail_URL',
                        icon_url TEXT NOT NULL DEFAULT 'Icon_URL',
                        is_hidden BOOLEAN NOT NULL DEFAULT 0,
                        notify_role_id INTEGER NOT NULL DEFAULT 0
                    );
                """)
        except Exception as e:
            self.logger.error(f"Error initializing database: {e}", exc_info=True)
            raise

    def _populate_db(self) -> None:
        """
        Populate initial data from SQL files located in /database/sql/.
        """
        try:
            # Caminho relativo à raiz do projeto
            sql_folder = Path(__file__).parent / "database/sql"
            if not sql_folder.exists() or not sql_folder.is_dir():
                self.logger.warning(f"No SQL folder found at '{sql_folder}', skipping population.")
                return

            # Aqui você pode especificar apenas os arquivos que quer executar
            sql_files = sorted(sql_folder.glob("*.sql"))  # Todos arquivos .sql na pasta
            if not sql_files:
                self.logger.warning(f"No .sql files found in '{sql_folder}', skipping population.")
                return

            with self._get_connection() as conn:
                for sql_file in sql_files:
                    self.logger.info(f"Executing {sql_file.name}...")
                    with sql_file.open("r", encoding="utf-8") as f:
                        sql_script = f.read()
                        conn.executescript(sql_script)

            self.logger.info("Database populated successfully from all SQL files.")

        except Exception as e:
            self.logger.error(f"Error populating database: {e}", exc_info=True)
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
                        name, discord_id, discord_username, discord_mention,
                        discord_avatar_url, discord_is_bot, discord_created_at,
                        aqw_id, aqw_username
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
                    f"UPDATE users SET {set_clause} WHERE discord_id = ?",
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
                cursor.execute("SELECT * FROM users WHERE discord_id = ?", (discord_id,))
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
                cursor.execute("DELETE FROM users WHERE discord_id = ?", (discord_id,))
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
                cursor.execute("SELECT 1 FROM users WHERE discord_id = ?", (discord_id,))
                return cursor.fetchone() is not None
        except Exception as e:
            self.logger.error(f"Error checking user {discord_id}: {e}", exc_info=True)
            return False

    # ==========================================================
    # ================= BOSS OPERATIONS =======================
    # ==========================================================


    def add_boss(self, boss_data: Dict) -> bool:
        """
        Add a new boss with all required fields.

        Args:
            boss_data (Dict): Dictionary containing boss info.

        Returns:
            bool: True if created, False if already exists or error.
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Evita duplicidade pelo nome
                cursor.execute("SELECT 1 FROM bosses WHERE name = ?", (boss_data.get("name"),))
                if cursor.fetchone():
                    return False

                cursor.execute("""
                    INSERT INTO bosses (
                        name, party_size, map, difficulty, hp, level,
                        tips, wiki_url, guide_url, thumbnail_url,
                        icon_url, is_hidden, notify_role_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    boss_data.get("name", "Boss_Name"),
                    boss_data.get("party_size", 1),
                    boss_data.get("map", "otto"),
                    boss_data.get("difficulty", 0),
                    boss_data.get("hp", 0),
                    boss_data.get("level", 0),
                    boss_data.get("tips", "None"),
                    boss_data.get("wiki_url", "Wiki_URL"),
                    boss_data.get("guide_url", "Guide_URL"),
                    boss_data.get("thumbnail_url", "Thumbnail_URL"),
                    boss_data.get("icon_url", "Icon_URL"),
                    int(boss_data.get("is_hidden", 0)),
                    boss_data.get("notify_role_id", 0)
                ))
                return True

        except sqlite3.IntegrityError as e:
            self.logger.warning(f"Boss already exists: {boss_data.get('name')} ({e})")
            return False
        except Exception as e:
            self.logger.error(f"Error adding boss {boss_data.get('name')}: {e}", exc_info=True)
            return False

    # ----------------- UPDATE BOSS -----------------
    def update_boss(self, boss_id: int, **kwargs) -> bool:
        """Update boss fields by boss ID."""
        if not kwargs:
            return False

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                set_clause = ", ".join(f"{k} = ?" for k in kwargs)
                values = list(kwargs.values()) + [boss_id]
                cursor.execute(
                    f"UPDATE bosses SET {set_clause} WHERE id = ?",
                    values
                )
                return cursor.rowcount > 0
        except Exception as e:
            self.logger.error(f"Error updating boss {boss_id}: {e}", exc_info=True)
            return False

    # ----------------- GET BOSS -----------------
    def get_boss(self, boss_id: int) -> Optional[Dict]:
        """Retrieve a boss by ID."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM bosses WHERE id = ?", (boss_id,))
                result = cursor.fetchone()
                return dict(result) if result else None
        except Exception as e:
            self.logger.error(f"Error getting boss {boss_id}: {e}", exc_info=True)
            return None

    # ----------------- DELETE BOSS -----------------
    def delete_boss(self, boss_id: int) -> bool:
        """Delete a boss by ID."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM bosses WHERE id = ?", (boss_id,))
                return cursor.rowcount > 0
        except Exception as e:
            self.logger.error(f"Error deleting boss {boss_id}: {e}", exc_info=True)
            return False

    # ----------------- LIST BOSSES -----------------
    def list_bosses(self) -> List[Dict]:
        """Return all bosses."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM bosses")
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            self.logger.error(f"Error listing bosses: {e}", exc_info=True)
            return []

    # ----------------- CHECK BOSS EXISTS -----------------
    def check_boss_exists(self, boss_id: int) -> bool:
        """Check if a boss exists by ID."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM bosses WHERE id = ?", (boss_id,))
                return cursor.fetchone() is not None
        except Exception as e:
            self.logger.error(f"Error checking boss {boss_id}: {e}", exc_info=True)
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
#db._populate_db() # Descomente esta linha caso precise repopular o banco de dados com os arquivos SQL

