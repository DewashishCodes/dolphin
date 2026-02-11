import streamlit as st
from database.memory_engine import chat_engine
from database.graph_engine import graph_engine
from database.connection import db

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Dolphin: Knowledge Graph AI", 
    page_icon="🐬", 
    layout="wide"
)

# Custom Professional Styling
st.markdown("""
    <style>
    .stChatMessage { border-radius: 10px; margin-bottom: 10px; }
    .st-emotion-cache-1c79332 { background-color: #f0f2f6; }
    /* FIX: Revert sidebar to dark, but kept graph white in Config below */
    [data-testid="stSidebar"] { background-color: #0e1117; color: white; }
    </style>
""", unsafe_allow_html=True)

# --- 2. SESSION STATE ---
if "messages" not in st.session_state:
    st.session_state.messages = []

if "session_id" not in st.session_state:
    # Using a specific session ID for testing Knowledge Graph persistence
    st.session_state.session_id = "graph_demo_v1"

# --- 3. SIDEBAR (Graph Visualization) ---
with st.sidebar:
    st.image("https://img.icons8.com/clouds/200/brain.png", width=100)
    st.header("🧠 Neural Memory")
    
    # 3D Interactive Graph
    from streamlit_agraph import agraph, Node, Edge, Config

    

    nodes_data, edges_data = graph_engine.get_visual_graph(st.session_state.session_id)
    
    if nodes_data:
        nodes = []
        edges = []
        
        # Define diverse colors for node types
        type_colors = {
            "User": "#FF4B4B",     # Red
            "Person": "#FFA500",   # Orange
            "Concept": "#00CC96",  # Green
            "Event": "#AB63FA",    # Purple
            "Location": "#19D3F3", # Cyan
            "Document": "#FFD700"  # Gold
        }

        for n in nodes_data:
            color = type_colors.get(n['label'], "#636EFA") # Default Blue
            
            # FIX: Detailed Node styling for high contrast
            nodes.append(Node(
                id=n['id'], 
                label=n['name'], 
                size=25, 
                color=color, 
                font={'color': 'black', 'face': 'arial', 'strokeWidth': 2, 'strokeColor': 'white'}
            ))
        
        for e in edges_data:
            # FIX: Black edges for visibility
            edges.append(Edge(
                source=e['source_id'], 
                target=e['target_id'], 
                label=e['relationship'], 
                color="#333333",
                font={'color': 'black', 'size': 12},
                smooth=True
            ))
            
        config = Config(width=5500, 
                        height=500, 
                        directed=True,
                        nodeHighlightBehavior=True, 
                        highlightColor="#F7A7A6",
                        collapsible=False,
                        physics=True,
                        backgroundColor="#F8F0E3") # White Background

        # FIX: Wrap in a white container to force background
        
        agraph(nodes=nodes, edges=edges, config=config)
        

        st.caption(f"Visualizing {len(nodes)} nodes & {len(edges)} connections")
    else:
        st.info("Brain is empty. Start chatting!")
        
    st.divider()
    
    # --- RESTORED CONTROLS ---
    st.markdown("### Active Connections")
    st.info("These are the logical relationships Dolphin retrieved from your personal graph.")
    # Placeholder for Graph context (Triples) - FIX: Added back
    graph_display = st.empty()

    st.divider()
    st.subheader("🌙 Synaptic Sleep Cycle")
    
    # 1. Show Current Stats
    n_count, e_count = graph_engine.get_stats(st.session_state.session_id)
    col1, col2 = st.columns(2)
    col1.metric("Nodes", n_count)
    col2.metric("Edges", e_count)

    # 2. Pruning Slider
    prune_limit = st.slider("Consolidation Depth", 5, 50, 10)
    st.write(f"<small>Reviewing {prune_limit} nodes for redundancy.</small>", unsafe_allow_html=True)

    # 3. Trigger Button
    if st.button("🚀 Trigger Sleep Cycle"):
        with st.spinner("Llama is pruning synapses..."):
            result = graph_engine.sleep_cycle_pruning(st.session_state.session_id, prune_limit)
            st.toast(result)
            st.rerun() # Refresh stats and UI
    
    if st.button("Clear UI History"):
        st.session_state.messages = []
        st.rerun()

    st.divider()
    # 4. Token Saver Mode
    fast_fill_mode = st.toggle("⚡ Fast Fill Mode (No LLM)", value=False, help="Inject memories without generating a response. Saves tokens.")

    # st.divider()
    # # 5. Active Knowledge Ingestion
    # st.subheader("📂 Brain Upload")
    # uploaded_file = st.file_uploader("Upload PDF/Text", type=["pdf", "txt", "md"])
    
    # if uploaded_file and st.button("📥 Ingest File"):
    #     from utils.file_processor import file_processor
        
    #     with st.status("Reading file...", expanded=True) as status:
    #         # 1. Extract Text
    #         st.write("Extracting text...")
    #         text = file_processor.extract_text(uploaded_file)
    #         print(f"DEBUG: Extracted text length: {len(text)}") # DEBUG
            
    #         chunks = file_processor.chunk_text(text)
    #         print(f"DEBUG: Generated {len(chunks)} chunks") # DEBUG
            
    #         # 2. Create Source Node
    #         file_name_clean = uploaded_file.name.replace(" ", "_")
    #         source_id = graph_engine._upsert_node(st.session_state.session_id, f"File: {uploaded_file.name}", "Document")
    #         print(f"DEBUG: Created Source Node ID: {source_id}") # DEBUG
            
    #         # 3. Process Chunks
    #         progress_bar = st.progress(0)
    #         total_chunks = len(chunks)
            
    #         for i, chunk in enumerate(chunks):
    #             status.update(label=f"Processing Chunk {i+1}/{total_chunks}...", state="running")
    #             print(f"DEBUG: Processing chunk {i+1}/{total_chunks} (Length: {len(chunk)})") # DEBUG
    #             res = graph_engine.extract_and_sync_graph(st.session_state.session_id, chunk, source_node_id=source_id)
    #             print(f"DEBUG: Chunk {i+1} Result: {res}") # DEBUG
    #             progress_bar.progress((i + 1) / total_chunks)
                
    #         status.update(label="Ingestion Complete!", state="complete", expanded=False)
    #         st.success(f"Successfully ingrained {uploaded_file.name} into your Knowledge Graph.")
    #         st.rerun()

