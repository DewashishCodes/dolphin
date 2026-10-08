<p align="center">
  <img width="100" height="100" alt="dolphin_logo"
       src="https://github.com/user-attachments/assets/5f652c60-7932-4a65-a3f5-0b7e2d3339ad" />
</p>

<div align="center">

# 🐬 Dolphin: Persistent Graph Memory for LLM Apps and AI Agents

Dolphin is a memory layer that combines **vector search** with a **knowledge graph**.
Use it as a Python SDK inside your LLM application, or as shared memory for Claude Code and other local agents, where what one session learns the next one already knows.

<img src="https://img.shields.io/badge/Python-3.10+-blue?style=for-the-badge&logo=python" />
<img src="https://img.shields.io/badge/Storage-SQLite_or_Supabase-3ECF8E?style=for-the-badge" />
<img src="https://img.shields.io/badge/Protocol-MCP-6E56CF?style=for-the-badge" />
<img src="https://img.shields.io/badge/Local_LLM-Ollama-orange?style=for-the-badge" />
<img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" />
</div>

## Two ways to use it

| | Memory for your LLM app | Shared memory for agents |
|---|---|---|
| **What** | A Python SDK: `add`, `search`, `get_context` | An MCP server and a Claude Code plugin |
| **Who remembers** | Your app's users, one namespace per `user_id` | Every agent session working on the same project |
| **Storage** | Local SQLite file, or Supabase for server-side apps | Local SQLite file shared by all sessions on the machine |
| **Start here** | [SDK quick start](#-sdk-quick-start) | [Agent quick start](#-agent-quick-start-claude-code) |

Full reference: [`sdk/README.md`](sdk/README.md). Internals: [`ARCHITECTURE.md`](ARCHITECTURE.md).

---

## ⚡ SDK quick start

> [!NOTE]
> Version 0.2.0 (local SQLite storage, MCP server, Claude Code plugin) is not on PyPI yet; `pip install dolphin-memory` currently gives 0.1.0, which requires Supabase. Until it is published, install from source:
> ```bash
> pip install "git+https://github.com/DewashishCodes/dolphin@main#subdirectory=sdk"
> ```

```bash
pip install dolphin-memory
```

```python
from dolphin_memory import DolphinMemory

# Local by default: memories live in ~/.dolphin/dolphin.db. No account, no server.
memory = DolphinMemory()

memory.add("I'm a software engineer in Mumbai. I love rock climbing.", user_id="u1")

context = memory.get_context("Suggest a weekend activity", user_id="u1")
# ### RELEVANT MEMORIES
# - [Just now]: I'm a software engineer in Mumbai. I love rock climbing.
#
# ### KNOWLEDGE GRAPH
# User LIKES Rock Climbing (Sport)
# User LIVES_IN Mumbai (City)
```

Inject `context` into your system prompt. For server-side apps, install `dolphin-memory[supabase]` and pass `supabase_url` / `supabase_key`; the API is the same.

Storing and searching memories works out of the box. Building the knowledge graph needs an LLM, by default a local [Ollama](https://ollama.com) model:

```bash
dolphin setup    # installs Ollama and pulls llama3.2
dolphin doctor   # checks that everything is healthy
```

---

## 🤖 Agent quick start (Claude Code)

```bash
pip install dolphin-memory
```
```
/plugin marketplace add DewashishCodes/dolphin
/plugin install dolphin-memory@dolphin
```

From then on, in every project:

| When | What happens |
|------|--------------|
| A session starts | A short brief of the project's most recent memories is added to context |
| You send a prompt | Memories related to that prompt are recalled and added to it |
| Claude finishes responding | The exchange is distilled; decisions, conventions and gotchas are stored, routine work is not |

Claude also gets `remember`, `recall`, `search`, `forget` and `graph_stats` tools, and the `/dolphin-memory:recall`, `/dolphin-memory:remember` and `/dolphin-memory:status` commands.

Memories are scoped to the project (its git remote), so every clone and every session of one repository shares them. Open a second terminal, start a new session, and it knows what the first one decided.

Only want the tools, or using another MCP client? Skip the plugin:

```bash
claude mcp add dolphin -- dolphin mcp
```

---

## 🧠 How it works

1. **Semantic layer.** Every memory is embedded and stored. Near-duplicates reinforce the existing memory instead of piling up.
2. **Graph layer.** An LLM extracts `(subject) -[RELATIONSHIP]-> (object)` triples in the background and merges them into a knowledge graph.
3. **Hybrid recall.** A query finds similar memories, then similar graph nodes, then walks one hop out from those nodes, so related facts surface even when they share no words with the query.
4. **Consolidation.** `consolidate()` asks the LLM to merge duplicate graph nodes ("Bill Gates", "William Gates III").

Everything runs locally by default: SQLite for storage, an ONNX embedding model, and Ollama for extraction. Gemini and OpenAI are optional extraction providers.

---

## 📁 Repository layout

| Path | What it is |
|------|------------|
| `sdk/` | The `dolphin-memory` Python package: SDK, MCP server, daemon, hooks, CLI |
| `plugin/` | The Claude Code plugin (hooks, MCP config, skills) |
| `.claude-plugin/` | Marketplace manifest that publishes `plugin/` |
| `docs/` | Landing page (Firebase Hosting) |
| `server.py`, `database/`, `static/` | The original Dolphin chat demo with a 3D graph view; see below |

### Development

```bash
python -m venv venv
venv/Scripts/python -m pip install -e "sdk[dev]"   # bin/ instead of Scripts/ on macOS/Linux
cd sdk && ../venv/Scripts/python -m pytest -q
```

The tests use a fake embedder and a stubbed extractor, so they need no model downloads, Ollama, or Supabase.

---

## 🕸️ The original chat demo

Dolphin started as a chat app that builds a global knowledge graph and renders it as an interactive 3D force graph. It still lives at the repository root and runs on Supabase + Gemini/Ollama, separately from the SDK.

https://github.com/user-attachments/assets/c2197f3a-10ba-40e1-a7b2-59e3b170ac4c

<details>
<summary>Run the chat demo</summary>

1. Create a [Supabase](https://supabase.com/) project and run `supabase/migrations/20260214062656_remote_schema.sql`, then `supabase/migrations/20260412000000_v2_critical_fixes.sql`, in the SQL Editor.
2. Copy `.env.example` to `.env` and fill in `SUPABASE_URL`, `SUPABASE_KEY` and `GOOGLE_API_KEY`.
3. Install [Ollama](https://ollama.com/) and run `ollama pull llama3.2`.
4. `pip install -r requirements.txt`
5. `uvicorn server:app --reload`, then open http://localhost:8000.

</details>

---

## 🗺️ Roadmap

- [x] `dolphin-memory` SDK on PyPI
- [x] Local SQLite backend, no setup
- [x] MCP server
- [x] Claude Code plugin with automatic recall and capture
- [ ] Claude as an extraction provider
- [ ] Capture at session end and before compaction
- [ ] Recall ranking by recency and reinforcement
- [ ] Graph viewer for the local store
- [ ] Dolphin Cloud: managed, team-shared memory

---

Made with ❤️ by DewashishCodes
