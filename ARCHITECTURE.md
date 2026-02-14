# Dolphin Architecture

## Overview
Dolphin is a **Hybrid Neuro-Symbolic System** that combines the flexibility of Large Language Models (LLMs) with the structured precision of a Knowledge Graph.

---

## 1. The Global Knowledge Graph (`database/graph_engine.py`)
Unlike traditional RAG which retrieves chunks of text, Dolphin retrieves **Structured Triples** (Subject -> Predicate -> Object).

- **Global Scope:** The graph is decoupled from `session_id`. A constant `GLOBAL_GRAPH_ID` is used for all graph operations, meaning facts learned in *Thread A* are accessible in *Thread B*.
- **Extraction:** A background process (using `llama3.2` via Ollama or Gemini) runs on every user message to extract new facts and "Upsert" them into Supabase.
- **Pruning:** A "Sleep Cycle" mechanism uses an LLM to identify and merge duplicate nodes (e.g., "Bill Gates" and "William Gates III") to keep the graph clean.

## 2. Dynamic LLM Factory (`database/connection.py`)
Dolphin supports model agnosticism through a proprietary **LLM Factory Pattern**.

- **Workflow:**
  1. Frontend sends a `ChatRequest` containing an optional `llm_config` object (Provider + API Key).
  2. The `DatabaseManager.get_llm()` method inspects this config.
  3. It dynamically instantiates the corresponding LangChain wrapper (`ChatOpenAI`, `ChatGroq`, etc.) for *that specific request*.
  4. This allows multiple users to use different models simultaneously on the same server instance.

## 3. Hybrid Retrieval Context (`database/memory_engine.py`)
When generating a response, Dolphin constructs a context window from three sources:

1.  **Working Memory:** The last 10 messages of the *current* conversation (Session-specific).
2.  **Semantic Memory:** Vector search matches from the `user_memories` table (Long-term text).
3.  **Graph Context:** 
    - **1-Hop Neighbors:** Explicit connections to the user or entities mentioned in the query.
    - **Visual Traversal:** The system "looks" at the graph to find indirect paths (e.g., User -> Lives In -> Pune -> Weather).

## 4. Frontend Architecture
- **No Build Step:** Uses native ES Modules (`import ... from 'https://esm.sh/...'`) for modern browser support without Webpack/Vite complexity.
- **State Management:** heavily relies on `localStorage` for:
    - Chat History (per session)
    - LLM Settings
    - UI Preferences (Fast Fill toggle)
- **Visualization:** `3d-force-graph` rendered on a Canvas overlay, communicating with the DOM via exposed window functions.

## 5. Database Schema (Supabase)

### `graph_nodes`
- `id`: UUID
- `session_id`: String (Now mostly `GLOBAL_GRAPH_ID`)
- `name`: Text (e.g., "Pune")
- `label`: Text (e.g., "City")
- `embedding`: Vector(768)

### `graph_edges`
- `source_id`: UUID (FK)
- `target_id`: UUID (FK)
- `relationship`: Text (e.g., "LOCATED_IN")