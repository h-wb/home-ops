# Open WebUI presets

System prompts for Open WebUI's custom models (Workspace → Models). The models
themselves live in Open WebUI's database; these files are the source of their
prompt text, so edits here are pasted (or pushed through the API) into the preset.

| File | Preset id | Base model | Tools |
| --- | --- | --- | --- |
| `homelab.md` | `homelab` | `qwen3.5-9b-chat` | `server:mcp:toolhive`, built-in tools off |

Why a preset at all: an 8–9B model asked "what was my latest workout?" with only
the ToolHive gateway wandered through `find_tool` results until its 32k context
ran out. With this data map it answers in one or two calls. It fixes navigation,
not reasoning: questions that need judgement still want a bigger model.

`homelab` runs on the reasoning-off alias because, after tool calls, qwen3.5-9b
with reasoning on leaves its answer inside `reasoning_content` and the visible
reply comes back empty.
