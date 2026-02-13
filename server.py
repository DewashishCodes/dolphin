import uvicorn
from fastapi import FastAPI, HTTPException, Request
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
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GLOBAL_GRAPH_ID = "primary_user_brain"

app = FastAPI(title="Dolphin AI", description="Neural Memory Graph AI", version="2.0")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Pydantic Models ---
class ChatRequest(BaseModel):
    message: str
    session_id: str = "default_session"
    fast_fill: bool = False

class ChatResponse(BaseModel):
    response: str
    memories: Optional[List[str]] = None
    graph_updates: Optional[List[Dict[str, Any]]] = None

class PruneRequest(BaseModel):
    session_id: str
    limit: int = 10

# --- API Endpoints ---

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    try:
        session_id = request.session_id
        prompt = request.message
        fast_fill = request.fast_fill

        logger.info(f"Received chat request for session {session_id}: {prompt}")

        # 1. Log user message (Chat History is Session-Specific)
        db.add_message(session_id, "user", prompt)

        if fast_fill:
             # FAST PATH: Skip LLM, just acknowledge
            response_text = "✅ **Memory Stored.** (LLM Skipped)"
            memories = ["Fast Fill Mode Active"]
            # Graph Updates are GLOBAL
            new_triples = graph_engine.extract_and_sync_graph(GLOBAL_GRAPH_ID, prompt)
        else:
            # 2. Generate Response (Hybrid Reasoning)
            # Pass GLOBAL_GRAPH_ID so the AI remembers facts across sessions
            response_text, memories = chat_engine.generate_response(GLOBAL_GRAPH_ID, prompt)

            # 3. Background Graph Extraction (GLOBAL)
            new_triples = graph_engine.extract_and_sync_graph(GLOBAL_GRAPH_ID, prompt)
        
        # Log assistant response (Chat History is Session-Specific)
        db.add_message(session_id, "assistant", response_text)

        return ChatResponse(
            response=response_text,
            memories=memories if memories else [],
            graph_updates=new_triples if new_triples else []
        )

    except Exception as e:
        logger.error(f"Error in chat_endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/graph")
async def get_graph(session_id: str = "default_session"):
    try:
        # Visualize the GLOBAL Knowledge Graph
        nodes_data, edges_data = graph_engine.get_visual_graph(GLOBAL_GRAPH_ID)
        
        # Format for frontend (3d-force-graph usually takes {nodes: [], links: []})
        # Our backend returns 'edges', frontend library might expect 'links'
        
        # Map edges to expected format if necessary, or strictly pass through
        formatted_edges = []
        for e in edges_data:
            formatted_edges.append({
                "source": e['source_id'],
                "target": e['target_id'],
                "label": e['relationship'],
                "color": "#333333" # Default color
            })
            
        return {
            "nodes": nodes_data,
            "links": formatted_edges
        }
    except Exception as e:
        logger.error(f"Error in get_graph: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/history")
async def clear_history(session_id: str = "default_session"):
    # Implement logic to clear session history if needed
    # For now, just a placeholder or basic db call if available
    return {"status": "cleared", "message": "History cleared (Logic to be implemented in DB layer if needed)"}

@app.get("/api/stats")
async def get_stats(session_id: str = "default_session"):
    try:
        # Return total stats for the entire database (ignore session)
        n_count, e_count = graph_engine.get_stats(None)
        return {"nodes": n_count, "edges": e_count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/prune")
async def prune_graph(request: PruneRequest):
    try:
        # Prune the GLOBAL Knowledge Graph
        result = graph_engine.sleep_cycle_pruning(GLOBAL_GRAPH_ID, request.limit)
        return {"message": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Static Files ---
# Mount static files to serve the frontend
# Ensure 'static' directory exists
if not os.path.exists("static"):
    os.makedirs("static")

app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
