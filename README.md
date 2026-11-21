# MAAYA

**Offline-First Personal AI Companion**

MAAYA is a personal AI companion designed to act as a thoughtful second perspective: someone who listens, remembers important ideas and projects, helps organise daily life, and supports reflection.

Its personality is inspired by the collaborative dynamic between Sherlock Holmes and Dr. John Watson: intelligent, observant, thoughtful, curious, supportive, and occasionally challenging.

MAAYA is **not** a generic chatbot, a therapist, or an autonomous decision-maker.

---

## Target Hardware & Runtime Environment

MAAYA is engineered specifically to run entirely on mobile hardware without cloud reliance:

- **Target Device:** Realme 3 Pro (Android 11 / Realme UI 2.0, non-rooted, stock Android).
- **SoC:** Qualcomm Snapdragon 710 (`sdm710`), 8 cores (2x Kryo 360 Gold @ 2.2 GHz + 6x Kryo 360 Silver @ 1.7 GHz).
- **Architecture:** ARM64 / aarch64.
- **Physical Memory:** 6 GB RAM.
- **Storage:** 64 GB onboard storage.
- **AI Inference Engine:** `llama.cpp` packaged via Termux (`llama-cli` v1.0.0).
- **Model:** Gemma 3 1B IT Q4_K_M (`google_gemma-3-1b-it-Q4_K_M.gguf`).
- **Observed Performance:** ~6.8–7.2 tokens/second at 1,024–2,048 context lengths with zero thermal throttling or crashes.

> **Important Architecture Principle:**
> The primary execution environment is the Android phone inside Termux. The development laptop is purely an editor/workstation and is **never** used as an inference host or cloud backend.

---

## Core Capabilities (Roadmap)

- **Configurable Personality:** Natural conversational companion with distinct analytical and supportive traits.
- **Decoupled Memory System:** SQLite-backed persistence independent of language model state.
- **Idea Vault & Project Tracking:** Explicit logging of projects, decisions, ideas, and tasks.
- **Privacy-Guaranteed Reflection:** Optional personal journal with strict user consent gates before storing sensitive reflections.
- **Reminders & Daily Planning:** Lightweight offline scheduling and action items.
- **Local Voice Support:** Native Android Text-to-Speech (TTS) and offline Speech-to-Text (STT).
- **Private Cross-Device Access:** Local network / WireGuard / Tailscale access for laptop-to-phone UI viewing without cloud exposure.

---

## Technology Stack

- **Backend:** Python (Starlette + Uvicorn) bound strictly to `127.0.0.1`.
- **Database:** SQLite (embedded, zero-configuration, robust ACID guarantees).
- **Inference Runtime:** `llama.cpp` (Termux packaged build).
- **Frontend:** Lightweight HTML5, modern CSS, and minimal vanilla JavaScript (no heavy node build steps or large bundle frameworks).
- **Audio/Voice:** Android native subsystem (TTS / speech APIs).

---

## Directory Layout

```text
maaya/
├── README.md              # Project overview, hardware details, workflow
├── ARCHITECTURE.md        # Technical architecture, module contracts, boundaries
├── .gitignore             # Exclusions for Python env, SQLite databases, models
├── requirements.txt       # Minimal, mobile-friendly Python dependencies
├── config.example.toml    # Reference non-secret configuration
├── app/                   # Backend application package
│   ├── __init__.py
│   ├── main.py            # Starlette application entrypoint
│   ├── config.py          # Configuration loader
│   ├── api/               # API route definitions
│   ├── engine/            # Inference engine adapters (subprocess / HTTP)
│   ├── memory/            # SQLite schemas and memory management
│   ├── projects/          # Project tracking and idea vault logic
│   └── services/          # Supporting services (reminders, planning, journal)
├── tests/                 # Unit and contract tests
└── docs/                  # Architecture notes, hardware testing logs, runbooks
```

---

## Development Workflow

1. **Laptop Development:**
   - Author, review, and test code on the laptop.
   - Run unit tests and static validation.
   - Commit and push changes to the private GitHub repository.
2. **Phone Deployment via Termux:**
   - Pull latest commits via `git pull` inside Termux on the phone.
   - Update Python environment if dependencies change (`pip install -r requirements.txt`).
   - Run the local application and verify performance against the phone's CPU and memory constraints.
3. **Model & Data Isolation:**
   - Model files (`*.gguf`) remain stored exclusively in `~/MAAYA/models/` on the phone.
   - Personal databases (`*.db`) remain on the phone and are never tracked in Git.

---

## Getting Started

### Local Development / Linting on Laptop

```bash
# Create and activate virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy example configuration
cp config.example.toml config.toml

# Run basic tests
pytest
```

### Running on Android (Termux)

```bash
cd ~/MAAYA
git pull
pip install -r requirements.txt
python -m app.main
```

### Accessing the Web Chat Interface

1. Start the server inside Termux:
   ```bash
   python -m app.main
   ```
2. Open your Android browser (Chrome, Firefox, etc.) on the phone and navigate to:
   ```text
   http://127.0.0.1:8000
   ```
3. **Conversations and Persistence (Phase 5):**
   - Click the hamburger menu icon (top left) to open the **Conversations Drawer**.
   - Create new conversations or switch between previous chats.
   - All conversations, user messages, and model responses are stored locally in SQLite (`data/maaya.db`).
   - Conversations survive browser reloads, server restarts, and phone reboots.
   - Gemma 3 1B automatically receives previous conversation turns (up to the configured `max_history_turns`) for multi-turn dialogue context.
   - Delete conversations deliberately with the trash icon (includes confirmation).

### Database Management & Backup

- **Database Location:** `data/maaya.db` (and SQLite WAL files `data/maaya.db-wal`, `data/maaya.db-shm`).
- **Backup:**
  ```bash
  # Safe backup using SQLite .backup or file copy when server is idle
  mkdir -p backups
  sqlite3 data/maaya.db ".backup 'backups/maaya_backup_$(date +%Y%m%d_%H%M%S).db'"
  ```
- **Restore:**
  ```bash
  # Stop the server, then restore:
  cp backups/your_backup.db data/maaya.db
  ```

### Testing the Chat API via cURL

In another Termux session or local shell:

```bash
# Health check
curl -X GET http://127.0.0.1:8000/health

# Create a conversation
curl -X POST http://127.0.0.1:8000/conversations \
  -H "Content-Type: application/json" \
  -d '{"title": "Test Chat"}'
# Response: {"id": "<conv_id>", "title": "Test Chat", ...}

# List conversations
curl -X GET http://127.0.0.1:8000/conversations

# Send a message into a conversation (with history context)
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello MAAYA, introduce yourself briefly.", "conversation_id": "<conv_id>"}'

# Retrieve conversation history
curl -X GET http://127.0.0.1:8000/conversations/<conv_id>

# Delete a conversation
curl -X DELETE http://127.0.0.1:8000/conversations/<conv_id>
```

