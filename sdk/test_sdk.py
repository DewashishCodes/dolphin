import os
import time
from dotenv import load_dotenv
from dolphin_memory import DolphinMemory

# Load credentials from .env
load_dotenv()

def test_dolphin_sdk():
    print("🐬 Starting Dolphin SDK Test...")
    
    # 1. Initialize
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    
    if not url or not key:
        print("❌ Error: SUPABASE_URL or SUPABASE_KEY not found in .env")
        return

    print(f"🔗 Connecting to Supabase: {url[:25]}...")
    memory = DolphinMemory(
        supabase_url=url,
        supabase_key=key,
        ollama_model="llama3.2" # Ensure this is pulled
    )

    user_id = "test_user_777"
    
    # 2. Add a memory
    print(f"\n📝 Adding memory for user '{user_id}'...")
    fact = "I am a high-performance AI agent. I love building scalable systems and live in the cloud."
    result = memory.add(fact, user_id=user_id)
    print(f"✅ Memory added! ID: {result.get('memory_id')}")
    print(f"🕸️ Extracted Triples: {result.get('triples')}")

    # Give a tiny bit of time for background processing simulation (though SDK is synchronous currently in add)
    time.sleep(1)

    # 3. Search
    print(f"\n🔍 Searching for 'What do I do?'...")
    search_results = memory.search("What do I do?", user_id=user_id)
    if search_results:
        print(f"✅ Found {len(search_results)} results:")
        for r in search_results:
            print(f"  - [{r.get('similarity'):.2f}] {r.get('content', {}).get('value')}")
    else:
        print("❓ No search results found.")

    # 4. Get Context
    print(f"\n🧠 Generating LLM Context for 'Tell me about the user'...")
    context = memory.get_context("Tell me about the user", user_id=user_id)
    print("-" * 30)
    print(context)
    print("-" * 30)

    # 5. Get Stats
    print("\n📊 User Stats:")
    stats = memory.get_stats(user_id=user_id)
    print(f"   Nodes: {stats['nodes']}")
    print(f"   Edges: {stats['edges']}")

    print("\n🎉 Test Complete!")

if __name__ == "__main__":
    test_dolphin_sdk()
