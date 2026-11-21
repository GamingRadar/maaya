"""Automated tests for SQLite persistent conversations and database operations."""

from pathlib import Path
import pytest
from app.memory.database import Database, Conversation, Message


def test_database_initialization(tmp_path):
    """Verify database creates tables and indexes on clean path."""
    db_file = tmp_path / "test.db"
    db = Database(str(db_file))
    assert db_file.is_file()

    with db.get_connection() as conn:
        tables = [
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table';"
            ).fetchall()
        ]
        assert "conversations" in tables
        assert "messages" in tables
        assert "schema_version" in tables


def test_create_and_get_conversation(tmp_path):
    """Verify creating a conversation and retrieving it with message count."""
    db = Database(str(tmp_path / "test.db"))
    conv = db.create_conversation(title="Project Discussion")
    assert conv.id is not None
    assert conv.title == "Project Discussion"
    assert conv.message_count == 0

    fetched = db.get_conversation(conv.id)
    assert fetched is not None
    assert fetched.id == conv.id
    assert fetched.title == "Project Discussion"
    assert fetched.message_count == 0


def test_message_persistence_and_chronology(tmp_path):
    """Verify messages are persisted and retrieved in chronological order."""
    db = Database(str(tmp_path / "test.db"))
    conv = db.create_conversation(title="Dialogue")

    m1 = db.add_message(conv.id, "user", "First user prompt")
    m2 = db.add_message(conv.id, "assistant", "First assistant answer")
    m3 = db.add_message(conv.id, "user", "Second user prompt")

    messages = db.get_messages(conv.id)
    assert len(messages) == 3
    assert messages[0].content == "First user prompt"
    assert messages[0].role == "user"
    assert messages[1].content == "First assistant answer"
    assert messages[1].role == "assistant"
    assert messages[2].content == "Second user prompt"

    # Verify conversation message_count updated
    conv_updated = db.get_conversation(conv.id)
    assert conv_updated.message_count == 3


def test_list_conversations_ordered_by_updated_at(tmp_path):
    """Verify conversations are listed ordered by most recently updated."""
    db = Database(str(tmp_path / "test.db"))
    c1 = db.create_conversation("Conv 1")
    c2 = db.create_conversation("Conv 2")

    # Add message to c1, which updates its updated_at
    db.add_message(c1.id, "user", "Hello in Conv 1")

    convs = db.list_conversations()
    assert len(convs) == 2
    # c1 was updated after c2 creation, so it should be first
    assert convs[0].id == c1.id
    assert convs[1].id == c2.id


def test_conversation_deletion_and_cascade(tmp_path):
    """Verify deleting a conversation cascades to delete associated messages."""
    db = Database(str(tmp_path / "test.db"))
    conv = db.create_conversation("To be deleted")
    db.add_message(conv.id, "user", "Message 1")
    db.add_message(conv.id, "assistant", "Response 1")

    assert len(db.get_messages(conv.id)) == 2
    deleted = db.delete_conversation(conv.id)
    assert deleted is True

    # Conversation must not exist
    assert db.get_conversation(conv.id) is None
    # Messages must have cascaded
    assert len(db.get_messages(conv.id)) == 0


def test_database_persistence_across_reconnect(tmp_path):
    """Verify data persists when database connection is closed and reopened."""
    db_file = tmp_path / "persistent.db"
    db1 = Database(str(db_file))
    conv = db1.create_conversation("Permanent Chat")
    db1.add_message(conv.id, "user", "Will this survive?")
    db1.add_message(conv.id, "assistant", "Yes, across reboots.")

    # Reopen brand new Database instance pointing to same file
    db2 = Database(str(db_file))
    fetched = db2.get_conversation(conv.id)
    assert fetched is not None
    assert fetched.title == "Permanent Chat"
    messages = db2.get_messages(conv.id)
    assert len(messages) == 2
    assert messages[0].content == "Will this survive?"


def test_foreign_key_enforcement(tmp_path):
    """Verify foreign key constraint prevents adding message to non-existent conversation."""
    db = Database(str(tmp_path / "test.db"))
    with pytest.raises(Exception):
        db.add_message("non-existent-conv-id", "user", "Orphan message")
