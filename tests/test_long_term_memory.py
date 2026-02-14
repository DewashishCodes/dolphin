from database.memory_engine import memory_engine, chat_engine
from database.connection import db
import time

def test_long_term_memory():
    # 1. SETUP: Use a fresh session
    session_id = "test_memory_v3"
    print(f"Testing Session: {session_id}")

    # 2. INJECT A CORE FACT (Long-term memory)
    fact = "My favorite color is Electric Blue."
    print(f"Injecting Fact: {fact}")
    memory_engine.extract_and_store(session_id, fact)
    
    # 3. FILL WORKING MEMORY (Distractors)
    print("Flooding working memory with 15 distractor messages...")
    for i in range(15):
        # We manually add these to logs so they push the fact out of "Recent 10"
        db.add_message(session_id, "user", f"Just talking about random topic {i}")
        db.add_message(session_id, "assistant", f"Interesting topic {i}")

    # 4. TEST RETRIEVAL
    query = "What is my favorite color?"
    print(f"\nAsking: {query}")
    
    # This should trigger the new hybrid retrieval
    response, context_info = chat_engine.generate_response(session_id, query)
    
    print("\n--- AI RESPONSE ---")
    print(response)
    print(f"\n--- DEBUG INFO ---")
    print(context_info)

    # 5. VERIFICATION
    if "Electric Blue" in response or "Blue" in response:
        print("\n✅ SUCCESS: Long-term memory retrieved correctly!")
    else:
        print("\n❌ FAILURE: Failed to recall the fact.")

if __name__ == "__main__":
    test_long_term_memory()
