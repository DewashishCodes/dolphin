<p align="center">
  <img width="100" height="100" alt="dolphin_logo"
       src="https://github.com/user-attachments/assets/5f652c60-7932-4a65-a3f5-0b7e2d3339ad" />
</p>

<div align="center">

# 🐬 Dolphin: AI with Persistent Graph Memory

Dolphin is a **Neural Memory Graph AI** that retains knowledge across conversations.  
Unlike standard chatbots that forget everything when you start a new thread, Dolphin builds a **Global Knowledge Graph** of facts, preferences, and relationships, allowing for hyper-personalized interactions.

<img src="https://img.shields.io/badge/Python-3.10+-blue?style=for-the-badge&logo=python" />
<img src="https://img.shields.io/badge/Backend-FastAPI-009688?style=for-the-badge&logo=fastapi" />
<img src="https://img.shields.io/badge/Database-Supabase-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white" />
<img src="https://img.shields.io/badge/Vector-pgvector-336791?style=for-the-badge&logo=postgresql" />
<img src="https://img.shields.io/badge/LLM-Gemini_3.0_Flash-4285F4?style=for-the-badge&logo=google" />
<img src="https://img.shields.io/badge/Local_LLM-Llama_3.2-orange?style=for-the-badge" />
<img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" />
</div>

## 🎥 Demo

https://github.com/user-attachments/assets/c2197f3a-10ba-40e1-a7b2-59e3b170ac4c

## 🏗️ Architecture
<div align="center">
<img width="829" height="493" alt="Screenshot 2026-02-13 112856" src="https://github.com/user-attachments/assets/59e219c8-2530-4640-9c9d-5a9708f4bd7c" />
</div>


## 🚀 Key Features

### 🧠 1. Global Neural Graph (Cross-Session Memory)
Dolphin doesn't just "remember" the last 10 messages. It builds a permanent **Knowledge Graph** in Supabase.
- **Fact Extraction:** Every time you chat, Dolphin extracts entities and relationships (e.g., `(User) -[LIVES_IN]-> (San Francisco)`).
- **Global Access:** Start a new chat session, and Dolphin *still knows* who you are. The graph is global, not session-locked.

### 🔗 2. GraphRAG & Hybrid Retrieval
Traditional RAG (Vector Search) is often not enough. Dolphin combines it with **Graph Traversal**.
- **The "Mental Map":** If you ask about "deadlines", Dolphin doesn't just look for the word "deadline". It traverses the graph: `Deadline -> Project Beta -> Team Lead -> Alex`.
- **Contextual Awareness:** It understands the *relationships* between facts, providing deeper, more intelligent answers.

### 🕸️ 3. Interactive 3D Visualization
See your AI's brain grow in real-time.
- **Live Force Graph:** A beautiful, interactive 3D view of all your memories.
- **Explorable:** Zoom, pan, and hover over nodes to see how facts are connected.
- **Visual Debugging:** Instantly see if the AI has formed the right connections.

### ⚡ 4. Synaptic Pruning & Consolidation
Just like a human brain, Dolphin sleeps.
- **Efficiency:** Background processes (using local Llama 3) analyze the graph to merge duplicate nodes and remove irrelevant noise.
- **Long-Term Stability:** Keeps the graph clean and efficient as it scales to thousands of memories.

### 🤖 5. Local & Cloud Flexibility
- **Hybrid AI:** Use **Google Gemini** (Cloud) for complex reasoning and **Ollama (Llama 3)** (Local) for privacy-focused tasks or embeddings.
- **Cost Effective:** Offload heavy lifting to your local GPU.

---

## 🛠️ Tech Stack

- **Frontend:** Vanilla JS (ES Modules), Three.js, 3d-force-graph
- **Backend:** FastAPI (Python), Uvicorn
- **Database:** Supabase (PostgreSQL + pgvector)
- **AI Orchestration:** LangChain
- **LLMs:** Gemini 1.5 Flash, GPT-4, Llama 3 (via Groq), Ollama (Local)

---

## 🏁 Getting Started

Follow these steps to set up Dolphin locally.

### 1. Prerequisites

- **Python 3.10+** installed.
- **Node.js** (optional, for package management if needed).
- A **Supabase** account.

### 2. Ollama Setup (Local AI)

Dolphin uses local models for embeddings and high-performance tasks.

1.  **Download Ollama:** Go to [ollama.com](https://ollama.com/) and download the installer for your OS.
2.  **Install & Run:** Run the installer. Ensure the Ollama app is running in the background (you should see an icon in your system tray).
3.  **Pull the Model:** Open your terminal/command prompt and run:
    ```bash
    ollama pull llama3.2
    ```
    *This downloads the Llama 3.2 model, which Dolphin uses for local inference.*

### 3. Supabase Setup

1.  **Create a Project:** Log in to [Supabase](https://supabase.com/) and create a new project.
2.  **Get Credentials:** Go to **Project Settings -> API**. Copy the `Project URL` and `anon public key`.
3.  **Run Migrations (Database Setup):**
    -   Go to the **SQL Editor** in your Supabase dashboard.
    -   Open the file `supabase/migrations/20260214062656_remote_schema.sql` from this repository.
    -   Copy the *entire* content of that file.
    -   Paste it into the Supabase SQL Editor and click **RUN**.
    *This will create all the necessary tables (`conversation_logs`, `graph_nodes`, `graph_edges`, `user_memories`) and enable the `vector` extension.*

### 4. Environment Variables

1.  Copy `.env.example` to `.env`:
    ```bash
    cp .env.example .env
    ```
    *(Or manually rename the file)*.
2.  Open `.env` and fill in your keys:
    ```ini
    SUPABASE_URL=your_supabase_url
    SUPABASE_KEY=your_supabase_anon_key
    GOOGLE_API_KEY=your_gemini_api_key
    # Add other keys if using OpenAI/Groq
    ```

### 5. Run the Application

1.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
2.  **Start the Server:**
    ```bash
    uvicorn server:app --reload
    ```
3.  **Access the UI:** Open [http://localhost:8000](http://localhost:8000) in your browser.

---

## 🧪 Usage

1.  **Chat:** Start talking! Tell Dolphin about yourself.
2.  **Visualize:** Click the "Graph" icon to see your memory grow.
3.  **Settings:** Click the "Settings" icon to switch between Cloud (Gemini) and Local (Ollama) models.

---

## 🗺️ Roadmap

- **Beta 1.0 (Current Version):** 
    - Full local setup (Supabase + Ollama + Python).
    - Experience the Neural Memory Graph firsthand.
    - Ideal for developers and testers.

- **Alpha 1.0 (Upcoming):** 
    - **Dolphin SDK & CLI:** `pip install dolphin-memory`.
    - Easily integrate the memory layer into *your* existing Python products.
    - Automated setup tools.<br>
  <b>PS: Work on Alpha 1.0 has started !!! Stay tuned for the package release. </b>

- **Alpha 2.0 (Future):** 
    - **Dolphin Cloud:** A fully managed SaaS platform.
    - We handle the database, graph infrastructure, and scaling.
    - Simple API for developers (like OpenAI/Supabase).

---

Made with ❤️ by DewashishCodes
