# MAAYA Architecture Specification

## 1. System Overview & Principles

MAAYA is an offline-first personal AI assistant and reflective thinking partner running natively on an Android device (Realme 3 Pro / Snapdragon 710) via Termux.

### Fundamental Principles

1. **Independent Memory (Decoupled from LLM):**
   The Language Model (LLM) is an ephemerally stateless reasoning engine, *not* the repository of truth. All persistent state, memory, ideas, projects, and metadata reside in a structured SQLite database.
2. **Offline-First & Air-Gapped Operation:**
   The entire application runs locally. The web server binds to `127.0.0.1` by default. No data or telemetry leaves the physical phone.
3. **Hardware-Conscious Design:**
   With 6 GB total physical RAM and Snapdragon 710 (Kryo 360 cores), resource efficiency is paramount:
   - Inference uses Gemma 3 1B IT Q4_K_M (~1 GB memory footprint).
   - Minimal Python footprint (< 100 MB).
   - No heavyweight JS single-page app frameworks (React/Next.js/Angular) running on the device.
4. **User Agency and Privacy Gates:**
   Emotional reflections and personal memories are never automatically saved or indexed without explicit confirmation. No background profiling or covert surveillance.

---

## 2. High-Level Architecture Diagram

```
+---------------------------------------------------------------+
|                      User Interface                           |
|       (Lightweight HTML5 + CSS + Vanilla JS Frontend)         |
+-------------------------------+-------------------------------+
                                | HTTP / JSON (127.0.0.1:8000)
+-------------------------------v-------------------------------+
|                       Starlette Backend                       |
|                                                               |
|  +--------------------+  +------------------+  +-----------+  |
|  |     app.api        |  |   app.projects   |  |app.services| |
|  | (REST endpoints)   |  | (Vault & Tasks)  |  | (Reminders)| |
|  +---------+----------+  +--------+---------+  +-----+-----+  |
|            |                      |                  |        |
|  +---------v----------------------v------------------v-----+  |
|  |                    app.memory                           |  |
|  |     (SQLite Repository & Context Window Assembler)      |  |
|  +----------------------------+----------------------------+  |
|                               | Assembled Prompt Context      |
|  +----------------------------v----------------------------+  |
|  |                    app.engine                           |  |
|  |  (Inference Adapter: llama-cli Subprocess / HTTP Server)|  |
+--+----------------------------+-------------------------------+
                                |
             +------------------v------------------+
             |             llama.cpp               |
             |  (Packaged Termux binary aarch64)   |
             |   Gemma 3 1B IT Q4_K_M GGUF Model   |
             +-------------------------------------+
```

---

## 3. Module Responsibilities

### `app.config`
- Single source of truth for configuration using typed settings (Python standard library `dataclasses` and `tomllib`).
- Loads settings with fallback defaults, allowing overrides via `config.toml` or environment variables without code modification.
- Avoids Rust or native build toolchains (such as `pydantic-core`), ensuring direct compatibility with Android Termux environments.
- Never commits secrets or personal paths to version control.

### `app.api`
- Exposes RESTful HTTP endpoints for chat (`POST /chat`), conversations (`POST /conversations`, `GET /conversations`, `GET /conversations/{id}`, `DELETE /conversations/{id}`), health checks (`GET /health`), and static assets via Starlette routing.
- Implements request validation using Python standard library dataclasses and types.
- Binds strictly to `127.0.0.1` to prevent unauthorized network access.
- Handles malformed JSON, empty messages, and payload size bounds cleanly without leaking internal traces.

### `app.engine` (Inference Subsystem)
- Abstracts LLM communication behind a clean interface: `GemmaEngine.generate(user_message, history=None)`.
- **Primary Adapter (`GemmaEngine`):** Executes the Termux-packaged `llama-cli` executable via asynchronous subprocess (`asyncio.create_subprocess_exec`) without `shell=True`.
- **Multi-Turn Context Prompting:** Injects chronological previous dialogue turns formatted with Gemma turn tags (`<start_of_turn>user`, `<start_of_turn>model`), enabling multi-turn conversational context while bounding history to recent turns (`max_history_turns`).
- **Concurrency Serialization:** Enforces strict single-process execution using `asyncio.Lock` to ensure multiple concurrent requests cannot exhaust the phone's RAM.
- **Output Sanitization:** Strips llama.cpp banners, timing stats, echoed prompts, and Gemma turn tokens `<start_of_turn>` / `<end_of_turn>`.
- **Fault Tolerance:** Robust handling of timeouts, missing binaries, missing models, non-zero exits, and empty responses.
- Handles parameter translation (context length, temperature, top-p, thread limits).

### `app.memory` (Persistence & Knowledge Storage)
- Encapsulates SQLite operations using Python standard library `sqlite3` (no heavy ORM overhead on mobile).
- Connection management: connection-per-operation with WAL mode (`PRAGMA journal_mode = WAL`) and foreign key constraints enabled.
- **Conversations & Messages:**
  - `conversations` table: stores conversation ID, title, `created_at`, `updated_at`.
  - `messages` table: stores message ID, `conversation_id`, `role`, `content`, `created_at`, `status`.
  - Messages cascade on conversation deletion.
  - Transactions are committed atomically immediately after writing user messages and assistant responses; transactions are never held open across model generation.
- **Note on Scope:** Phase 5 provides full persistent conversation history. Long-term semantic memory / user-approved facts and vector indexing belong to later phases.

### `app.projects` (Idea Vault & Planning)
- Manages discrete user projects, goals, decisions, and related tasks.
- Links project notes and decisions to conversations where they originated.
- Distinct from broad conversational memory to allow purposeful project reviews.

### `app.services`
- **Reminders & Scheduler:** Lightweight task scheduling suitable for mobile environments without background process guarantees.
- **Journal & Reflection:** Secure, user-controlled entries with strict permission boundaries.
- **Voice / TTS Interface:** Abstraction for dispatching text-to-speech requests to Android native services (e.g. via Termux:API `termux-tts-speak`).

---

## 4. Mobile Execution & Lifecycle Considerations

1. **Android Low Memory Killer (OOM):**
   Android aggressively terminates background processes when physical memory is pressured. The backend state must be committed atomically to SQLite after every message so no state is lost if the process is terminated.
2. **Process Management:**
   Long-running background services on stock Android (Realme UI) may be stopped by battery optimization. A foreground notification or Termux wake-lock (`termux-wake-lock`) should be maintained during active usage sessions.
3. **Subprocess Concurrency:**
   The phone's Snapdragon 710 contains 2 performance cores (Gold) and 6 efficiency cores (Silver). CPU thread usage is capped at 4 threads to prevent thermal buildup and allow background system operations to run smoothly.

