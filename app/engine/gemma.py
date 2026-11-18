"""Gemma 3 1B inference engine adapter using llama-cli subprocess.

Safely invokes the Termux-packaged llama-cli on Android/ARM64, handling:
- Subprocess execution without shell=True
- Process concurrency serialization via asyncio.Lock to protect device RAM
- Dual-stream (stdout/stderr) output inspection and robust cleaning
- Comprehensive error handling without leaking filesystem paths or traces
"""

import asyncio
import logging
import os
import re
import shutil
from dataclasses import dataclass
from typing import Optional

from app.config import InferenceSettings, PersonalitySettings
from app.engine.exceptions import (
    EmptyResponseError,
    ExecutableNotFoundError,
    InferenceError,
    InferenceTimeoutError,
    ModelNotFoundError,
    ProcessExecutionError,
)

logger = logging.getLogger("maaya.engine")


@dataclass
class GenerationResult:
    text: str
    model: str


def format_gemma_prompt(system_prompt: str, user_message: str) -> str:
    """Format input using Gemma turn markers (<start_of_turn>)."""
    return (
        f"<start_of_turn>system\n{system_prompt.strip()}<end_of_turn>\n"
        f"<start_of_turn>user\n{user_message.strip()}<end_of_turn>\n"
        f"<start_of_turn>model\n"
    )


def extract_assistant_response(raw_text: str, prompt: str = "") -> str:
    """Extract and sanitize generated assistant response from raw process output.

    Handles both stdout and mixed output cases:
    - Strips terminal banners, 'Loading model...', and 'available commands' blocks
    - Strips prompt echo (including full Gemma turns or raw prompt text)
    - Strips performance lines like '[ Prompt: ... | Generation: ... ]' and 'Exiting...'
    - Strips llama_print_timings, ggml_, and standard llama.cpp timing logs
    - Strips Gemma turn delimiters (<start_of_turn>, <end_of_turn>, etc.)
    - Preserves normal multiline conversational text from the model
    """
    if not raw_text:
        return ""

    text = raw_text

    # 1. Remove ANSI escape sequences (e.g., colors, cursor codes)
    text = re.sub(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])", "", text)

    # 2. If the text contains the interactive banner 'available commands:',
    # the actual response starts after the initial prompt marker (e.g. '>')
    # or after the 'available commands:' block.
    if "available commands:" in text:
        # Find where 'available commands:' block ends (usually ending with a prompt '>' or empty line)
        parts = text.split("available commands:", 1)
        after_banner = parts[1]
        lines = after_banner.splitlines()
        start_idx = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            # Skip commands like /exit, /regen, /clear, /read, /glob, /image
            if stripped.startswith("/") or stripped.startswith("stop or exit") or stripped.startswith("regenerate"):
                continue
            if stripped.startswith(">"):
                # If the line starts with '>', strip the leading '>' and start from this line
                lines[i] = stripped[1:].strip()
                start_idx = i
                break
            if stripped and not stripped.startswith("/"):
                # Non-command line found
                start_idx = i
                break
        text = "\n".join(lines[start_idx:])

    # 3. Strip prompt echo if present
    # Check full prompt match
    if prompt and prompt in text:
        text = text.split(prompt, 1)[-1]
    else:
        # Check if Gemma model tag marker was echoed: '<start_of_turn>model'
        if "<start_of_turn>model" in text:
            text = text.split("<start_of_turn>model", 1)[-1]

    # 4. Filter line-by-line for diagnostic headers, timings, and banners
    cleaned_lines = []
    for line in text.splitlines():
        trimmed = line.strip()

        # Skip empty lines at the very beginning of processing
        if not cleaned_lines and not trimmed:
            continue

        # Terminal / execution status lines
        if trimmed == "Exiting..." or trimmed == "Loading model..." or trimmed == ">":
            continue

        # Performance summary line: e.g. [ Prompt: 10.7 t/s | Generation: 7.1 t/s ]
        if re.match(r"^\[\s*Prompt:.*?Generation:.*?\]", trimmed):
            continue

        # Standard llama.cpp / ggml timing and diagnostic prefixes
        if trimmed.startswith("llama_") or trimmed.startswith("ggml_") or trimmed.startswith("main: ") or trimmed.startswith("srv "):
            continue
        if re.match(r"^(load|sample|prompt eval|eval|total)\s*time\s*=", trimmed):
            continue
        if trimmed.startswith("system_info:") or trimmed.startswith("sampler seed:"):
            continue

        # Skip residual command list lines if banner splitting left any
        if trimmed.startswith("/exit") or trimmed.startswith("/regen") or trimmed.startswith("/clear"):
            continue

        cleaned_lines.append(line)

    result = "\n".join(cleaned_lines)

    # 5. Clean turn tags
    result = result.replace("<start_of_turn>model", "")
    result = result.replace("<start_of_turn>user", "")
    result = result.replace("<start_of_turn>system", "")
    result = result.replace("<start_of_turn>", "")
    result = result.replace("<end_of_turn>", "")

    return result.strip()


