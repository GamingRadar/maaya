# Inference Engine Module

The `app.engine` package is responsible for driving the local AI inference engine.

## Principles

1. **Decoupled Interface:**
   The rest of the application interacts with an abstract inference interface (`generate`), insulating the application from the underlying execution details.
2. **Adapters:**
   - **`GemmaEngine` (`app.engine.gemma`):** Executes the verified Termux package `llama-cli` via `asyncio.create_subprocess_exec` without `shell=True`. Uses `-st` (`--single-turn`) to ensure immediate process termination after single-turn generation, serialized via `asyncio.Lock`.
   - **Output Parsing (`extract_assistant_response`):** Robustly sanitizes interactive terminal headers (`available commands:`), prompt echoes, timing blocks (`[ Prompt: ... | Generation: ... ]`), and Gemma control tokens, while supporting fallback stream inspection if buffering routes text to `stderr`.
3. **No Cloud Fallbacks:**
   All execution is purely local.
4. **Diagnostic Tooling:**
   - `probe_llama.py`: Standalone script to inspect stdout vs stderr behavior, exit codes, and timing metrics directly on the target phone.
