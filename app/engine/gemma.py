"""Gemma 3 1B inference engine adapter using llama-cli subprocess.

Safely invokes the Termux-packaged llama-cli on Android/ARM64, handling:
- Subprocess execution without shell=True
- Process concurrency serialization via asyncio.Lock to protect device RAM
- Output cleaning (stripping llama.cpp logs, banner, stats, and echoed prompts)
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


def clean_llama_output(raw_stdout: str, prompt: str) -> str:
    """Strip llama.cpp banners, timing stats, prompt echo, and Gemma turn tokens."""
    text = raw_stdout

    # Strip prompt echo if present at start
    if prompt and text.startswith(prompt):
        text = text[len(prompt):]

    # Remove Gemma turn tokens
    text = text.replace("<start_of_turn>model", "")
    text = text.replace("<start_of_turn>", "")
    text = text.replace("<end_of_turn>", "")

    # Strip llama.cpp timing/diagnostic lines (e.g., "llama_print_timings: ...", "load time = ...")
    lines = []
    for line in text.splitlines():
        trimmed = line.strip()
        # Common llama.cpp diagnostic prefixes
        if trimmed.startswith("llama_") or trimmed.startswith("ggml_"):
            continue
        if re.match(r"^(load|sample|prompt eval|eval|total) time\s*=", trimmed):
            continue
        if trimmed.startswith("main: ") or trimmed.startswith("system_info:"):
            continue
        lines.append(line)

    cleaned = "\n".join(lines).strip()
    return cleaned


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
        # Check direct path if provided
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

            # 5. Check exit code
            if process.returncode != 0:
                logger.error(
                    "Inference subprocess exited with code %d. Stderr: %s",
                    process.returncode,
                    stderr_data.decode("utf-8", errors="replace")[:200],
                )
                raise ProcessExecutionError("Inference process failed")

            # 6. Parse and clean output
            raw_output = stdout_data.decode("utf-8", errors="replace")
            cleaned_text = clean_llama_output(raw_output, prompt)

            if not cleaned_text:
                logger.warning("Inference completed but output was empty")
                raise EmptyResponseError("Inference returned empty response")

            return GenerationResult(
                text=cleaned_text,
                model=self.inference_settings.model_name,
            )
