import asyncio
from database.memory_engine import memory_engine

async def test_extraction():
    session_id = "test_user_001"
    
    # Simulating a user message with multiple facts
    user_input = "Hi, I'm Dewashish. I prefer being called after 11 AM and I use Kannada as my main language."
    
    print("Extracting memories from input...")
    memories = await memory_engine.extract_and_store(session_id, user_input)
    
    print(f"Extracted and stored {len(memories)} memories.")
    print("Check your Supabase 'user_memories' table now!")

if __name__ == "__main__":
    asyncio.run(test_extraction())