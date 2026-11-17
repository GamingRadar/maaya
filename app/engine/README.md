# Inference Engine Module

The `app.engine` package is responsible for driving the local AI inference engine.

## Principles

1. **Decoupled Interface:**
   The rest of the application interacts with an abstract inference interface (`generate`), insulating the application from the underlying execution details.
2. **Adapters:**
   - **`CLIAdapter`:** Executes the verified Termux package `llama-cli` via `asyncio.create_subprocess_exec`. This is the proven runtime on the Snapdragon 710 target device.
   - **`ServerAdapter`:** Can communicate via HTTP with `llama-server` if that mode is confirmed and running.
3. **No Cloud Fallbacks:**
   All execution is purely local.

