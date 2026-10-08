"""
Dolphin MCP Server
===================
Exposes Dolphin Memory to any MCP client (Claude Code, Claude Desktop, Cursor, ...)
over stdio.

Usage:
    dolphin mcp

Claude Code:
    claude mcp add dolphin -- dolphin mcp

Configuration comes from environment variables (see DolphinConfig.from_env).
With none set, memories live in a local SQLite file shared by every session on
this machine. Memories are scoped to the project the server is started in;
DOLPHIN_SCOPE overrides that.
"""

import logging
import os
import sys
import threading
from typing import Any, Dict, List, Optional

try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    # mcp 1.x, where the same class is called FastMCP
    from mcp.server.fastmcp import FastMCP as MCPServer

from dolphin_memory.client import DolphinMemory
from dolphin_memory.config import DolphinConfig
from dolphin_memory.scopes import resolve_scope

logger = logging.getLogger("dolphin.mcp")

LOG_LEVEL = os.environ.get("DOLPHIN_LOG_LEVEL", "WARNING").upper()

mcp = MCPServer(
    "dolphin",
    log_level=LOG_LEVEL,
    instructions=(
        "Dolphin is a persistent memory shared across sessions and agents. "
        "Call `recall` before starting work that may depend on earlier decisions, "
        "preferences or project facts. Call `remember` when you learn something a "
        "future session would need: a decision and its reason, a convention, a "
        "gotcha, a user preference. Do not store secrets or routine chatter."
    ),
)

_memory: Optional[DolphinMemory] = None
_memory_lock = threading.Lock()


def _get_memory() -> DolphinMemory:
    """Create the DolphinMemory client on first use (Thread-Safe)."""
    global _memory
    with _memory_lock:
        if _memory is None:
            _memory = DolphinMemory(config=DolphinConfig.for_agents())
        return _memory


def _scope(scope: Optional[str]) -> str:
    # The MCP server runs in the project directory, so the default is this project
    return resolve_scope(scope)


@mcp.tool()
def remember(text: str, scope: Optional[str] = None) -> Dict[str, Any]:
    """Store a fact, decision, preference or lesson in persistent memory.

    Write one self-contained statement that will still make sense without the
    current conversation. Entities and relationships are extracted into the
    knowledge graph in the background.

    Args:
        text: What to remember.
        scope: Omit for this project's memory. Use "user" for preferences that
            apply across all projects.
    """
    return _get_memory().add(text, scope=_scope(scope), metadata={"source": "mcp"})


@mcp.tool()
def recall(query: str, scope: Optional[str] = None) -> str:
    """Get everything memory knows that is relevant to a query.

    Combines semantically similar memories with related knowledge-graph facts.
    Use this before work that may depend on past decisions or preferences.

    Args:
        query: What you want to know about, in natural language.
        scope: Omit for this project's memory. Use "user" for preferences that
            apply across all projects.
    """
    return _get_memory().get_context(query, scope=_scope(scope))


@mcp.tool()
def search(query: str, limit: int = 5, scope: Optional[str] = None) -> List[Dict[str, Any]]:
    """Search stored memories by meaning and return them with ids and similarity scores.

    Use this instead of `recall` when you need memory ids (for `forget`) or raw
    matches without knowledge-graph context.

    Args:
        query: Natural language search query.
        limit: Maximum number of results.
        scope: Omit for this project's memory. Use "user" for preferences that
            apply across all projects.
    """
    return _get_memory().search(query, scope=_scope(scope), limit=limit)


@mcp.tool()
def forget(memory_id: int) -> str:
    """Permanently delete one memory by id. Get the id from `search` first.

    Args:
        memory_id: The id of the memory to delete.
    """
    if _get_memory().delete(memory_id):
        return f"Deleted memory {memory_id}."
    return f"No memory with id {memory_id}."


@mcp.tool()
def graph_stats(scope: Optional[str] = None) -> Dict[str, int]:
    """Count the entities (nodes) and relationships (edges) in the knowledge graph.

    Args:
        scope: Omit for this project's memory. Use "user" for preferences that
            apply across all projects.
    """
    return _get_memory().get_stats(scope=_scope(scope))


def _prewarm():
    """Load the embedding model ahead of the first tool call."""
    try:
        _get_memory().prewarm()
    except Exception as e:
        logger.warning(f"Pre-warm failed: {e}")


def run():
    """Run the MCP server over stdio. Called by `dolphin mcp`."""
    # stdout carries the MCP protocol, so all logging goes to stderr
    logging.basicConfig(
        level=LOG_LEVEL,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        stream=sys.stderr,
        force=True,
    )
    threading.Thread(target=_prewarm, daemon=True).start()
    mcp.run()


if __name__ == "__main__":
    run()
