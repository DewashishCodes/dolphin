# 🐬 Dolphin: Real-Time Long-Form Memory AI

Dolphin is a real-time AI assistant capable of retaining and recalling information across **1,000+ turns** without replaying conversation history or increasing system latency.

## 🚀 The Problem
Modern LLMs "forget" information as the conversation grows. Re-prompting the entire history is:
1. **Slow:** Increases latency per turn.
2. **Expensive:** Consumes massive token counts.
3. **Inaccurate:** Models suffer from "Lost in the Middle" syndrome.

## ✨ The Solution: Dolphin
Dolphin uses a **Structured Memory Vault**. Instead of searching through raw text, it extracts facts into queryable JSON objects.

### Key Features:
- **Instant Recall:** Recalls facts from Turn 1 at Turn 1,000 in < 2 seconds.
- **Context Awareness:** Automatically switches language or tone based on stored preferences.
- **Zero-Prompt Growth:** The context window stays small because only *relevant* facts are injected.
- **Hybrid Storage:** Combines the flexibility of Vector Search with the precision of JSONB schemas.

## 🛠️ Tech Stack
- **Model:** Gemini 2.5 Flash (via LangChain)
- **Embeddings:** Google `gemini-embedding-001` (768-dim)
- **Database:** Supabase (PostgreSQL + pgvector)
- **Interface:** Streamlit
- **Orchestration:** Python / Asyncio

## 📦 Installation & Setup

1. **Clone the Repo**
   ```bash
   git clone https://github.com/your-username/dolphin-memory-ai.git
   cd dolphin-memory-ai