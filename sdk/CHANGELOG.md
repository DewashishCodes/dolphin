# Changelog

## 0.2.0 (unreleased)

Dolphin becomes usable without any setup, and as shared memory for AI agents.

### Added
- **SQLite backend**, now the default. `DolphinMemory()` with no arguments stores to `~/.dolphin/dolphin.db`.
- **MCP server** (`dolphin mcp`) with `remember`, `recall`, `search`, `forget` and `graph_stats` tools.
- **Claude Code plugin** (`plugin/`): a memory brief at session start, recall on every prompt, and capture of durable facts after each response.
- **Local daemon** (`dolphin daemon start | stop | status`) that keeps the embedding model loaded for the hooks.
- **Scopes**: every method accepts `scope="..."`; agents use a per-project scope derived from the git remote, plus `user:global`.
- `DolphinMemory.capture()` distills an exchange into facts worth remembering.
- `DolphinMemory.delete(memory_id)` deletes a single memory.
- `extraction_profile="agent"` for project knowledge instead of personal facts.
- `dolphin` command: `mcp`, `daemon`, `hook`, `setup`, `doctor`.
- `fastembed` embedder (ONNX, no PyTorch) as the local default.
- Test suite under `sdk/tests`.

### Changed
- **Install:** the base package no longer depends on Supabase, LangChain or PyTorch. Supabase users install `dolphin-memory[supabase]`; Gemini/OpenAI extraction needs `dolphin-memory[cloud]`.
- `supabase_url` / `supabase_key` are optional. Passing them selects the Supabase backend, as before.
- All storage goes through a `StorageBackend` interface (`dolphin_memory/backends`).
- `add()` embeds the text once instead of twice when deduplicating.
- Importing `dolphin_memory` is lazy, so the hook command starts quickly.

### Not yet verified
- Graph extraction and `capture()` against a real model with the new prompts (tested with stubs only).
- The Supabase backend after the move behind `StorageBackend`.

## 0.1.0

Initial release: Supabase-backed vector + knowledge-graph memory with Ollama extraction.
