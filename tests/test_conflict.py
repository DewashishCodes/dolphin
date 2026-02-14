import asyncio
from database.memory_engine import memory_engine
from database.connection import db

async def test_conflict_resolution():
    session_id = "conflict_test_user"
    
    # 1. Establish initial fact
    print("1️⃣ User says: 'I only eat Vegan food.'")
    await memory_engine.extract_and_store(session_id, "I only eat Vegan food.")
    
    # Check DB
    print("   (Fact stored. Checking DB...)")
    mems = await db.fetch_memories_by_key(session_id, "diet_preference")
    print(f"   Current Memory: {mems[0]['content'] if mems else 'None'}\n")
    
    # 2. Establish conflicting fact
    print("2️⃣ User says: 'Actually, I started eating Chicken recently.'")
    await memory_engine.extract_and_store(session_id, "Actually, I started eating Chicken recently.")
    
    # 3. Verify
    print("\n3️⃣ Verifying Conflict Resolution...")
    
    # Fetch all memories (active and archived) to see what happened
    all_mems = db.supabase.table("user_memories").select("*").eq("session_id", session_id).execute().data
    
    for m in all_mems:
        status_icon = "✅" if m['status'] == 'active' else "🗑️"
        print(f"{status_icon} Status: {m['status']} | Content: {m['content']}")

if __name__ == "__main__":
    asyncio.run(test_conflict_resolution())