#!/usr/bin/env python3
"""Diagnostic script to probe llama-cli streams and output behavior on Termux / Android.

Usage:
    python probe_llama.py [model_path]

Tests:
1. stdout vs stderr stream distribution
2. Behavior of -st, --simple-io, and prompt echo
3. Performance timing lines and exit codes
"""

import asyncio
import os
import shutil
import sys


async def test_cmd(cmd_desc: str, cmd_args: list[str]):
    print("=" * 60)
    print(f"TEST: {cmd_desc}")
    print("CMD :", " ".join(cmd_args))
    print("-" * 60)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=30.0)
    except Exception as e:
        print(f"FAILED TO EXECUTE: {e}")
        return

    stdout_str = stdout_bytes.decode("utf-8", errors="replace")
    stderr_str = stderr_bytes.decode("utf-8", errors="replace")

    print(f"EXIT CODE: {proc.returncode}")
    print(f"STDOUT LEN: {len(stdout_str)} chars")
    print(f"STDERR LEN: {len(stderr_str)} chars")

    print("\n--- STDOUT SAMPLE (First 500 chars) ---")
    print(stdout_str[:500])
    if len(stdout_str) > 500:
        print("... [truncated] ...")
        print("--- STDOUT TAIL (Last 200 chars) ---")
        print(stdout_str[-200:])

    print("\n--- STDERR SAMPLE (First 500 chars) ---")
    print(stderr_str[:500])
    if len(stderr_str) > 500:
        print("... [truncated] ...")
        print("--- STDERR TAIL (Last 200 chars) ---")
        print(stderr_str[-200:])


async def main():
    llama_bin = shutil.which("llama-cli") or "llama-cli"
    model_path = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/MAAYA/models/google_gemma-3-1b-it-Q4_K_M.gguf")

    print(f"Binary : {llama_bin}")
    print(f"Model  : {model_path} (exists: {os.path.isfile(model_path)})")

    if not os.path.isfile(model_path):
        print("Model file not found. Pass model path as argument: python probe_llama.py /path/to/model.gguf")
        return

    prompt = "<start_of_turn>user\nSay 'MAAYA DIAGNOSTIC SUCCESS' in one short sentence.<end_of_turn>\n<start_of_turn>model\n"

    # Test 1: Baseline command with -st
    await test_cmd(
        "Single-turn with -st",
        [llama_bin, "-m", model_path, "-c", "512", "-n", "32", "-t", "2", "-ngl", "0", "--no-warmup", "-st", "-p", prompt],
    )

    # Test 2: Adding --simple-io
    await test_cmd(
        "Single-turn with -st and --simple-io",
        [llama_bin, "-m", model_path, "-c", "512", "-n", "32", "-t", "2", "-ngl", "0", "--no-warmup", "-st", "--simple-io", "-p", prompt],
    )


if __name__ == "__main__":
    asyncio.run(main())
