# 🐬 Dolphin: AI with Persistent Graph Memory

Dolphin is a **Neural Memory Graph AI** that retains knowledge across conversations. Unlike standard chatbots that forget everything when you start a new thread, Dolphin builds a **Global Knowledge Graph** of facts, preferences, and relationships, allowing for hyper-personalized interactions.

## 🚀 Key Features

### 🧠 Global Knowledge Graph
- **Persistent Memory:** Facts extracted from one conversation (e.g., "I live in Pune") are instantly available in all future chats, even new threads.
- **GraphRAG:** Retrieval isn't just semantic; it traverses a structured graph to find related concepts (e.g., "Deadline" -> "Friday" -> "Project X").

### 🕸️ Interactive 3D Visualization
- **Live Graph:** See your brain grow in real-time.
- **Explorable:** Zoom, pan, and hover over nodes to see connections using our customized 3D Force Graph engine.

### 🤖 Multi-LLM Support
- **Bring Your Own Key:** Switch between **Google Gemini**, **OpenAI (GPT-4)**, and **Groq (Llama 3)** instantly from the UI.
- **Dynamic Instantiation:** The backend hot-swaps the LLM engine based on your settings for each request.

### ⚡ "Fast Fill" Mode
- **Quick Memorization:** Toggle "Fast Fill" to instantly inject facts into the graph without waiting for a full LLM response.

---

## 🛠️ Tech Stack

- **Frontend:** Vanilla JS (ES Modules), Three.js, 3d-force-graph
- **Backend:** FastAPI (Python), Uvicorn
- **Database:** Supabase (PostgreSQL + pgvector)
- **AI Orchestration:** LangChain
- **LLMs:** Gemini 1.5 Flash, GPT-4, Llama 3 (via Groq)

---

This project is still under development and to give a gist of what it does: it basically solves the problem with LLM api's and memory. 
That's all I can say right now but very soon beta version for testing will get released. 

Best Regards,
Dewashish
