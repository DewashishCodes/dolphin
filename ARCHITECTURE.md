# Dolphin Architecture

Dolphin has two codebases in one repository:

1. **`sdk/dolphin_memory`**: the memory layer (SDK, MCP server, daemon, hooks). This is the product.
2. **The chat demo** at the repository root (`server.py`, `database/`, `static/`): the original app the SDK was extracted from.

---

## Part 1: The memory layer (`sdk/dolphin_memory`)

```
Claude Code session A ─┐  hooks: dolphin hook <event> ──> daemon (127.0.0.1) ─┐
Claude Code session B ─┤                                                      │
                       └─ MCP:   dolphin mcp (one per session) ───────────────┤
Python app ───────────── DolphinMemory(...) ──────────────────────────────────┤
                                                                              ▼
                                              DolphinMemory (client.py)
                                              ├─ MemoryStore (store.py)  ── embedder (embeddings.py)
                                              ├─ GraphEngine (graph.py)  ── TripleExtractor (extraction.py)
                                              └─ StorageBackend (backends/): SQLite | Supabase
```

### 1.1 Client (`client.py`)
`DolphinMemory` is the public API: `add`, `search`, `get_context`, `capture`, `get_graph`, `get_stats`, `consolidate`, `delete`, `delete_user`.

- `add()` embeds the text, checks for a near-duplicate (similarity above `dedupe_threshold` reinforces the existing memory), stores it, and schedules graph extraction on a two-thread pool so it returns immediately.
- `get_context()` returns a Markdown block of similar memories plus graph facts, ready for a system prompt.
- `capture()` asks the extraction LLM which durable facts an exchange contains and `add()`s each one. Most exchanges yield none.

### 1.2 Namespaces and scopes (`scopes.py`)
Every row carries a `session_id` namespace. There are two ways to choose it:

- `user_id="u1"` maps to `user_u1`. This is the SDK's per-user memory.
- `scope="..."` is used verbatim and takes precedence. Agents use `project:<git remote>` (for example `project:github.com/org/repo`) and `user:global`.

`project_scope(cwd)` uses the git remote so clones and worktrees share memory. Without a remote it falls back to a hash of the repository root, then of the directory. A repository rooted at the user's home directory (dotfiles) is ignored, so it does not swallow every folder beneath it.

### 1.3 Storage backends (`backends/`)
`StorageBackend` (`base.py`) is the only place persistence happens. Embeddings are computed by the caller and passed in.

| | `SQLiteBackend` | `SupabaseBackend` |
|---|---|---|
| Selected when | default | `supabase_url` is set, or `backend="supabase"` |
| Vector search | exact cosine in numpy over the namespace's rows | pgvector via the `match_memories` / `match_graph_nodes` functions |
| Concurrency | WAL mode; several processes share one file | Postgres |
| Schema | created on first use | `schema.sql`, run once in the SQL Editor |

The SQLite file records which embedding model wrote it and refuses to open with a different one, because vectors from different models are not comparable.

Tables (same shape in both): `user_memories` (text + embedding), `graph_nodes` (unique per namespace and name), `graph_edges` (unique per source, target and relationship; repeats raise `access_count` and `weight`).

### 1.4 Embeddings (`embeddings.py`)
- `fastembed` with `all-MiniLM-L6-v2` (384 dims, ONNX): default for SQLite. Small install, no PyTorch.
- `sentence-transformers` with `all-mpnet-base-v2` (768 dims): default for Supabase, matching the `vector(768)` columns.

Both are sentence-transformers models with similar score distributions, so the same similarity thresholds apply.

### 1.5 Extraction (`extraction.py`)
`TripleExtractor` runs prompts on Ollama (default) or Gemini/OpenAI, falling back to the other side when the answer is unusable.