# Backward compatibility alias
clean_llama_output = extract_assistant_response


class GemmaEngine:
    """Inference engine managing asynchronous llama-cli execution."""

    def __init__(
        self,
        inference_settings: InferenceSettings,
        personality_settings: PersonalitySettings,
    ):
        self.inference_settings = inference_settings
        self.personality_settings = personality_settings
        # Lock ensures only a single inference subprocess runs at any given time
        self._lock = asyncio.Lock()

    def _resolve_executable(self) -> str:
        """Resolve executable path, verifying existence in PATH or on disk."""
        exe = self.inference_settings.llama_cli_path
        resolved = shutil.which(exe)
        if resolved:
            return resolved
        expanded = os.path.expanduser(exe)
        if os.path.isfile(expanded) and os.access(expanded, os.X_OK):
            return expanded
        raise ExecutableNotFoundError("Inference executable not found")

    def _resolve_model(self) -> str:
        """Resolve model path, verifying existence on disk."""
        path = os.path.expanduser(self.inference_settings.model_path)
        if not os.path.isfile(path):
            raise ModelNotFoundError("Model file not found")
        return path

    async def generate(self, user_message: str) -> GenerationResult:
        """Execute inference subprocess for a user message, protected by concurrency lock."""
        async with self._lock:
            # 1. Validate environment
            exe_path = self._resolve_executable()
            model_path = self._resolve_model()

            # 2. Build prompt and CLI arguments
            prompt = format_gemma_prompt(
                self.personality_settings.system_prompt,
                user_message,
            )

            # Invocation configuration:
            # -st (--single-turn) guarantees non-interactive exit after one response
            # -p passes the formatted prompt
            cmd = [
                exe_path,
                "-m", model_path,
                "-c", str(self.inference_settings.context_size),
                "-n", str(self.inference_settings.max_tokens),
                "-t", str(self.inference_settings.threads),
                "-ngl", "0",
                "--no-warmup",
                "-st",
                "-p", prompt,
            ]

            logger.info("Executing inference subprocess with %d threads", self.inference_settings.threads)

            # 3. Spawn subprocess safely without shell=True
            try:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            except Exception as e:
                logger.error("Failed to spawn inference process: %s", type(e).__name__)
                raise ProcessExecutionError("Failed to start inference process") from e

            # 4. Await process completion with configured timeout
            try:
                stdout_data, stderr_data = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.inference_settings.timeout,
                )
            except asyncio.TimeoutError:
                logger.warning("Inference subprocess timed out after %s seconds", self.inference_settings.timeout)
                try:
                    res = process.kill()
                    if asyncio.iscoroutine(res):
                        await res
                except Exception:
                    pass
                try:
                    await process.wait()
                except Exception:
                    pass
                raise InferenceTimeoutError("Inference timed out")

            stdout_str = stdout_data.decode("utf-8", errors="replace")
            stderr_str = stderr_data.decode("utf-8", errors="replace")

            # Diagnostic logging (safe metadata only: returncode and stream lengths)
            logger.info(
                "Subprocess finished: returncode=%d, stdout_len=%d, stderr_len=%d",
                process.returncode,
                len(stdout_str),
                len(stderr_str),
            )
            # Safe truncated sample logging (up to 80 chars, without logging full user message)
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("stdout sample: %r", stdout_str[:80])
                logger.debug("stderr sample: %r", stderr_str[:80])

            # 5. Check exit code
            if process.returncode != 0:
                logger.error(
                    "Inference subprocess exited with code %d. Stderr snippet: %s",
                    process.returncode,
                    stderr_str[:120].strip(),
                )
                raise ProcessExecutionError("Inference process failed")

            # 6. Parse and extract generated assistant response
            # In standard llama-cli execution, stdout receives the generation.
            # If stdout is empty due to stream redirection behavior, fallback to checking stderr.
            cleaned_text = extract_assistant_response(stdout_str, prompt)
            if not cleaned_text and stderr_str:
                logger.info("stdout yielded no response; checking stderr channel")
                cleaned_text = extract_assistant_response(stderr_str, prompt)

            if not cleaned_text:
                logger.warning(
                    "Inference completed (code %d) but extracted text was empty. stdout_len=%d, stderr_len=%d",
                    process.returncode,
                    len(stdout_str),
                    len(stderr_str),
                )
                raise EmptyResponseError("Inference returned empty response")

            return GenerationResult(
                text=cleaned_text,
                model=self.inference_settings.model_name,
            )
