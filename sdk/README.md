<p align="center">
  <img width="120" height="120" alt="dolphin_logo" src="https://github.com/user-attachments/assets/5f652c60-7932-4a65-a3f5-0b7e2d3339ad" />
</p>

<div align="center">

# 🐬 Dolphin Memory
### Give your AI a brain. One line of code.

**Dolphin** is a production-grade memory layer for LLMs that combines **Vector Retrieval** with **Knowledge Graphs**. It transforms raw conversations into structured facts and relationships, ensuring your AI remembers exactly who the user is, what they like, and how they relate to the world.

[**Quick Start**](#-quick-start-5-minutes) • [**Agents (MCP)**](#-use-it-from-claude-code-and-other-agents-mcp) • [**How It Works**](#-how-it-works) • [**API Reference**](#-api-reference) • [**Cloud Fallback**](#-cloud-fallback)

<img src="https://img.shields.io/badge/Python-3.10+-blue?style=for-the-badge&logo=python" />
<img src="https://img.shields.io/badge/Local_LLM-Llama_3.2-orange?style=for-the-badge" />
<img src="https://img.shields.io/badge/Storage-SQLite_or_Supabase-3ECF8E?style=for-the-badge" />

</div>

---

## 🚀 Why Dolphin?

Most memory systems are just "chat history backups." Dolphin is different:

*   **🧠 Hybrid Intelligence**: Combines semantic vector search with neighborhood graph traversal (GraphRAG).
*   **🏠 Local-First & Private**: Facts are extracted locally on your machine via [Ollama](https://ollama.com). No data leakage, no token costs for extraction.
*   **⚡ Non-blocking Architecture**: Memory storage and graph extraction happen in background threads. Your UI never freezes.
*   **🧹 Semantic Deduplication**: Automatically merges similar memories (e.g., "I love Python" and "I really enjoy Python") to prevent "memory clutter."
*   **🕓 Temporal Awareness**: Automatically tracks *when* memories were formed, giving your LLM relative time clues (e.g., `[2h ago]`).

---

## 💎 The Dolphin Edge

Compared to standard memory implementations, Dolphin provides a significant leap in both speed and depth.

| Capability | Basic Vector Memory | Dolphin Hybrid |
|------------|---------------------|----------------|
| **Recall Depth** | Content chunks only | Full Relationship Context |
| **Intelligence** | Semantic search | Relationship Reasoning (GraphRAG) |
| **Cost** | High (Cloud Tokens) | **Free** (Local Ollama) |
| **Latency** | Blocks main thread | **Non-blocking** (Async) |
| **Cleanliness**| Duplicate heavy | Auto-Deduplicated |

---

## ⚡ Quick Start (5 minutes)

> [!NOTE]
> Version 0.2.0 (local SQLite storage, MCP server, Claude Code plugin) is not on PyPI yet; `pip install dolphin-memory` currently gives 0.1.0, which requires Supabase. Until it is published, install from source:
> ```bash
> pip install "git+https://github.com/DewashishCodes/dolphin@main#subdirectory=sdk"
> ```

### 1. Install
```bash
pip install dolphin-memory
```

### 2. Use it
```python
from dolphin_memory import DolphinMemory

# Local by default: memories live in ~/.dolphin/dolphin.db. No account, no server.
memory = DolphinMemory()

# Optional: Load models into RAM/GPU to remove first-call lag
memory.prewarm()

# 1. Add a memory (Returns instantly; extraction happens in background)
memory.add("I'm a software engineer in Mumbai. I love rock climbing.", user_id="u1")

# 2. Get enriched context for your LLM
context = memory.get_context("Suggest a weekend activity", user_id="u1")

print(context)
# Output:
# ### RELEVANT MEMORIES
# - [Just now]: software engineer in Mumbai, loves rock climbing
#
# ### KNOWLEDGE GRAPH
# User LIKES Rock Climbing (Sport)
# User LIVES_IN Mumbai (City)
```

### 3. Knowledge graph extraction (Ollama)
Storing and searching memories works out of the box. Building the knowledge graph needs an LLM; by default that is a local [Ollama](https://ollama.com) model:
```bash
dolphin setup    # installs Ollama and pulls llama3.2
dolphin doctor   # checks that everything is healthy
```

---

## 🤖 Use it from Claude Code and other agents (MCP)

Dolphin ships an MCP server, so any MCP client can read and write the same memory. Every session on the machine shares one local database: what one session stores, the next one can recall.

```bash
claude mcp add dolphin -- dolphin mcp
```

| Tool | What it does |
|------|--------------|
| `remember(text)` | Store a fact, decision or preference |
| `recall(query)` | Relevant memories plus related knowledge-graph facts |
| `search(query, limit)` | Raw matches with ids and similarity scores |
| `forget(memory_id)` | Delete one memory |
| `graph_stats()` | Node and edge counts |

Memories are scoped to the project (the git remote of the directory the agent runs in), so every clone and every session of one repository shares them. Pass `scope: "user"` for preferences that apply to all projects. The server is configured with environment variables: `DOLPHIN_SCOPE`, `DOLPHIN_DB_PATH`, `DOLPHIN_EXTRACTION_PROVIDER`, `DOLPHIN_OLLAMA_MODEL`, and `SUPABASE_URL` / `SUPABASE_KEY` to use Supabase instead of the local file.

### Claude Code plugin: automatic memory

The plugin adds the MCP server plus hooks, so memory works without the agent having to ask for it:

```bash
pip install dolphin-memory
```
```
/plugin marketplace add DewashishCodes/dolphin
/plugin install dolphin-memory@dolphin
```

| When | What happens |
|------|--------------|
| Session starts | A short brief of the project's most recent memories is added to context |
| You send a prompt | Memories related to that prompt are recalled and added to it |
| Claude finishes responding | The exchange is distilled by the extraction model; decisions, conventions and gotchas are stored, routine work is not |

The hooks talk to a small local daemon (`dolphin daemon start | stop | status`) that keeps the embedding model loaded. It starts on demand, listens on `127.0.0.1` only, and shuts down after 8 idle hours. If it is unavailable, prompts go through untouched.

Automatic capture needs the extraction model (Ollama by default); recall and the tools work without it. Text that looks like a credential is never stored. Set `DOLPHIN_CAPTURE=0` to keep recall but stop capturing, or `DOLPHIN_DISABLE=1` to turn the hooks off, for example in a project's `.claude/settings.json` `env`.

---

## ☁️ Supabase backend

For server-side apps where memory must live in the cloud, use Supabase (Postgres + pgvector):

```bash
pip install "dolphin-memory[supabase]"
```

Run `dolphin_memory/schema.sql` in your Supabase SQL Editor, then:

```python
memory = DolphinMemory(
    supabase_url="https://your-project.supabase.co",
    supabase_key="your-anon-key",
)
```

The API is identical on both backends.

---

## 🧠 How It Works: The Hybrid Brain

Dolphin builds a **dual-layer memory** for every user:

1.  **Semantic Layer (Short-term)**: Uses embeddings to find memories that "feel" similar to the current query.
2.  **Graph Layer (Long-term)**: Extracts entities and relationships (Triples) into a Knowledge Graph. This allows the AI to "reason" across related facts (e.g., if you like Tokyo, it might remember you also like Ramen).

> [!TIP]
> **Semantic Deduplication**: Dolphin checks if a new memory is $>92\%$ similar to an existing one. If it is, it "reinforces" the old memory instead of creating a duplicate.

---

## 📖 API Reference

### `DolphinMemory(...)`
**Configuration Options:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `backend` | str | `"auto"` | `"sqlite"`, `"supabase"`, or `"auto"` (Supabase when `supabase_url` is set) |
| `db_path` | str | `~/.dolphin/dolphin.db` | SQLite file for the local backend |
| `supabase_url` | str | `""` | Your Supabase project URL |
| `supabase_key` | str | `""` | Your Supabase anon key |
| `embedding_provider` | str | `"auto"` | `"fastembed"` (local default) or `"sentence-transformers"` (Supabase default) |
| `ollama_model` | str | `"llama3.2"` | Local model for fact extraction |
| `deduplicate` | bool | `True` | Prevent redundant memory rows |
| `dedupe_threshold` | float| `0.92` | Similarity score (0-1) for merging |
| `enable_background_extraction` | bool | `True` | Run LLM extraction in a thread pool |
| `extraction_profile` | str | `"personal"` | `"personal"` (facts about a person) or `"agent"` (project knowledge from coding agents) |

### Core Methods

*   **`add(text, user_id, metadata=None)`**: Returns a `memory_id`. Triggers background graph extraction.
*   **`get_context(query, user_id)`**: Returns a Markdown string ready to be injected into a System Prompt.
*   **`prewarm()`**: Force-loads the embedding model and verifies Ollama connectivity. Recommended at startup.
*   **`search(query, user_id, limit=5)`**: Returns raw memory dicts with similarity scores.
*   **`capture(exchange, user_id)`**: Asks the extraction model which durable facts a conversation exchange contains and stores each one. Returns one result per stored fact; often none.
*   **`get_stats(user_id)`**: Returns `{nodes: X, edges: Y}` for the specified user.
*   **`delete(memory_id)`**: Deletes a single memory. `delete_user(user_id)` deletes everything for a user.

Every method that takes `user_id` also accepts `scope="..."`, a namespace used as-is (for example `scope="project:github.com/org/repo"`). It takes precedence over `user_id` and is what the agent integrations use.

---

## 🌩️ Cloud Fallback (Optional)

Running locally is free and private, but if you need higher throughput or are running on low-power hardware, you can use a Cloud LLM for extraction:

```bash
pip install "dolphin-memory[cloud]"
```

```python
memory = DolphinMemory(
    ...,
    extraction_provider="gemini", # or "openai"
    cloud_api_key="your-api-key"
)
```

---

## 📄 License
MIT © [DewashishCodes](https://github.com/DewashishCodes)

---
<p align="center">Made with ❤️ for the Agentic future.</p>
