import asyncio
from database.connection import db

async def test_flow():
    session_id = "test_user_001"
    
    print("1. Saving User message...")
    await db.add_message(session_id, "user", "Hello, my favorite color is Blue.")
    
    print("2. Saving AI response...")
    await db.add_message(session_id, "ai", "Noted, I will remember that.")
    
    print("3. Fetching history...")
    history = await db.get_recent_history(session_id)
    print("Retrieved History:", history)
    
    print("\nPhase 1 Setup Complete! Database is connected.")

if __name__ == "__main__":
    asyncio.run(test_flow())