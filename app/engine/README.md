# Inference Engine Module

The `app.engine` package is responsible for driving the local AI inference engine.

## Principles

1. **Decoupled Interface:**
   The rest of the application interacts with an abstract inference interface (`generate`), insulating the application from the underlying execution details.
2. **Adapters:**
   - **`GemmaEngine` (`app.engine.gemma`):** Executes the verified Termux package `llama-cli` via `asyncio.create_subprocess_exec` without `shell=True`. Concurrency is strictly serialized via `asyncio.Lock` to prevent multiple model instances from exhausting phone RAM.
3. **Execution Flags & Stream Separation:**
   - `-st` (`--single-turn`): Runs a single generation turn and immediately exits.
   - `--simple-io`: **Essential on Termux / Android.** Disables interactive terminal control characters, complex redraws, and TTY curses mode. It ensures `stdout` is properly flushed and captured by Python subprocess pipes instead of 0-byte capture.
   - `-ngl 0`: Forces CPU execution, bypassing missing or broken mobile GPU/Vulkan drivers.
   - `--no-warmup`: Prevents redundant warmup compute iterations on battery-powered mobile hardware.
4. **Stream Roles:**
   - `stdout`: Contains the model generation stream. Only `stdout` is extracted and sanitized as the assistant response.
   - `stderr`: Contains backend initialization, device offload notices, and GPU warnings (e.g. Vulkan fallbacks). Stderr is never treated as assistant text. If `stdout` yields no response, `EmptyResponseError` is raised.
5. **Output Parsing (`extract_assistant_response`):**
   - Sanitizes ANSI escape sequences.
   - Strips prompt echo (matching full prompt or `<start_of_turn>model` marker).
   - Strips timing lines (`[ Prompt: ... | Generation: ... ]`, `llama_print_timings`, etc.) and process headers.
   - Strips Gemma turn tokens (`<start_of_turn>`, `<end_of_turn>`).
   - Preserves normal multiline conversational text.
6. **Diagnostic Tooling:**
   - `probe_llama.py`: Standalone script to inspect stdout vs stderr behavior, exit codes, and stream lengths directly on the target phone.
