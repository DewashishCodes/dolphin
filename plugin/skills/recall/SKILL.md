---
name: recall
description: Look up what Dolphin memory knows about a topic from earlier sessions. Use when the user asks what was decided, how something was done before, or what is remembered about this project.
argument-hint: "[topic]"
---

Look up `$ARGUMENTS` in Dolphin memory.

1. Call the dolphin `recall` tool with the topic as the query. If no topic was given, ask what to look up.
2. If the answer could also be a personal preference rather than a project fact, call `recall` again with `scope: "user"`.
3. Report what memory holds, with how old each memory is. Memories can be outdated: where one conflicts with the current code, say so and trust the code.
4. If nothing relevant comes back, say that plainly instead of guessing.
