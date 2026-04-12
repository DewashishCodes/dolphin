import os
import time
from dotenv import load_dotenv
from dolphin_memory import DolphinMemory

import logging

# Configure logging to see background task progress
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# Load credentials from .env
load_dotenv()

def test_polished_sdk():
    print("🐬 Starting Polished Dolphin SDK Test...")
    
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    
    if not url or not key:
        print("❌ Error: SUPABASE_URL or SUPABASE_KEY not found in .env")
        return

    # Initialize
    memory = DolphinMemory(
        supabase_url=url,
        supabase_key=key,
        deduplicate=True,
        dedupe_threshold=0.92,
        enable_background_extraction=True
    )
    
    memory.prewarm()

    user_id = f"tester_{int(time.time())}"
    fact = "I am building a high-performance memory SDK for AI agents."
    
    # 1. Test Initial Add (Background Extraction)
    print(f"\n📝 [Test 1] Adding new memory (User: {user_id})...")
    start_time = time.time()
    res1 = memory.add(fact, user_id=user_id)
    duration = time.time() - start_time
    print(f"✅ Add returned in {duration:.4f}s (Should be fast!)")
    print(f"   Status: {res1.get('status')}")
    print(f"   Triples Pending: {res1.get('triples_pending')}")

    # 2. Test Deduplication
    print(f"\n📝 [Test 2] Adding the SAME memory again (Deduplication)...")
    res2 = memory.add(fact, user_id=user_id)
    print(f"   Status: {res2.get('status')} (Should be 'reinforced')")
    print(f"   Similarity: {res2.get('similarity', 0):.4f}")

    # 3. Test Slight Variation Deduplication
    print(f"\n📝 [Test 3] Adding slight variation (Deduplication)...")
    fact_variant = "I'm currently building a high-performance memory SDK for AI agents."
    res3 = memory.add(fact_variant, user_id=user_id)
    print(f"   Status: {res3.get('status')}")
    if res3.get('status') == 'reinforced':
        print(f"✅ Deduplication matched variation!")
    else:
        print(f"ℹ️ Variation was added as new memory (Threshold: 0.92)")

    # 4. Wait for background extraction
    print("\n⏳ Waiting 12s for background graph extraction to complete (model loading)...")
    time.sleep(12)

    # 5. Test Enriched Context
    print(f"\n🧠 [Test 4] Generating LLM Context...")
    context = memory.get_context("What am I building?", user_id=user_id)
    print("-" * 50)
    print(context)
    print("-" * 50)

    # 6. Verify Graph
    stats = memory.get_stats(user_id=user_id)
    print(f"\n📊 Stats: {stats['nodes']} nodes, {stats['edges']} edges")
    if stats['edges'] > 0:
        print("✅ Background extraction successful!")
    else:
        print("⚠️ No edges found. Check if Ollama is running.")

    print("\n🎉 Polished SDK Test Complete!")

if __name__ == "__main__":
    test_polished_sdk()
