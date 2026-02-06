import streamlit as st
import asyncio
from database.memory_engine import chat_engine, memory_engine
from database.connection import db

st.set_page_config(page_title="Dolphin Long-Term Memory AI", layout="wide")

st.title("🐬 Dolphin: Long-Form Memory AI")
st.caption("Retaining information across 1,000+ turns in real-time.")

if "messages" not in st.session_state:
    st.session_state.messages = []
if "session_id" not in st.session_state:
    st.session_state.session_id = "hackathon_user_unique"

# Sidebar to show "What the AI is thinking"
with st.sidebar:
    st.header("🧠 Active Memory Vault")
    st.info("This is the structured data the AI retrieved from the database to answer your current prompt.")
    memory_container = st.empty()

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# User Input
if prompt := st.chat_input("Ask me anything..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 1. Generate Response + Retrieve Memory
    with st.chat_message("assistant"):
        with st.spinner("Searching memory..."):
            response, memories = asyncio.run(chat_engine.generate_response(st.session_state.session_id, prompt))
            st.markdown(response)
            
            # Update the sidebar with used memories
            if memories:
                memory_container.json(memories)
            else:
                memory_container.write("No specific historical facts needed for this turn.")

    # 2. Add to session state
    st.session_state.messages.append({"role": "assistant", "content": response})

    # 3. BACKGROUND: Save logs and Extract New Memories
    # In a real app, this would be a background task (celery/fastapi background)
    asyncio.run(db.add_message(st.session_state.session_id, "user", prompt))
    asyncio.run(memory_engine.extract_and_store(st.session_state.session_id, prompt))