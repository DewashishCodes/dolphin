import streamlit as st
from database.memory_engine import chat_engine, memory_engine
from database.connection import db

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Dolphin: Long-Form Memory AI", 
    page_icon="🐬", 
    layout="wide"
)

# Custom Styling for a professional look
st.markdown("""
    <style>
    .stChatMessage { border-radius: 10px; margin-bottom: 10px; }
    .st-emotion-cache-1c79332 { background-color: #f0f2f6; }
    </style>
""", unsafe_allow_html=True)

# --- 2. SESSION STATE MANAGEMENT ---
if "messages" not in st.session_state:
    st.session_state.messages = []

if "session_id" not in st.session_state:
    # This ID ensures that even if you refresh, the DB knows it's you
    st.session_state.session_id = "pune_stable_demo_user"

# --- 3. SIDEBAR: THE MEMORY VAULT ---
with st.sidebar:
    st.title("🧠 Memory Vault")
    st.info("Retrieved facts used for this turn:")
    
    # This placeholder updates every time the AI 'remembers' something
    memory_display = st.empty()
    
    st.divider()
    st.subheader("📊 System Specs")
    st.write("✅ **Recall Mode:** Timestamp-aware")
    st.write("✅ **Embeddings:** Local (768-dim)")
    st.write("✅ **Architecture:** Sync-Stable")
    
    if st.button("Clear Chat UI"):
        st.session_state.messages = []
        st.rerun()

# --- 4. CHAT INTERFACE ---

# Display previous messages from the session
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# User Input Logic
if prompt := st.chat_input("Ask me anything (e.g., 'What is my favorite food?')"):
    
    # A. Display User Message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # B. Process AI Response
    with st.chat_message("assistant"):
        with st.spinner("🐬 Dolphin is searching its memory..."):
            try:
                # 1. Log the user's message to the database
                db.add_message(st.session_state.session_id, "user", prompt)
                
                # 2. Generate Response (Includes Query Expansion & Memory Retrieval)
                # This is a synchronous call - no event loop errors!
                response, memories = chat_engine.generate_response(st.session_state.session_id, prompt)
                
                # 3. Save AI response to logs
                db.add_message(st.session_state.session_id, "ai", response)
                
                # 4. Extract and store any new facts from this turn
                memory_engine.extract_and_store(st.session_state.session_id, prompt)

                # --- UI UPDATES ---
                st.markdown(response)
                
                # Update the Sidebar with the retrieved JSON data
                if memories:
                    memory_display.json(memories)
                else:
                    memory_display.write("No specific historical facts needed for this turn.")

                # Save to session history
                st.session_state.messages.append({"role": "assistant", "content": response})
                
            except Exception as e:
                st.error(f"Critical System Error: {str(e)}")
                st.info("Check your database connection or API keys.")

# --- 5. FOOTER ---
st.caption("Dolphin AI • Built for Long-Form Memory Retention")