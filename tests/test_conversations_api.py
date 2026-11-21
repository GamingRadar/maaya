"""Automated tests for Conversation API routes (/conversations)."""

from unittest.mock import AsyncMock, patch
import pytest
from starlette.testclient import TestClient

from app.api.chat import engine
from app.api.conversations import db
from app.engine.gemma import GenerationResult
from app.main import app

client = TestClient(app)


def test_create_conversation_endpoint():
    """Verify POST /conversations creates and returns new conversation."""
    resp = client.post("/conversations", json={"title": "Custom Title"})
    assert resp.status_code == 201
    data = resp.json()
    assert "id" in data
    assert data["title"] == "Custom Title"
    assert data["message_count"] == 0


def test_list_conversations_endpoint():
    """Verify GET /conversations returns array of conversations."""
    resp = client.get("/conversations")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_conversation_with_messages():
    """Verify GET /conversations/{id} returns conversation metadata and message list."""
    create_resp = client.post("/conversations", json={"title": "Review"})
    conv_id = create_resp.json()["id"]

    resp = client.get(f"/conversations/{conv_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == conv_id
    assert data["title"] == "Review"
    assert "messages" in data
    assert isinstance(data["messages"], list)


def test_get_non_existent_conversation_returns_404():
    """Verify GET /conversations/{invalid_id} returns 404."""
    resp = client.get("/conversations/non-existent-id-12345")
    assert resp.status_code == 404
    assert "not found" in resp.json()["error"].lower()


def test_delete_conversation_endpoint():
    """Verify DELETE /conversations/{id} deletes the conversation."""
    create_resp = client.post("/conversations", json={"title": "Temporary"})
    conv_id = create_resp.json()["id"]

    del_resp = client.delete(f"/conversations/{conv_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "deleted"

    # Fetching deleted conversation must return 404
    get_resp = client.get(f"/conversations/{conv_id}")
    assert get_resp.status_code == 404


def test_chat_with_conversation_id_persists_messages_and_passes_history():
    """Verify POST /chat with conversation_id persists messages and supplies history to engine."""
    create_resp = client.post("/conversations", json={"title": "New Conversation"})
    conv_id = create_resp.json()["id"]

    mock_generate = AsyncMock(
        return_value=GenerationResult(
            text="I remember our previous turns.",
            model="gemma-3-1b",
        )
    )

    with patch.object(engine, "generate", new=mock_generate):
        # 1. Turn 1
        resp1 = client.post("/chat", json={"message": "First statement", "conversation_id": conv_id})
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["conversation_id"] == conv_id
        assert data1["response"] == "I remember our previous turns."

        # Engine called with history=[] or empty on turn 1
        assert mock_generate.call_args[1]["history"] == []

        # 2. Turn 2: Engine must receive Turn 1 in history
        resp2 = client.post("/chat", json={"message": "Second query", "conversation_id": conv_id})
        assert resp2.status_code == 200

        history_arg = mock_generate.call_args[1]["history"]
        assert len(history_arg) == 2  # Turn 1 user + Turn 1 assistant
        assert history_arg[0]["role"] == "user"
        assert history_arg[0]["content"] == "First statement"
        assert history_arg[1]["role"] == "assistant"

    # Verify conversation title was auto-updated from first user message
    conv_detail = client.get(f"/conversations/{conv_id}").json()
    assert conv_detail["title"].startswith("First statement")
    assert len(conv_detail["messages"]) == 4  # 2 user + 2 assistant


def test_chat_with_invalid_conversation_id_returns_404():
    """Verify POST /chat with unknown conversation_id returns 404."""
    resp = client.post("/chat", json={"message": "Hello", "conversation_id": "invalid-uuid"})
    assert resp.status_code == 404
    assert "not found" in resp.json()["error"].lower()


def test_legacy_chat_without_conversation_id_preserved():
    """Verify POST /chat without conversation_id continues working as legacy single-turn."""
    with patch.object(
        engine,
        "generate",
        new=AsyncMock(return_value=GenerationResult(text="Legacy response", model="gemma-3-1b")),
    ):
        resp = client.post("/chat", json={"message": "Legacy greeting"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["response"] == "Legacy response"
        assert data["model"] == "gemma-3-1b"
        assert "conversation_id" not in data  # Clean legacy response format preserved
