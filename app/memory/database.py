"""SQLite Database repository for persistent conversations and messages.

Provides safe connection management, schema initialization, and transactional
operations for conversations and turns.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional
import uuid


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Conversation:
    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int = 0


@dataclass
class Message:
    id: str
    conversation_id: str
    role: str
    content: str
    created_at: str
    status: str = "completed"  # pending, completed, failed


class Database:
    """Encapsulates SQLite access for conversations and messages."""

    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self._ensure_dir()
        self.init_db()

    def _ensure_dir(self) -> None:
        """Create parent directory if it does not exist."""
        if not self.db_path.parent.exists():
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        """Create a new SQLite connection with foreign keys and WAL mode enabled."""
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    def init_db(self) -> None:
        """Initialize database tables, schema version, and indexes."""
        with self.get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'completed',
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                );
                """
            )

            # Indexes for fast retrieval and chronological sorting
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_conversations_updated ON conversations(updated_at DESC);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, created_at ASC);"
            )

            # Record initial schema version
            cursor = conn.execute("SELECT version FROM schema_version WHERE version = 1;")
            if not cursor.fetchone():
                conn.execute(
                    "INSERT INTO schema_version (version, applied_at) VALUES (1, ?);",
                    (utc_now_iso(),),
                )

    def create_conversation(self, title: str = "New Conversation", conv_id: Optional[str] = None) -> Conversation:
        """Create a new conversation record."""
        conv_id = conv_id or str(uuid.uuid4())
        now = utc_now_iso()
        with self.get_connection() as conn:
            conn.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?);",
                (conv_id, title, now, now),
            )
        return Conversation(id=conv_id, title=title, created_at=now, updated_at=now, message_count=0)

    def get_conversation(self, conv_id: str) -> Optional[Conversation]:
        """Fetch conversation by ID including total message count."""
        with self.get_connection() as conn:
            row = conn.execute(
                """
                SELECT c.id, c.title, c.created_at, c.updated_at, COUNT(m.id) as message_count
                FROM conversations c
                LEFT JOIN messages m ON c.id = m.conversation_id
                WHERE c.id = ?
                GROUP BY c.id;
                """,
                (conv_id,),
            ).fetchone()
            if row:
                return Conversation(
                    id=row["id"],
                    title=row["title"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    message_count=row["message_count"],
                )
            return None

    def list_conversations(self, limit: int = 50) -> List[Conversation]:
        """List conversations ordered by most recently updated."""
        with self.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT c.id, c.title, c.created_at, c.updated_at, COUNT(m.id) as message_count
                FROM conversations c
                LEFT JOIN messages m ON c.id = m.conversation_id
                GROUP BY c.id
                ORDER BY c.updated_at DESC
                LIMIT ?;
                """,
                (limit,),
            ).fetchall()
            return [
                Conversation(
                    id=row["id"],
                    title=row["title"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    message_count=row["message_count"],
                )
                for row in rows
            ]

    def update_conversation_title(self, conv_id: str, title: str) -> bool:
        """Update a conversation title."""
        now = utc_now_iso()
        with self.get_connection() as conn:
            cursor = conn.execute(
                "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?;",
                (title, now, conv_id),
            )
            return cursor.rowcount > 0

    def touch_conversation(self, conv_id: str) -> bool:
        """Update conversation's updated_at timestamp."""
        now = utc_now_iso()
        with self.get_connection() as conn:
            cursor = conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?;",
                (now, conv_id),
            )
            return cursor.rowcount > 0

    def delete_conversation(self, conv_id: str) -> bool:
        """Delete a conversation and all its associated messages."""
        with self.get_connection() as conn:
            cursor = conn.execute("DELETE FROM conversations WHERE id = ?;", (conv_id,))
            return cursor.rowcount > 0

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        status: str = "completed",
        msg_id: Optional[str] = None,
    ) -> Message:
        """Add a message to a conversation and update conversation updated_at."""
        msg_id = msg_id or str(uuid.uuid4())
        now = utc_now_iso()
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO messages (id, conversation_id, role, content, created_at, status)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (msg_id, conversation_id, role, content, now, status),
            )
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?;",
                (now, conversation_id),
            )
        return Message(
            id=msg_id,
            conversation_id=conversation_id,
            role=role,
            content=content,
            created_at=now,
            status=status,
        )

    def update_message_status(self, msg_id: str, status: str) -> bool:
        """Update message status (e.g. pending -> completed or failed)."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "UPDATE messages SET status = ? WHERE id = ?;",
                (status, msg_id),
            )
            return cursor.rowcount > 0

    def get_messages(self, conversation_id: str) -> List[Message]:
        """Fetch all messages for a conversation in chronological order."""
        with self.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, conversation_id, role, content, created_at, status
                FROM messages
                WHERE conversation_id = ?
                ORDER BY created_at ASC;
                """,
                (conversation_id,),
            ).fetchall()
            return [
                Message(
                    id=row["id"],
                    conversation_id=row["conversation_id"],
                    role=row["role"],
                    content=row["content"],
                    created_at=row["created_at"],
                    status=row["status"],
                )
                for row in rows
            ]
