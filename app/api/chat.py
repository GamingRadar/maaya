"""Chat API route handlers."""

import json
import logging
from json import JSONDecodeError
from typing import List, Optional

from starlette.requests import Request
from starlette.responses import JSONResponse

from app.api.conversations import db
from app.config import settings
from app.engine.exceptions import (
    EmptyResponseError,
    ExecutableNotFoundError,
    InferenceTimeoutError,
    ModelNotFoundError,
    ProcessExecutionError,
)
from app.engine.gemma import GemmaEngine
from app.memory.database import Message

logger = logging.getLogger("maaya.api.chat")

# Global engine instance initialized with application settings
engine = GemmaEngine(
    inference_settings=settings.inference,
    personality_settings=settings.personality,
)


def generate_title_from_message(message: str, max_length: int = 36) -> str:
    """Generate a clean, concise title from the user's first message."""
    cleaned = " ".join(message.strip().splitlines())
    if len(cleaned) <= max_length:
        return cleaned
    return cleaned[:max_length].rstrip() + "..."


async def chat_handler(request: Request) -> JSONResponse:
    """Handle POST /chat requests.

    Supports optional conversation_id for multi-turn persistence,
    while maintaining 100% backward compatibility with legacy requests without conversation_id.
    """
    # 1. Parse JSON body
    try:
        body = await request.json()
    except (JSONDecodeError, ValueError):
        return JSONResponse(
            {"error": "Invalid JSON in request body"},
            status_code=400,
        )

    if not isinstance(body, dict):
        return JSONResponse(
            {"error": "Request body must be a JSON object"},
            status_code=400,
        )

    # 2. Validate "message" field
    if "message" not in body:
        return JSONResponse(
            {"error": "Missing 'message' field"},
            status_code=400,
        )

    message = body["message"]
    if not isinstance(message, str):
        return JSONResponse(
            {"error": "'message' must be a string"},
            status_code=400,
        )

    message = message.strip()
    if not message:
        return JSONResponse(
            {"error": "'message' cannot be empty"},
            status_code=400,
        )

    # 3. Check message length limit
    max_len = settings.app.max_message_length
    if len(message) > max_len:
        return JSONResponse(
            {"error": f"Message exceeds maximum allowed length of {max_len} characters"},
            status_code=400,
        )

    # 4. Check optional conversation_id
    conversation_id = body.get("conversation_id")
    conv = None
    history_messages: List[Message] = []
    user_msg_id: Optional[str] = None

    if conversation_id:
        if not isinstance(conversation_id, str):
            return JSONResponse({"error": "conversation_id must be a string"}, status_code=400)

        conv = db.get_conversation(conversation_id)
        if not conv:
            return JSONResponse({"error": "Conversation not found"}, status_code=404)

        # Retrieve previous messages for context window assembly
        existing_messages = db.get_messages(conversation_id)
        # Apply max history limit (last N turns)
        limit = settings.storage.max_history_turns
        if limit > 0 and len(existing_messages) > limit:
            history_messages = existing_messages[-limit:]
        else:
            history_messages = existing_messages

        # Persist user message with 'completed' status immediately
        user_msg = db.add_message(
            conversation_id=conversation_id,
            role="user",
            content=message,
            status="completed",
        )
        user_msg_id = user_msg.id

        # Update conversation title if it's the first message and still titled "New Conversation"
        if conv.title == "New Conversation" and len(existing_messages) == 0:
            new_title = generate_title_from_message(message)
            db.update_conversation_title(conversation_id, new_title)

    # 5. Invoke inference engine with clean error handling
    # Convert history_messages to role/content list
    history_payload = [
        {"role": m.role, "content": m.content}
        for m in history_messages
        if m.status == "completed"
    ] if conv else None

    try:
        result = await engine.generate(message, history=history_payload)

        # If conversation exists, persist assistant response
        if conv:
            db.add_message(
                conversation_id=conversation_id,
                role="assistant",
                content=result.text,
                status="completed",
            )

        resp_payload = {
            "response": result.text,
            "model": result.model,
        }
        if conv:
            resp_payload["conversation_id"] = conversation_id

        return JSONResponse(resp_payload, status_code=200)

    except ModelNotFoundError:
        logger.error("Inference failed: Model file not found")
        if user_msg_id:
            db.update_message_status(user_msg_id, "failed")
        return JSONResponse(
            {"error": "Model file is not available on the host"},
            status_code=503,
        )
    except ExecutableNotFoundError:
        logger.error("Inference failed: llama-cli executable not found")
        if user_msg_id:
            db.update_message_status(user_msg_id, "failed")
        return JSONResponse(
            {"error": "Inference executable is not available on the host"},
            status_code=503,
        )
    except InferenceTimeoutError:
        logger.warning("Inference request timed out")
        if user_msg_id:
            db.update_message_status(user_msg_id, "failed")
        return JSONResponse(
            {"error": "Inference timed out"},
            status_code=504,
        )
    except (ProcessExecutionError, EmptyResponseError):
        logger.error("Inference process failed or produced empty response")
        if user_msg_id:
            db.update_message_status(user_msg_id, "failed")
        return JSONResponse(
            {"error": "Inference process failed"},
            status_code=500,
        )
    except Exception as exc:
        logger.error("Unexpected error during chat inference: %s", type(exc).__name__)
        if user_msg_id:
            db.update_message_status(user_msg_id, "failed")
        return JSONResponse(
            {"error": "Internal server error"},
            status_code=500,
        )
