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
    - **Dolphin SDK & CLI:** `pip install dolphin-core`.
    - Easily integrate the memory layer into *your* existing Python products.
    - Automated setup tools.

- **Alpha 2.0 (Future):** 
    - **Dolphin Cloud:** A fully managed SaaS platform.
    - We handle the database, graph infrastructure, and scaling.
    - Simple API for developers (like OpenAI/Supabase).

---

Made with ❤️ by Dewashish
