---
name: system-docs
description: Find and read the documentation of this assistant and the homelab (design, what is deployed, flows, wiring, where things live). Use when asked how the assistant, the workshops, the tools or the homelab are set up, why something is built the way it is, or where a skill, a routine or a document lives.
---

# System documentation

The documentation lives in git. Read the page you need before you answer; do
not answer from memory.

Call `mcp__tools__github_get_file_contents` by its exact name with
`tool_call`, with `owner: "h-wb"`, `repo` and `path` from this table. A path
that ends in `/` is a folder: the call lists it.

| Question                                              | Repo     | Path                                            |
| ----------------------------------------------------- | -------- | ----------------------------------------------- |
| What is deployed; where skills, docs and notes live   | home-ops | kubernetes/apps/main/llm/README.md              |
| Why it is built this way: the rule, roles, decisions  | home-ops | kubernetes/apps/main/llm/DESIGN.md              |
| What is left to do                                    | home-ops | kubernetes/apps/main/llm/DESIGN.md              |
| How work moves, step by step                          | home-ops | kubernetes/apps/main/llm/docs/flows.md          |
| How each agent is connected, and its tools and memory | home-ops | kubernetes/apps/main/llm/docs/wiring.md         |
| The two workshops                                     | home-ops | kubernetes/apps/main/llm/paseo/README.md        |
| Your own routines and when they run                   | home-ops | kubernetes/apps/main/llm/hermes/app/routines/   |
| Your own settings                                     | home-ops | kubernetes/apps/main/llm/hermes/app/config.yaml |
| The homelab as a whole: clusters, conventions         | home-ops | AGENTS.md                                       |
| The skills every agent shares                         | dotfiles | conf.d/ai/README.md                             |

## Answer

- Say which page the answer comes from.
- If the page and what you observe differ, say so; the page may be behind.
- These pages are general data. You may quote them in a prompt for the
  general workshop.
- You cannot change them. A change is coding work: hand it to a workshop.
