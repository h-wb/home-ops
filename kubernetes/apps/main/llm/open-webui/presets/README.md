# Open WebUI presets

See [the stack access policy](../../README.md) for the private/general connection
keys, model grants and shared Paseo boundary.

System prompts for Open WebUI's custom models (Workspace → Models). The models
themselves live in Open WebUI's database; these files are the source of their
prompt text, so edits here are pasted (or pushed through the API) into the preset.

| File         | Preset id | Base model           | Tools                                                                                                    |
| ------------ | --------- | -------------------- | -------------------------------------------------------------------------------------------------------- |
| `homelab.md` | `homelab` | `qwen3.5-9b-chat`    | `server:mcp:toolhive` (Metabase, Dawarich, memini, kubectl, flux, GitHub, n8n, Anki), built-in tools off |
| `ops.md`     | `ops`     | `chatgpt/gpt-6-luna` | `server:mcp:toolhive-ops` (kubectl, flux, GitHub, n8n, Anki), built-in tools off                         |

Why a preset at all: an 8–9B model asked "what was my latest workout?" with only
the ToolHive gateway wandered through `find_tool` results until its 32k context
ran out. With this data map it answers in one or two calls. It fixes navigation,
not reasoning: questions that need judgement still want a bigger model.

`homelab` runs on the reasoning-off alias because, after tool calls, qwen3.5-9b
with reasoning on leaves its answer inside `reasoning_content` and the visible
reply comes back empty.

The memory section tells the model to pass `tier: "semantic"` on every
`memini_memory_remember`: memini puts a write without a tier in `working`, which
expires after 72 hours. Without that line a stated preference was stored and then
silently gone three days later.

The full ToolHive gateway can also be used with `mistral/mistral-small-latest`,
`mistral/mistral-medium-latest` or `mistral/mistral-large-latest`. Mistral is an
explicitly trusted cloud provider for personal data. Local embeddings remain unchanged.

`ops` is the restricted-provider preset. It only gets the `mcp-ops` gateway, and LiteLLM's cloud
tool guard refuses anything else on an untrusted model, so enabling the full ToolHive
server on it (or continuing a Homelab chat on it) fails with a 400 instead of
sending personal data out.

The Paseo agents currently share a pod, home directory and credentials. Vibe's
full-gateway configuration and Claude/Codex's ops configuration are a soft
boundary: they do not enforce isolation against direct network access. The
LiteLLM guard applies only to requests routed through LiteLLM. Pasted text,
attachments and shared credentials remain outside that guard.
