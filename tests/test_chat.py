"""Automated tests for Gemma inference engine and /chat endpoint."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from starlette.testclient import TestClient

from app.api.chat import engine
from app.config import InferenceSettings, PersonalitySettings
from app.engine.exceptions import (
    EmptyResponseError,
    ExecutableNotFoundError,
    InferenceTimeoutError,
    ModelNotFoundError,
    ProcessExecutionError,
)
from app.engine.gemma import (
    GemmaEngine,
    GenerationResult,
    clean_llama_output,
    extract_assistant_response,
    format_gemma_prompt,
)
from app.main import app

client = TestClient(app)


# ============================================================================
# Engine Unit Tests (Formatting, Output Cleaning, Real Termux Output Parsing)
# ============================================================================

def test_format_gemma_prompt():
    """Verify Gemma turn markers format correctly."""
    prompt = format_gemma_prompt("Be helpful.", "Hello")
    assert "<start_of_turn>system\nBe helpful.<end_of_turn>" in prompt
    assert "<start_of_turn>user\nHello<end_of_turn>" in prompt
    assert prompt.endswith("<start_of_turn>model\n")


def test_clean_llama_output_strips_diagnostics():
    """Verify clean_llama_output removes prompt echo, llama timings, and tags."""
    prompt = "<start_of_turn>system\nSystem<end_of_turn>\n<start_of_turn>user\nHi<end_of_turn>\n<start_of_turn>model\n"
    raw_output = (
        prompt
        + "Hello! I am MAAYA.\n"
        + "<end_of_turn>\n"
        + "llama_print_timings:        load time =     210.12 ms\n"
        + "llama_print_timings:      sample time =      15.02 ms\n"
        + "total time =     450.00 ms\n"
    )

    cleaned = extract_assistant_response(raw_output, prompt)
    assert cleaned == "Hello! I am MAAYA."


def test_real_termux_output_parsing():
    """Verify parser extracts response from real Termux llama-cli output with interactive banner and stats."""
    prompt = (
        "<start_of_turn>system\n"
        "You are MAAYA.<end_of_turn>\n"
        "<start_of_turn>user\n"
        "Hello! Briefly introduce yourself.<end_of_turn>\n"
        "<start_of_turn>model\n"
    )

    # Reconstruct the exact output format reported from the Realme 3 Pro device
    real_device_output = (
        "Loading model...\n"
        "build : b8256\n"
        "available commands:\n"
        "  /exit or Ctrl+C     stop or exit\n"
        "  /regen              regenerate the last response\n"
        "  /clear              clear the chat history\n"
        "  /read <file>        add a text file\n"
        "  /glob <pattern>     add text files using globbing pattern\n"
        "> "
        + prompt
        + "Hello! I'm MAAYA, your thoughtful personal companion inspired by Holmes and Watson. "
        + "I am here to help you reflect, organize ideas, and think clearly.\n"
        + "<end_of_turn>\n"
        + "[ Prompt: 10.7 t/s | Generation: 7.1 t/s ]\n"
        + "Exiting...\n"
    )

    cleaned = extract_assistant_response(real_device_output, prompt)
    expected = (
        "Hello! I'm MAAYA, your thoughtful personal companion inspired by Holmes and Watson. "
        "I am here to help you reflect, organize ideas, and think clearly."
    )
    assert cleaned == expected


def test_multiline_assistant_response_preserved():
    """Verify multiline response is preserved without losing legitimate paragraphs."""
    raw = (
        "Loading model...\n"
        "> Hello! I am MAAYA.\n\n"
        "Here are three things I can do:\n"
        "1. Listen to your thoughts.\n"
        "2. Help track your projects.\n"
        "3. Provide reflective insights.\n\n"
        "How can I help you today?\n"
        "[ Prompt: 12.0 t/s | Generation: 7.0 t/s ]\n"
        "Exiting...\n"
    )
    cleaned = extract_assistant_response(raw)
    assert "1. Listen to your thoughts." in cleaned
    assert "2. Help track your projects." in cleaned
    assert "3. Provide reflective insights." in cleaned
    assert "How can I help you today?" in cleaned
    assert "Exiting..." not in cleaned
    assert "Prompt:" not in cleaned


def test_empty_raw_output():
    """Verify empty raw output returns empty string."""
    assert extract_assistant_response("") == ""
    assert extract_assistant_response("   \n\n  ") == ""


@pytest.mark.anyio
async def test_engine_missing_executable():
    """Verify engine raises ExecutableNotFoundError when binary is not in path."""
    inf_cfg = InferenceSettings(llama_cli_path="non_existent_llama_binary_xyz")
    pers_cfg = PersonalitySettings()
    test_engine = GemmaEngine(inf_cfg, pers_cfg)

    with pytest.raises(ExecutableNotFoundError):
        await test_engine.generate("test")


@pytest.mark.anyio
async def test_engine_missing_model():
    """Verify engine raises ModelNotFoundError when model file is not found."""
    inf_cfg = InferenceSettings(
        llama_cli_path="llama-cli",
        model_path="/non/existent/path/to/model.gguf",
    )
    pers_cfg = PersonalitySettings()
    test_engine = GemmaEngine(inf_cfg, pers_cfg)

    with patch("shutil.which", return_value="/mock/bin/llama-cli"):
        with pytest.raises(ModelNotFoundError):
            await test_engine.generate("test")


@pytest.mark.anyio
async def test_engine_successful_execution(tmp_path):
    """Verify successful subprocess execution and output extraction."""
    dummy_model = tmp_path / "model.gguf"
    dummy_model.write_text("dummy")

    inf_cfg = InferenceSettings(
        llama_cli_path="llama-cli",
        model_path=str(dummy_model),
        threads=2,
        context_size=512,
        max_tokens=64,
        timeout=10.0,
    )
    pers_cfg = PersonalitySettings()
    test_engine = GemmaEngine(inf_cfg, pers_cfg)

    mock_process = AsyncMock()
    mock_process.returncode = 0
    mock_process.communicate.return_value = (
        b"Loading model...\n[ Prompt: 10 t/s | Generation: 7 t/s ]\nI am MAAYA, pleased to assist you.\nExiting...\n",
        b"",
    )

    with patch("shutil.which", return_value="/mock/bin/llama-cli"):
        with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
            res = await test_engine.generate("Hello")
            assert res.text == "I am MAAYA, pleased to assist you."
            assert res.model == "gemma-3-1b"

            mock_exec.assert_called_once()
            args = mock_exec.call_args[0]
            assert args[0] == "/mock/bin/llama-cli"
            assert "-m" in args
            assert "-st" in args
            assert "--no-warmup" in args


@pytest.mark.anyio
async def test_engine_stream_fallback_to_stderr(tmp_path):
    """Verify engine extracts answer from stderr if stdout was empty due to stream redirection."""
    dummy_model = tmp_path / "model.gguf"
    dummy_model.write_text("dummy")

    inf_cfg = InferenceSettings(
        llama_cli_path="llama-cli",
        model_path=str(dummy_model),
    )
    test_engine = GemmaEngine(inf_cfg, PersonalitySettings())

    mock_process = AsyncMock()
    mock_process.returncode = 0
    # stdout empty, stderr contains the output
    mock_process.communicate.return_value = (
        b"",
        b"Loading model...\navailable commands:\n  /exit stop\n> Hello from MAAYA via stderr!\n[ Prompt: 10 t/s | Generation: 7 t/s ]\nExiting...\n",
    )

    with patch("shutil.which", return_value="/mock/bin/llama-cli"):
        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            res = await test_engine.generate("Hello")
            assert res.text == "Hello from MAAYA via stderr!"


@pytest.mark.anyio
async def test_engine_subprocess_timeout(tmp_path):
    """Verify engine raises InferenceTimeoutError on subprocess timeout."""
    dummy_model = tmp_path / "model.gguf"
    dummy_model.write_text("dummy")

    inf_cfg = InferenceSettings(
        llama_cli_path="llama-cli",
        model_path=str(dummy_model),
        timeout=0.01,
    )
    test_engine = GemmaEngine(inf_cfg, PersonalitySettings())

    mock_process = AsyncMock()
    mock_process.communicate.side_effect = asyncio.TimeoutError()
    mock_process.kill = AsyncMock(return_value=None)
    mock_process.wait = AsyncMock(return_value=None)

    with patch("shutil.which", return_value="/mock/bin/llama-cli"):
        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with pytest.raises(InferenceTimeoutError):
                await test_engine.generate("Hello")


@pytest.mark.anyio
async def test_engine_non_zero_exit(tmp_path):
    """Verify engine raises ProcessExecutionError on non-zero exit code."""
    dummy_model = tmp_path / "model.gguf"
    dummy_model.write_text("dummy")

    inf_cfg = InferenceSettings(
        llama_cli_path="llama-cli",
        model_path=str(dummy_model),
    )
    test_engine = GemmaEngine(inf_cfg, PersonalitySettings())

    mock_process = AsyncMock()
    mock_process.returncode = 1
    mock_process.communicate.return_value = (b"", b"Error: failed to allocate memory")

    with patch("shutil.which", return_value="/mock/bin/llama-cli"):
        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with pytest.raises(ProcessExecutionError):
                await test_engine.generate("Hello")


@pytest.mark.anyio
async def test_engine_empty_response(tmp_path):
    """Verify engine raises EmptyResponseError if output contains no assistant content."""
    dummy_model = tmp_path / "model.gguf"
    dummy_model.write_text("dummy")

    inf_cfg = InferenceSettings(
        llama_cli_path="llama-cli",
        model_path=str(dummy_model),
    )
    test_engine = GemmaEngine(inf_cfg, PersonalitySettings())

    mock_process = AsyncMock()
    mock_process.returncode = 0
    mock_process.communicate.return_value = (b"Loading model...\n[ Prompt: 10 t/s | Generation: 7 t/s ]\nExiting...\n", b"")

    with patch("shutil.which", return_value="/mock/bin/llama-cli"):
        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with pytest.raises(EmptyResponseError):
                await test_engine.generate("Hello")


@pytest.mark.anyio
async def test_engine_concurrency_serialization(tmp_path):
    """Verify multiple concurrent generate() calls are serialized through the lock."""
    dummy_model = tmp_path / "model.gguf"
    dummy_model.write_text("dummy")

    inf_cfg = InferenceSettings(
        llama_cli_path="llama-cli",
        model_path=str(dummy_model),
    )
    test_engine = GemmaEngine(inf_cfg, PersonalitySettings())

    active_executions = 0
    max_concurrent_observed = 0

    async def mock_communicate():
        nonlocal active_executions, max_concurrent_observed
        active_executions += 1
        max_concurrent_observed = max(max_concurrent_observed, active_executions)
        await asyncio.sleep(0.05)
        active_executions -= 1
        return (b"Response text", b"")

    mock_process = AsyncMock()
    mock_process.returncode = 0
    mock_process.communicate.side_effect = mock_communicate

    with patch("shutil.which", return_value="/mock/bin/llama-cli"):
        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            results = await asyncio.gather(
                test_engine.generate("Req 1"),
                test_engine.generate("Req 2"),
                test_engine.generate("Req 3"),
            )
            assert len(results) == 3
            assert max_concurrent_observed == 1


# ============================================================================
# API /chat Endpoint Integration Tests
# ============================================================================

def test_chat_valid_request():
    """Verify POST /chat returns 200 with model and response."""
    with patch.object(
        engine,
        "generate",
        new=AsyncMock(return_value=GenerationResult(text="Hello! I am MAAYA.", model="gemma-3-1b")),
    ):
        response = client.post("/chat", json={"message": "Hello MAAYA"})
        assert response.status_code == 200
        data = response.json()
        assert data["response"] == "Hello! I am MAAYA."
        assert data["model"] == "gemma-3-1b"


def test_chat_missing_message():
    """Verify POST /chat without 'message' returns 400."""
    response = client.post("/chat", json={})
    assert response.status_code == 400
    assert "Missing 'message' field" in response.json()["error"]


def test_chat_empty_message():
    """Verify POST /chat with empty message returns 400."""
    response = client.post("/chat", json={"message": "   "})
    assert response.status_code == 400
    assert "'message' cannot be empty" in response.json()["error"]


def test_chat_invalid_message_type():
    """Verify POST /chat with non-string message returns 400."""
    response = client.post("/chat", json={"message": 12345})
    assert response.status_code == 400
    assert "'message' must be a string" in response.json()["error"]


def test_chat_malformed_json():
    """Verify POST /chat with malformed JSON returns 400."""
    response = client.post(
        "/chat",
        content="This is not JSON",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400
    assert "Invalid JSON" in response.json()["error"]


def test_chat_message_length_exceeded():
    """Verify POST /chat rejects messages exceeding max_message_length."""
    oversized = "A" * 5000
    response = client.post("/chat", json={"message": oversized})
    assert response.status_code == 400
    assert "exceeds maximum allowed length" in response.json()["error"]


def test_chat_missing_model_error():
    """Verify POST /chat returns 503 without revealing filesystem paths."""
    with patch.object(
        engine,
        "generate",
        new=AsyncMock(side_effect=ModelNotFoundError("internal/path/not/found")),
    ):
        response = client.post("/chat", json={"message": "Hello"})
        assert response.status_code == 503
        data = response.json()
        assert data["error"] == "Model file is not available on the host"
        assert "internal/path" not in str(data)


def test_chat_missing_executable_error():
    """Verify POST /chat returns 503 without revealing binary paths."""
    with patch.object(
        engine,
        "generate",
        new=AsyncMock(side_effect=ExecutableNotFoundError("binary missing")),
    ):
        response = client.post("/chat", json={"message": "Hello"})
        assert response.status_code == 503
        data = response.json()
        assert data["error"] == "Inference executable is not available on the host"


def test_chat_timeout_error():
    """Verify POST /chat returns 504 on timeout."""
    with patch.object(
        engine,
        "generate",
        new=AsyncMock(side_effect=InferenceTimeoutError("Timeout")),
    ):
        response = client.post("/chat", json={"message": "Hello"})
        assert response.status_code == 504
        assert response.json()["error"] == "Inference timed out"


def test_chat_process_execution_error():
    """Verify POST /chat returns 500 on process failure."""
    with patch.object(
        engine,
        "generate",
        new=AsyncMock(side_effect=ProcessExecutionError("Exit 1")),
    ):
        response = client.post("/chat", json={"message": "Hello"})
        assert response.status_code == 500
        assert response.json()["error"] == "Inference process failed"
