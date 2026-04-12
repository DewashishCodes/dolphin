"""
Dolphin V2 Server
==================
FastAPI server with async graph extraction via BackgroundTasks.

V2 Changes:
- Graph extraction runs as a background task (non-blocking)
- Structured logging throughout
- Better error responses
- Proper CORS configuration notes
"""

import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import os
import logging

# Import existing core modules
from database.memory_engine import chat_engine
from database.graph_engine import graph_engine
from database.connection import db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger("dolphin.server")

GLOBAL_GRAPH_ID = "primary_user_brain"

app = FastAPI(
    title="Dolphin AI",
    description="Neural Memory Graph AI — Persistent Knowledge for LLMs",
    version="2.0"
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Pydantic Models ---

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default_session"
    fast_fill: bool = False
    llm_config: Optional[Dict[str, str]] = None


class ChatResponse(BaseModel):
    response: str
    memories: Optional[List[str]] = None
    graph_updates: Optional[List[Dict[str, Any]]] = None


class PruneRequest(BaseModel):
    session_id: str
    limit: int = 10


# --- Background Task Functions ---

def background_graph_extraction(session_id: str, text: str):
    """Runs graph extraction in background so it doesn't block the response."""
    try:
        new_triples = graph_engine.extract_and_sync_graph(session_id, text)
        logger.info(f"Background extraction complete: {len(new_triples)} triples from session {session_id}")
    except Exception as e:
        logger.error(f"Background extraction failed: {e}", exc_info=True)


# --- API Endpoints ---

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest, background_tasks: BackgroundTasks):
    """
    Main chat endpoint. Generates a response using hybrid retrieval,
    then kicks off graph extraction as a background task.
    """
    try:
        session_id = request.session_id
        prompt = request.message
        fast_fill = request.fast_fill
        llm_config = request.llm_config

        logger.info(f"Chat request [session={session_id}]: {prompt[:80]}...")

        # 1. Log user message (Chat History is Session-Specific)
        db.add_message(session_id, "user", prompt)

        if fast_fill:
            # FAST PATH: Skip LLM response, just store the memory
            response_text = "✅ **Memory Stored.** (LLM Skipped)"
            memories = ["Fast Fill Mode Active"]
        else:
            # NORMAL PATH: Generate response with hybrid context
            # Pass GLOBAL_GRAPH_ID so the AI remembers facts across sessions
            response_text, memories = chat_engine.generate_response(
                GLOBAL_GRAPH_ID, prompt, llm_config
            )

        # 2. Background graph extraction (NON-BLOCKING)
        # This used to take 3-8 seconds and blocked the response. Now it runs async.
        background_tasks.add_task(background_graph_extraction, GLOBAL_GRAPH_ID, prompt)

        # 3. Log assistant response (Session-Specific)
        db.add_message(session_id, "assistant", response_text)

        return ChatResponse(
            response=response_text,
            memories=memories if memories else [],
            graph_updates=[]  # Graph updates happen in background now
        )

    except Exception as e:
        logger.error(f"Chat endpoint error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/graph")
async def get_graph(session_id: str = "default_session"):
    """Returns the full Knowledge Graph for 3D visualization."""
    try:
        # Visualize the ENTIRE Knowledge Graph (Global)
        nodes_data, edges_data = graph_engine.get_visual_graph(None)

        # Format edges for frontend (3d-force-graph expects 'links')
        formatted_edges = []
        for e in edges_data:
            formatted_edges.append({
                "source": e['source_id'],
                "target": e['target_id'],
                "label": e['relationship'],
                "color": "#333333"
            })

        return {
            "nodes": nodes_data,
            "links": formatted_edges
        }
    except Exception as e:
        logger.error(f"Graph endpoint error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/history")
async def clear_history(session_id: str = "default_session"):
    """Clears conversation history for a session."""
    try:
        # Delete conversation logs for this session
        db.supabase.table("conversation_logs") \
            .delete() \
            .eq("session_id", session_id) \
            .execute()
        return {"status": "cleared", "message": f"History cleared for session {session_id}"}
    except Exception as e:
        logger.error(f"Clear history error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stats")
async def get_stats(session_id: str = "default_session"):
    """Returns node/edge counts for the knowledge graph."""
    try:
        n_count, e_count = graph_engine.get_stats(None)
        return {"nodes": n_count, "edges": e_count}
    except Exception as e:
        logger.error(f"Stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/prune")
async def prune_graph(request: PruneRequest):
    """Triggers the Synaptic Sleep Cycle to consolidate graph nodes."""
    try:
        result = graph_engine.sleep_cycle_pruning(GLOBAL_GRAPH_ID, request.limit)
        return {"message": result}
    except Exception as e:
        logger.error(f"Prune error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- Health Check ---

@app.get("/api/health")
async def health_check():
    """Health check endpoint for monitoring."""
    try:
        n_count, e_count = graph_engine.get_stats(None)
        return {
            "status": "healthy",
            "version": "2.0",
            "graph": {"nodes": n_count, "edges": e_count}
        }
    except Exception as e:
        return {"status": "degraded", "error": str(e)}


# --- Static Files ---
if not os.path.exists("static"):
    os.makedirs("static")

app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
