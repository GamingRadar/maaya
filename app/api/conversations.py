"""Conversations API route handlers."""

import logging
from json import JSONDecodeError

from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings
from app.memory.database import Database

logger = logging.getLogger("maaya.api.conversations")

# Database instance initialized with configured database path
db = Database(settings.storage.database_path)


async def create_conversation_handler(request: Request) -> JSONResponse:
    """Handle POST /conversations - Create a new conversation."""
    title = "New Conversation"
    try:
        body = await request.json()
        if isinstance(body, dict) and "title" in body:
            custom_title = str(body["title"]).strip()
            if custom_title:
                title = custom_title[:60]
    except Exception:
        pass  # Title is optional, default to "New Conversation"

    conv = db.create_conversation(title=title)
    return JSONResponse(
        {
            "id": conv.id,
            "title": conv.title,
            "created_at": conv.created_at,
            "updated_at": conv.updated_at,
            "message_count": conv.message_count,
        },
        status_code=201,
    )


async def list_conversations_handler(request: Request) -> JSONResponse:
    """Handle GET /conversations - List conversations sorted by most recently updated."""
    convs = db.list_conversations(limit=100)
    return JSONResponse(
        [
            {
                "id": c.id,
                "title": c.title,
                "created_at": c.created_at,
                "updated_at": c.updated_at,
                "message_count": c.message_count,
            }
            for c in convs
        ],
        status_code=200,
    )


async def get_conversation_handler(request: Request) -> JSONResponse:
    """Handle GET /conversations/{conversation_id} - Retrieve conversation and its messages."""
    conv_id = request.path_params.get("conversation_id")
    if not conv_id:
        return JSONResponse({"error": "Missing conversation_id"}, status_code=400)

    conv = db.get_conversation(conv_id)
    if not conv:
        return JSONResponse({"error": "Conversation not found"}, status_code=404)

    messages = db.get_messages(conv_id)
    return JSONResponse(
        {
            "id": conv.id,
            "title": conv.title,
            "created_at": conv.created_at,
            "updated_at": conv.updated_at,
            "message_count": conv.message_count,
            "messages": [
                {
                    "id": m.id,
                    "role": m.role,
                    "content": m.content,
                    "created_at": m.created_at,
                    "status": m.status,
                }
                for m in messages
            ],
        },
        status_code=200,
    )


async def delete_conversation_handler(request: Request) -> JSONResponse:
    """Handle DELETE /conversations/{conversation_id} - Delete conversation and its messages."""
    conv_id = request.path_params.get("conversation_id")
    if not conv_id:
        return JSONResponse({"error": "Missing conversation_id"}, status_code=400)

    conv = db.get_conversation(conv_id)
    if not conv:
        return JSONResponse({"error": "Conversation not found"}, status_code=404)

    deleted = db.delete_conversation(conv_id)
    if deleted:
        return JSONResponse({"status": "deleted", "id": conv_id}, status_code=200)
    return JSONResponse({"error": "Failed to delete conversation"}, status_code=500)