- `extract(text)` returns triples. The prompt depends on `extraction_profile`: `personal` (facts about a person) or `agent` (files, modules, tools, decisions).
- `distill(exchange)` returns up to five self-contained facts worth keeping from a developer/agent exchange, or none.
- Anything matching common credential patterns is dropped before it is stored.

### 1.6 Graph (`graph.py`)
- `extract_and_sync` upserts nodes and edges for each triple.
- `get_context` combines the `User` node's direct edges, nodes semantically similar to the query, and a one-hop walk out from those nodes.
- `sleep_cycle_pruning` asks the LLM which nodes are duplicates and merges them.

### 1.7 MCP server (`mcp_server.py`)
`dolphin mcp` serves `remember`, `recall`, `search`, `forget` and `graph_stats` over stdio. Each session runs its own server process; they share the database. The default scope is the project the server was started in.

### 1.8 Daemon and hooks (`daemon.py`, `hook.py`)
Hooks run on every prompt, so they cannot afford to load an embedding model. A single daemon per machine keeps it loaded.

- **Daemon**: a stdlib HTTP server on `127.0.0.1`. It writes its port and a random token to `~/.dolphin/daemon.json` (owner-only); every POST must carry the token, which keeps other users and web pages out. It exits after 8 idle hours.
  - `/brief`: recent memories for a project.
  - `/recall`: memories above a stricter threshold than `search()`, from the project scope and `user:global`, plus relationship facts. Empty when nothing clearly relates.
  - `/capture`: pairs the response with the session's last prompt and queues `capture()` on a single worker.
- **Hook client**: `dolphin hook session-start | user-prompt-submit | stop`. Standard library only, starts the daemon on demand, swallows every error and always exits 0, so a memory problem can never block the agent.

### 1.9 Claude Code plugin (`plugin/`)
`hooks/hooks.json` wires the three hook events to `dolphin hook`, `.mcp.json` registers the MCP server, and `skills/` adds recall, remember and status commands. `.claude-plugin/marketplace.json` at the repository root publishes it.

---

## Part 2: The chat demo (repository root)

### 2.1 The Global Knowledge Graph (`database/graph_engine.py`)
Unlike traditional RAG which retrieves chunks of text, Dolphin retrieves **Structured Triples** (Subject -> Predicate -> Object).

- **Global Scope:** The graph is decoupled from `session_id`. A constant `GLOBAL_GRAPH_ID` is used for all graph operations, meaning facts learned in *Thread A* are accessible in *Thread B*.
- **Extraction:** A background process (using `llama3.2` via Ollama or Gemini) runs on every user message to extract new facts and "Upsert" them into Supabase.
- **Pruning:** A "Sleep Cycle" mechanism uses an LLM to identify and merge duplicate nodes (e.g., "Bill Gates" and "William Gates III") to keep the graph clean.

### 2.2 Dynamic LLM Factory (`database/connection.py`)
- The frontend sends a `ChatRequest` containing an optional `llm_config` object (Provider + API Key).
- `DatabaseManager.get_llm()` instantiates the corresponding LangChain wrapper (`ChatOpenAI`, `ChatGroq`, etc.) for that request, so different users can use different models on the same server.

### 2.3 Hybrid Retrieval Context (`database/memory_engine.py`)
When generating a response, the demo builds context from three sources:

1.  **Working Memory:** The last 10 messages of the current conversation.
2.  **Semantic Memory:** Vector search matches from the `user_memories` table.
3.  **Graph Context:** 1-hop neighbors of the user and of entities mentioned in the query.

### 2.4 Frontend
- **No Build Step:** native ES Modules loaded from `esm.sh`.
- **State:** `localStorage` for chat history, LLM settings and UI preferences.
- **Visualization:** `3d-force-graph` rendered on a canvas overlay.

### 2.5 Database Schema (Supabase)
The demo and the SDK's Supabase backend share the same tables: `graph_nodes`, `graph_edges`, `user_memories`, plus `conversation_logs` for the demo's chat history.
