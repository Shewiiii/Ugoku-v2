import sqlite3
from pathlib import Path
import logging
from typing import Set, Dict, Literal, Optional

# Database path - in the root folder
DB_PATH = Path(__file__).resolve().parent.parent.parent / "config.sqlite"

DATABASE_TABLE_SCHEMAS = {
    "chatbot_emotes": " (name TEXT PRIMARY KEY, emote_value TEXT NOT NULL)",
    "onsei_server_whitelist": " (server_id INTEGER PRIMARY KEY)",
    "chatbot_server_whitelist": " (server_id INTEGER PRIMARY KEY)",
    "gemini_server_whitelist": " (server_id INTEGER PRIMARY KEY)",
    "premium_gemini_user_id_whitelist": " (server_id INTEGER PRIMARY KEY)",
}


def _get_whitelist_table_name(
    list_type: Literal[
        "onsei_server", "chatbot_server", "gemini_server", "premium_gemini_user_id"
    ],
) -> str:
    return f"{list_type}_whitelist"


def initialize_database():
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            for table_name, schema in DATABASE_TABLE_SCHEMAS.items():
                cursor.execute(f"CREATE TABLE IF NOT EXISTS {table_name}{schema}")
            conn.commit()
        logging.info(f"Database initialized/checked at {DB_PATH}")
    except sqlite3.Error as e:
        logging.error(f"SQLite error during initialization: {e}", exc_info=True)
        raise


# Initialize database on module load
initialize_database()


# --- CHATBOT_EMOTES ---
def add_or_update_chatbot_emote(name: str, emote_value: str) -> None:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO chatbot_emotes (name, emote_value) VALUES (?, ?)",
                (name, emote_value),
            )
            conn.commit()
    except sqlite3.Error as e:
        logging.error(
            f"SQLite error adding/updating chatbot emote '{name}': {e}", exc_info=True
        )
        raise


def remove_chatbot_emote(name: str) -> bool:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM chatbot_emotes WHERE name = ?", (name,))
            conn.commit()
            return cursor.rowcount > 0
    except sqlite3.Error as e:
        logging.error(
            f"SQLite error removing chatbot emote '{name}': {e}", exc_info=True
        )
        raise
    return False


def get_chatbot_emote(name: str) -> Optional[str]:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT emote_value FROM chatbot_emotes WHERE name = ?", (name,)
            )
            row = cursor.fetchone()
            return row[0] if row else None
    except sqlite3.Error as e:
        logging.error(
            f"SQLite error getting chatbot emote '{name}': {e}", exc_info=True
        )
        raise
    return None


def get_all_chatbot_emotes() -> Dict[str, str]:
    emotes = {}
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name, emote_value FROM chatbot_emotes")
            for row in cursor.fetchall():
                emotes[row[0]] = row[1]
    except sqlite3.Error as e:
        logging.error(f"SQLite error getting all chatbot emotes: {e}", exc_info=True)
        # Return what we have, or an empty dict on error
    return emotes


# --- WHITELISTS (Sets of IDs) ---
def add_to_whitelist(
    list_type: Literal[
        "onsei_server", "chatbot_server", "gemini_server", "premium_gemini_user_id"
    ],
    server_id: int,
) -> None:
    table_name = _get_whitelist_table_name(list_type)
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"INSERT OR IGNORE INTO {table_name} (server_id) VALUES (?)",
                (server_id,),
            )
            conn.commit()
    except sqlite3.Error as e:
        logging.error(
            f"SQLite error adding server ID {server_id} to {table_name}: {e}",
            exc_info=True,
        )
        raise


def remove_from_whitelist(
    list_type: Literal[
        "onsei_server", "chatbot_server", "gemini_server", "premium_gemini_user_id"
    ],
    server_id: int,
) -> bool:
    table_name = _get_whitelist_table_name(list_type)
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"DELETE FROM {table_name} WHERE server_id = ?", (server_id,)
            )
            conn.commit()
            return cursor.rowcount > 0
    except sqlite3.Error as e:
        logging.error(
            f"SQLite error removing server ID {server_id} from {table_name}: {e}",
            exc_info=True,
        )
        raise
    return False


def get_whitelist(
    list_type: Literal[
        "onsei_server", "chatbot_server", "gemini_server", "premium_gemini_user_id"
    ],
) -> Set[int]:
    ids: Set[int] = set()
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT server_id FROM {_get_whitelist_table_name(list_type)}"
            )
            for row in cursor.fetchall():
                ids.add(row[0])
    except sqlite3.Error as e:
        logging.error(
            f"SQLite error getting whitelist {_get_whitelist_table_name(list_type)}: {e}",
            exc_info=True,
        )
        # Return what we have, or an empty set on error
    return ids
