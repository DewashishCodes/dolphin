"""
🐬 Dolphin Memory — Give your AI a brain.

Persistent graph-enhanced memory for LLMs. One class, three methods, works in 5 minutes.

Usage:
    from dolphin_memory import DolphinMemory

    memory = DolphinMemory(
        supabase_url="https://your-project.supabase.co",
        supabase_key="your-anon-key",
    )

    # Store a memory
    memory.add("I love Python and live in Mumbai", user_id="user_123")

    # Search memories
    results = memory.search("programming languages", user_id="user_123")

    # Get full context for LLM injection
    context = memory.get_context("Tell me about the user", user_id="user_123")
"""

from dolphin_memory.client import DolphinMemory
from dolphin_memory.config import DolphinConfig

__version__ = "0.1.0"
__all__ = ["DolphinMemory", "DolphinConfig"]
