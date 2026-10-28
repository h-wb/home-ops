# Models, tools and memory

Model access is declared in LiteLLM virtual keys. Tool access is declared in
ToolHive gateways and each client's MCP configuration. Keep these independent:
adding a model does not need a new gateway, and adding a tool does not need a new
model proxy. Paseo remains a single shared execution environment.

| Path | Model grants | Tool gateway | Memory |
| --- | --- | --- | --- |
| Private | Local inference and direct Mistral | `mcp-gateway` (full catalog) | Personal `memini` |
| General | Explicit other-provider models | `mcp-ops` (explicit workload allowlist) | Separate `memini-code` for coding agents |

“Private” describes permission to process personal data, not where inference
runs: Mistral receives that data in its cloud. Embeddings remain local.

## Open WebUI

Two native connections use the same LiteLLM URL and different credentials:

- Connection 0, tagged **Private**: `litellm/app/virtualkeys/open-webui.yaml`.
  Its existing Secret name is retained for RAG and local background tasks.
- Connection 1, tagged **General**: `litellm/app/virtualkeys/open-webui-general.yaml`.

Both keys have explicit `models` lists. Unclassified new models are unavailable
in Open WebUI until granted to a connection. Raw model IDs are preserved so
existing Workspace presets and chats continue to resolve. The connection tags
are navigation labels, not automatic tool permissions or conversation isolation.
The `homelab` preset selects full ToolHive; `ops` selects the ops gateway.

The small LiteLLM callback is retained as a history backstop. It inspects actual
backends and tool calls, including ToolHive's nested `call_tool` arguments. If a
private-tool conversation is switched to a general model, it refuses the request.
Every backend behind an alias must qualify as trusted. Native model grants alone
do not inspect conversation history. The callback does not inspect arbitrary
personal text, attachments or pasted tool results.

## Paseo

Vibe uses the full gateway. Claude Code and Codex use the ops gateway and the
separate coding memory instance. Their subscription requests bypass LiteLLM.
Provider MCP configuration is managed by the dotfiles bootstrap; gateway catalogs
live under `toolhive/config/`.

This is intentional configuration separation, not enforced isolation: agents
share the pod's network, home and credentials, and can reach in-cluster services.
Separate pods, homes and credentials are required if that assumption changes.

## Changing the policy

- **Add a model:** declare a `LiteLLMModel`, then explicitly grant its alias to
  the relevant virtual keys. Keep private aliases free of general-provider
  fallbacks. A new trusted cloud provider also needs endpoint classification in
  `litellm/app/patches/homeops_cloud_tool_guard.py`; an alias or UI tag alone
  cannot establish trust.
- **Add an ops tool:** add its workload to the deny-by-default catalog in
  `toolhive/config/ops-gateway.yaml` and its actual tool prefix to the guard's
  `CLOUD_TOOL_PREFIXES`. This is a deliberate grant to all general providers.
- **Add a personal tool:** add it to the full catalog only. It stays absent from
  the ops gateway and is rejected by the guard on general models by default.
- **Add a client:** give it only the model grants and gateway configuration it
  needs. Avoid catch-all keys for interactive chat.

The existing Kritika `allow_cloud_tools` exception is limited to its separately
scoped public-repository review key; Open WebUI keys have no such exception.
