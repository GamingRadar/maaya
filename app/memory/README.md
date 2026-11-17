# Memory Module

The `app.memory` package provides the persistent storage foundation for MAAYA.

## Fundamental Rule

**The language model is NOT the source of truth.** All durable state is stored explicitly in SQLite.

## Components

- **Database Repository:** Encapsulates standard library `sqlite3` access with WAL (Write-Ahead Logging) mode enabled for concurrent read safety.
- **Conversations:** History of interactions, including role, content, and timestamp.
- **Long-Term Memory:** User-approved facts, preferences, and personal details. Requires explicit consent before writing.
- **Context Assembler:** Dynamically builds the prompt context injected into the engine, ensuring system prompts, relevant memories, and recent messages stay within target context boundaries (e.g. 2048 tokens).

