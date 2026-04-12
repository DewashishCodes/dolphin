<p align="center">
  <img width="120" height="120" alt="dolphin_logo" src="https://github.com/user-attachments/assets/5f652c60-7932-4a65-a3f5-0b7e2d3339ad" />
</p>

<div align="center">

# 🐬 Dolphin Memory
### Give your AI a brain. One line of code.

**Dolphin** is a production-grade memory layer for LLMs that combines **Vector Retrieval** with **Knowledge Graphs**. It transforms raw conversations into structured facts and relationships, ensuring your AI remembers exactly who the user is, what they like, and how they relate to the world.

[**Quick Start**](#-quick-start-5-minutes) • [**How It Works**](#-how-it-works) • [**API Reference**](#-api-reference) • [**Cloud Fallback**](#-cloud-fallback)

<img src="https://img.shields.io/badge/Python-3.10+-blue?style=for-the-badge&logo=python" />
<img src="https://img.shields.io/badge/Local_LLM-Llama_3.2-orange?style=for-the-badge" />
<img src="https://img.shields.io/badge/Database-Supabase-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white" />

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

### 1. Install
```bash
pip install dolphin-memory
```

### 2. Auto-Setup (Ollama + Models)
```bash
# This downloads Ollama and the llama3.2 model automatically
dolphin-setup
```

### 3. Run the "Doctor" 🩺
Ensure your environment is ready to ship:
```bash
dolphin-setup doctor
```

### 4. Basic Usage
```python
from dolphin_memory import DolphinMemory

# Initialize
memory = DolphinMemory(
    supabase_url="https://your-project.supabase.co",
    supabase_key="your-anon-key"
)

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
| `supabase_url` | str | *required* | Your Supabase project URL |
| `supabase_key` | str | *required* | Your Supabase anon key |
| `ollama_model` | str | `"llama3.2"` | Local model for fact extraction |
| `deduplicate` | bool | `True` | Prevent redundant memory rows |
| `dedupe_threshold` | float| `0.92` | Similarity score (0-1) for merging |
| `enable_background_extraction` | bool | `True` | Run LLM extraction in a thread pool |

### Core Methods

*   **`add(text, user_id, metadata=None)`**: Returns a `memory_id`. Triggers background graph extraction.
*   **`get_context(query, user_id)`**: Returns a Markdown string ready to be injected into a System Prompt.
*   **`prewarm()`**: Force-loads the embedding model and verifies Ollama connectivity. Recommended at startup.
*   **`search(query, user_id, limit=5)`**: Returns raw memory dicts with similarity scores.
*   **`get_stats(user_id)`**: Returns `{nodes: X, edges: Y}` for the specified user.

---

## 🌩️ Cloud Fallback (Optional)

Running locally is free and private, but if you need higher throughput or are running on low-power hardware, you can use a Cloud LLM for extraction:

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
