"""
🐬 Dolphin Memory — Give your AI a brain.

Persistent graph-enhanced memory for LLMs. One class, three methods, works in 5 minutes.

Usage:
    from dolphin_memory import DolphinMemory

    # Local SQLite file, no setup. Pass supabase_url/supabase_key for the cloud.
    memory = DolphinMemory()

    # Store a memory
    memory.add("I love Python and live in Mumbai", user_id="user_123")

    # Search memories
    results = memory.search("programming languages", user_id="user_123")

    # Get full context for LLM injection
    context = memory.get_context("Tell me about the user", user_id="user_123")
"""

__version__ = "0.2.0"
__all__ = ["DolphinMemory", "DolphinConfig"]


def __getattr__(name):
    # Imported on first use, so `dolphin hook` (run on every prompt) starts fast
    if name == "DolphinMemory":
        from dolphin_memory.client import DolphinMemory
        return DolphinMemory
    if name == "DolphinConfig":
        from dolphin_memory.config import DolphinConfig
        return DolphinConfig
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
