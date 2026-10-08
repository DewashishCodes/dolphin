---
name: status
description: Show whether Dolphin memory is working and how much it holds for this project. Use when the user asks about Dolphin's status or why memories are not appearing.
---

Report the state of Dolphin memory for this project.

1. Run `dolphin daemon status` to see whether the background daemon that powers automatic recall is running. If it is not, run `dolphin daemon start`.
2. Call the dolphin `graph_stats` tool for the size of this project's knowledge graph.
3. Call the dolphin `search` tool with a broad query about this project and `limit: 5` to show a sample of what is stored.
4. If the graph has no entities although memories exist, the extraction model is not available: suggest `dolphin doctor`.
5. Summarize in a few lines: daemon state, graph size, sample memories, and any problem found.
