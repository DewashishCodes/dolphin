import asyncio
from database.memory_engine import chat_engine

async def test_retrieval():
    session_id = "test_user_001"
    
    # We aren't telling the bot our language or call preference here.
    # It has to find it in the DB from Phase 2.
    user_query = "Can you schedule a call for me tomorrow in my preferred language?"
    
    print(f"User: {user_query}")
    print("🔍 Searching memory and generating response...")
    
    response, memories_used = await chat_engine.generate_response(session_id, user_query)
    
    print("\n--- AI RESPONSE ---")
    print(response)
    print("\n--- MEMORIES RETRIEVED ---")
    for m in memories_used:
        print(f"Found: {m['content']}")

if __name__ == "__main__":
    asyncio.run(test_retrieval())