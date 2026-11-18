"""Chat API route handlers."""

import json
import logging
from json import JSONDecodeError

from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings
from app.engine.exceptions import (
    EmptyResponseError,
    ExecutableNotFoundError,
    InferenceTimeoutError,
    ModelNotFoundError,
    ProcessExecutionError,
)
from app.engine.gemma import GemmaEngine

logger = logging.getLogger("maaya.api.chat")

# Global engine instance initialized with application settings
engine = GemmaEngine(
    inference_settings=settings.inference,
    personality_settings=settings.personality,
)


async def chat_handler(request: Request) -> JSONResponse:
    """Handle POST /chat requests."""
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

    # 4. Invoke inference engine with clean error handling
    try:
        result = await engine.generate(message)
        return JSONResponse(
            {
                "response": result.text,
                "model": result.model,
            },
            status_code=200,
        )
    except ModelNotFoundError:
        logger.error("Inference failed: Model file not found")
        return JSONResponse(
            {"error": "Model file is not available on the host"},
            status_code=503,
        )
    except ExecutableNotFoundError:
        logger.error("Inference failed: llama-cli executable not found")
        return JSONResponse(
            {"error": "Inference executable is not available on the host"},
            status_code=503,
        )
    except InferenceTimeoutError:
        logger.warning("Inference request timed out")
        return JSONResponse(
            {"error": "Inference timed out"},
            status_code=504,
        )
    except (ProcessExecutionError, EmptyResponseError):
        logger.error("Inference process failed or produced empty response")
        return JSONResponse(
            {"error": "Inference process failed"},
            status_code=500,
        )
    except Exception as exc:
        logger.error("Unexpected error during chat inference: %s", type(exc).__name__)
        return JSONResponse(
            {"error": "Internal server error"},
            status_code=500,
        )