# --- 4. CHAT INTERFACE ---

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# User Input Logic
if prompt := st.chat_input("Say something like 'I live in Pune' or 'I love working with Python'"):
    
    # A. Display User Message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # B. Process Hybrid Reasoning
    with st.chat_message("assistant"):
        with st.spinner("🐬 Dolphin is traversing the Knowledge Graph..."):
            try:
                # 1. Log raw message to database
                db.add_message(st.session_state.session_id, "user", prompt)
                
                if fast_fill_mode:
                    # FAST PATH: Skip LLM, just acknowledge
                    response = "✅ **Memory Stored.** (LLM Skipped)"
                    memories = None
                    st.markdown(response)
                else:
                    # NORMAL PATH: GENERATE RESPONSE (Hybrid Reasoning)
                    # This fetches both Semantic Logs AND Knowledge Graph Relationships
                    response, memories = chat_engine.generate_response(st.session_state.session_id, prompt)
                    
                    # 3. UI Update (Show response immediately)
                    st.markdown(response)
                
                # 4. Update Sidebar with Graph Connections
                # We show the 'memories' retrieved for this specific turn
                if memories:
                    graph_display.markdown(f"```text\n{memories}\n```")
                elif not fast_fill_mode:
                    graph_display.write("No direct graph links found for this query.")

                # 5. LOCAL EXTRACTION (The Background Worker)
                # This runs on your i5 CPU via Ollama (Llama 3.2 3B)
                # It extracts triples and saves them to graph_nodes/graph_edges
                with st.status("Updating Knowledge Graph...", expanded=False):
                    new_triples = graph_engine.extract_and_sync_graph(st.session_state.session_id, prompt)
                    if new_triples:
                        st.write(f"Added {len(new_triples)} new relationships to your brain.")
                    else:
                        st.write("No new permanent facts found in this turn.")

                # Save to session history
                st.session_state.messages.append({"role": "assistant", "content": response})
                
            except Exception as e:
                st.error(f"System Error: {str(e)}")
                st.info("Ensure Ollama is running and Llama 3.2 is pulled.")

# --- 5. FOOTER ---
st.caption("Dolphin Graph AI • Revolutionary Personal Knowledge Architecture")