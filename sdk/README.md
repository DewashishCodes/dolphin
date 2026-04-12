<p align="center">
  <img width="100" height="100" alt="dolphin_logo" src="https://github.com/user-attachments/assets/5f652c60-7932-4a65-a3f5-0b7e2d3339ad" />
</p>

<div align="center">

# 🐬 Dolphin Memory

**Give your AI a brain. One line of code.**

Persistent, graph-enhanced memory for LLMs. Dolphin builds a Knowledge Graph of facts, preferences, and relationships — so your AI actually remembers.

<img src="https://img.shields.io/badge/Python-3.10+-blue?style=for-the-badge&logo=python" />
<img src="https://img.shields.io/badge/Local_LLM-Llama_3.2-orange?style=for-the-badge" />
<img src="https://img.shields.io/badge/Database-Supabase-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white" />
<img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" />

</div>

---

## ⚡ Quick Start (5 minutes)

### 1. Install

```bash
pip install dolphin-memory
```

### 2. Auto-Setup (Ollama + Llama 3.2)

```bash
dolphin-setup
```

This automatically:
- ✅ Installs [Ollama](https://ollama.com) (local LLM runtime)
- ✅ Downloads `llama3.2` model (~2GB)
- ✅ Prints Supabase schema setup instructions

### 3. Set Up Supabase

1. Create a free project at [supabase.com](https://supabase.com)
2. Go to **SQL Editor** → paste the schema from `dolphin_memory/schema.sql` → **RUN**
3. Copy your **Project URL** and **anon key** from Settings → API

### 4. Use It

```python
from dolphin_memory import DolphinMemory

# Initialize
memory = DolphinMemory(
    supabase_url="https://your-project.supabase.co",
    supabase_key="your-anon-key",
)

# Store memories — Dolphin extracts facts into a Knowledge Graph automatically
memory.add("I'm a software engineer living in Mumbai. I love Python and rock climbing.", user_id="dewashish")

# Search by meaning (not just keywords)
results = memory.search("What does the user do?", user_id="dewashish")
# → [{'content': {'value': 'software engineer living in Mumbai...'}, 'similarity': 0.89}]

# Get rich context for your LLM (combines vector search + Knowledge Graph)
context = memory.get_context("Suggest something fun to do this weekend", user_id="dewashish")
# → "MEMORIES:\n- software engineer in Mumbai, loves rock climbing\n\nKNOWLEDGE GRAPH:\n- User LIVES_IN Mumbai\n- User LIKES Rock Climbing"

# Inject into any LLM
response = your_llm.invoke(f"Context about user:\n{context}\n\nUser: Suggest something fun")
```

---

## 🧠 How It Works

Dolphin combines **two retrieval systems** for deeper recall:

```
User Message: "I live in Mumbai and work at Google"
                    │
                    ▼
    ┌───────────────────────────────┐
    │  1. VECTOR MEMORY             │  Stores full text with embeddings
    │     (Semantic Search)         │  → "software engineer in Mumbai..."
    └───────────────────────────────┘
                    │
                    ▼
    ┌───────────────────────────────┐
    │  2. KNOWLEDGE GRAPH           │  Extracts structured facts
    │     (GraphRAG)                │  → User -[LIVES_IN]→ Mumbai
    │                               │  → User -[WORKS_AT]→ Google
    └───────────────────────────────┘
```

When you call `get_context()`, Dolphin:
1. **Searches** vector memories by semantic similarity
2. **Traverses** the Knowledge Graph for structured facts + relationships
3. **Combines** both into a single context string for your LLM

---

## 📖 API Reference

### `DolphinMemory(supabase_url, supabase_key, **config)`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `supabase_url` | str | *required* | Your Supabase project URL |
| `supabase_key` | str | *required* | Your Supabase anon key |
| `ollama_model` | str | `"llama3.2"` | Local model for extraction |
| `embedding_model` | str | `"all-mpnet-base-v2"` | Sentence-transformer model |
| `similarity_threshold` | float | `0.25` | Min similarity for search (0–1) |
| `auto_extract` | bool | `True` | Auto-extract graph triples on `add()` |

### Core Methods

| Method | Description |
|--------|-------------|
| `add(text, user_id)` | Store a memory + extract graph triples |
| `search(query, user_id, limit)` | Semantic similarity search |
| `get_context(query, user_id)` | Get combined context string for LLM injection |
| `get_graph(user_id)` | Get full Knowledge Graph (nodes + edges) |
| `get_stats(user_id)` | Get node/edge counts |
| `consolidate(user_id)` | Merge duplicate nodes (Synaptic Pruning) |
| `delete_user(user_id)` | Delete ALL memories for a user |
| `get_all_memories(user_id)` | List all stored memories |

---

## 🔌 Use With Any LLM

### OpenAI

```python
from openai import OpenAI
from dolphin_memory import DolphinMemory

client = OpenAI()
memory = DolphinMemory(supabase_url="...", supabase_key="...")

def chat(user_message, user_id):
    # 1. Store the message
    memory.add(user_message, user_id=user_id)

    # 2. Get context
    context = memory.get_context(user_message, user_id=user_id)

    # 3. Generate response with memory
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": f"You have memory about this user:\n{context}"},
            {"role": "user", "content": user_message},
        ]
    )
    return response.choices[0].message.content
```

### LangChain

```python
from langchain_openai import ChatOpenAI
from dolphin_memory import DolphinMemory

llm = ChatOpenAI(model="gpt-4o")
memory = DolphinMemory(supabase_url="...", supabase_key="...")

context = memory.get_context("Tell me about myself", user_id="user_1")
response = llm.invoke(f"Context:\n{context}\n\nUser: Tell me about myself")
```

### Google Gemini

```python
import google.generativeai as genai
from dolphin_memory import DolphinMemory

genai.configure(api_key="...")
model = genai.GenerativeModel("gemini-2.5-flash")
memory = DolphinMemory(supabase_url="...", supabase_key="...")

context = memory.get_context("What's my favorite language?", user_id="u1")
response = model.generate_content(f"Context:\n{context}\n\nUser: What's my favorite language?")
```

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────┐
│               DolphinMemory                     │
│                                                 │
│  add() ──→ MemoryStore ──→ Supabase (pgvector)  │
│         ──→ TripleExtractor ──→ Ollama          │
│         ──→ GraphEngine ──→ Supabase (graph)    │
│                                                 │
│  search() ──→ Vector Similarity (pgvector)      │
│                                                 │
│  get_context() ──→ Vector + GraphRAG combined   │
└─────────────────────────────────────────────────┘
```

**Why Ollama (Local)?** Triple extraction runs on every `add()` call. Using a cloud LLM would cost $0.001–0.01 per message. With Ollama, it's **free forever** and works offline.

---

## 🤝 Contributing

PRs welcome! See the main [Dolphin repo](https://github.com/DewashishCodes/dolphin) for architecture docs.

## 📄 License

MIT — use it however you want.

---

Made with ❤️ by [DewashishCodes](https://github.com/DewashishCodes)
