import sqlite3
import logging
from typing import Set, Dict, Literal, Optional

from config import DB_PATH

DATABASE_TABLE_SCHEMAS = {
    "chatbot_emotes": " (name TEXT PRIMARY KEY, emote_value TEXT NOT NULL)",
    "onsei_servers": " (server_id INTEGER PRIMARY KEY)",
    "chatbot_ids": " (server_id INTEGER PRIMARY KEY)",
    "gemini_servers": " (server_id INTEGER PRIMARY KEY)",
}


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
tables = Literal[
    "onsei_servers", "chatbot_ids", "gemini_server"
]


def add_to_whitelist(
    table_name: tables,
    server_id: int,
) -> None:
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
    table_name: tables,
    server_id: int,
) -> bool:
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
    table_name: tables,
) -> Set[int]:
    ids: Set[int] = set()
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT server_id FROM {table_name}")
            for row in cursor.fetchall():
                ids.add(row[0])
    except sqlite3.Error as e:
        logging.error(
            f"SQLite error getting whitelist {table_name}: {e}",
            exc_info=True,
        )
        # Return what we have, or an empty set on error
    return ids
