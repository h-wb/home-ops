---
name: vault-notes
description: Write in the user's Obsidian vault by its rules (save a capture from chat, set a property, archive a finished idea or project, write the weekly review note). Use whenever a vault note is created, changed or moved.
---

# Vault notes

The vault is the user's notes. Its rules are `AGENTS.md` at the vault root:
read it once per conversation with `mcp__tools__vault_ro_read_note`
(`path: "AGENTS.md"`) before the first write, and follow it.

Reads use `mcp__tools__vault_ro_*`. Writes use `mcp__tools__vault_inbox_*` and
reach only `Notes/`, `AI/` and `Archives/`. Every write asks the user first, so
say in one line what you are about to write. Times are Toronto time.

## A capture from chat

The user says "note: …", "remember …", or sends a thought that is not a task.
A maybe ("I might", "someday") is a note too; a decided to-do is a TickTick
task.

`mcp__tools__vault_inbox_create_note` with `path: "Notes/<YYYY-MM-DD HHmm>.md"`
(now), frontmatter `{area: null, categories: [], created: "<YYYY-MM-DDTHH:mm>"}`
and the user's words as the body, unchanged. It lands in the vault inbox and
the user files it. Add `people: ["[[Name]]"]` when it is about someone who has
a note (check with `mcp__tools__vault_ro_resolve_note`).

## A note you write yourself

`AI/<YYYY-MM-DD> <title>.md` with frontmatter `author: ["[[Hermes]]"]`,
`categories: ["[[Resources]]"]`, `created`, and `area` when you know it.
Plain sentences, the facts only.

## A property

`mcp__tools__vault_inbox_patch_frontmatter` on the note's path. Values that
point at notes are links in quotes, like `"[[Projects]]"`. `status` is a list
with one value. A project's `ticktick` is its parent task's link:
`https://ticktick.com/webapp/#p/<projectId>/tasks/<taskId>`.

## Archive

A project or idea whose `status` becomes `done` or `archived`: patch the
status, then `mcp__tools__vault_inbox_move_note` to `Archives/<same file name>`.

## Never

- Write in `Daily/`, `References/`, `Clippings/` or `Templates/` (the tools
  refuse it anyway).
- Change the body of a Journal or Writing note.
- Delete a note. Archive it.
