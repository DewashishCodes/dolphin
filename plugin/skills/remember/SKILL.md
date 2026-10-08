---
name: remember
description: Save a fact, decision, convention or preference to Dolphin memory so future sessions know it. Use when the user says to remember something or asks that a decision be kept for later.
argument-hint: "[what to remember]"
---

Store `$ARGUMENTS` in Dolphin memory.

1. Rewrite it as one or more self-contained sentences that name what they are about and will still make sense months from now without this conversation. Include the reason for a decision when it is known.
2. Call the dolphin `remember` tool once per sentence. Use `scope: "user"` for the user's own preferences that apply to every project; omit `scope` for anything about this project.
3. Never store secrets, credentials or tokens. If the text contains one, leave it out and tell the user.
4. Confirm in one line what was stored.
