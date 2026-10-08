"""Storage backends for Dolphin Memory."""

from dolphin_memory.backends.base import StorageBackend
from dolphin_memory.config import DolphinConfig


def create_backend(config: DolphinConfig) -> StorageBackend:
    """Build the storage backend selected by the config."""
    backend = config.resolved_backend()
    if backend == "supabase":
        from dolphin_memory.backends.supabase import SupabaseBackend
        return SupabaseBackend(config.supabase_url, config.supabase_key)

    from dolphin_memory.backends.sqlite import SQLiteBackend
    return SQLiteBackend(config.db_path)


__all__ = ["StorageBackend", "create_backend"]
