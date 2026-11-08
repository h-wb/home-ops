# Models, tools and memory

Use **general** and **private** as data scopes. General includes operational
secrets and code; private includes personal notes, location, health and memory.
Direct Mistral and approved local inference may process both scopes. Claude and
Codex are general only. Mistral running in general still gets general credentials.

The shared eligibility policy is `kubernetes/components/agent-data-policy/policy.json`.
LiteLLM mounts it; the Paseo app overlays ship matching per-scope config
fragments (kept in sync by tests), so no consumer keeps another provider list.
Tool catalogs remain ToolHive's responsibility; model aliases and explicit client
grants remain LiteLLM's responsibility. Every deployment behind a private alias
must qualify. New backends require explicit classification.

| Scope   | Tool endpoint | Memory endpoint  | Paseo client keys                            |
| ------- | ------------- | ---------------- | -------------------------------------------- |
| General | `mcp-general` | `memini-general` | `mcp-paseo-general`, `litellm-paseo-general` |
| Private | `mcp-private` | `memini-private` | `mcp-paseo-private`, `litellm-paseo-private` |

Gateway keys identify consumers, not the models they currently use. Claude Code,
Codex, Vibe, OpenCode and Hermes send model requests through LiteLLM. MCP and
memory connections remain separate, with their existing scope credentials.

## Agent model gateway

The common model gateway is `https://litellm.${SECRET_DOMAIN}`. General Paseo
uses `litellm-paseo-general`; private uses `litellm-paseo-private`. Subscription
routes are granted only to general. The internal hostname is included in both
pods' Envoy host aliases, since these routes have no public DNS record.

| Client      | Model route                                           | Provider credentials                                                                                         |
| ----------- | ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| Claude Code | Root URL, `/v1/messages`, `anthropic/*`               | Claude Code owns subscription login and refresh; `ANTHROPIC_CUSTOM_HEADERS` carries the separate LiteLLM key |
| Codex       | `/v1`, `gpt-*` and `codex-*`, Responses over HTTP/SSE | Codex owns ChatGPT login and refresh; `x-litellm-api-key` carries the separate LiteLLM key                   |
| Vibe        | `/v1`, explicit Mistral aliases                       | LiteLLM owns the upstream Mistral API credential                                                             |
| OpenCode    | Existing in-cluster `/v1` route                       | LiteLLM owns upstream credentials                                                                            |
| Hermes      | Existing in-cluster `/v1` route                       | Separate general/private keys, with Mistral model grants                                                     |

Codex's provider configuration is merged from `scopes/general/codex.toml`.
Claude's URL is injected into general's provisioning, app and SSH containers;
External Secrets constructs its gateway header without writing a key to Git or
agent config files. Keep `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, and
Claude's `apiKeyHelper` unset for subscription use. Codex's subscription provider
deliberately has `requires_openai_auth = true` and no `env_key`. Existing local
subscription logins remain in the agents' homes. No paid API fallback is configured.

Vibe's scope fragment supplies the gateway provider, models, allowed aliases and
background title/approval models through `VIBE_*` settings. Both scopes use the
same Mistral routes with their own LiteLLM key. OpenCode and Hermes already use
LiteLLM and retain their existing model/tool configuration. Existing `chatgpt/*`
aliases and the proxy's shared ChatGPT token PVC remain for background consumers.

Client-owned Codex forwarding requires the published, digest-pinned
`v1.110.0-dev.1` image. The current docs mention `v1.109.0`, but that release/image
was unpublished when checked on 2026-11-08; `v1.108.3` lacks this forwarding code.
Move to a stable release containing it when available. This is a development
release dependency, so verify both interactive and existing background calls.

Roll out LiteLLM and let its virtual-key reconciliation and Bitwarden publication
finish before rolling Paseo. Start new agent sessions, confirm one request from
each client in LiteLLM logs, and confirm `used_client_oauth_token=true` for Claude
and Codex subscription requests. Test a native shell/file tool and general MCP
memory, then confirm private MCP calls are rejected on subscription routes. Claude
subscription dollar costs are API-price equivalents; they are not a bill.

References: [Claude subscriptions](https://docs.litellm.ai/docs/tutorials/claude_code_max_subscription)
and [Codex subscriptions](https://docs.litellm.ai/docs/tutorials/openai_codex_byok).

## Preserved identities

Memini app directories use the new names. The releases, PVCs, backup identities
and generated credentials remain `memini-code` (general) and `memini` (private).
Scoped Service aliases point at these existing instances and their UI hostnames
are scoped. No memory database or client key is recreated for naming consistency.
Memini keys do not restrict readable namespaces: keep the stores separate and use
namespaces only to organize projects/agents within each. General Paseo initially
reuses the existing general `codex` credential for all its agents.

ToolHive retains its `mcp-ops` and `mcp-gateway` resource identities and legacy
hostnames as aliases. New clients use scoped names. Existing CreatedOnce key sets
are intentionally unchanged to prevent rotating every old client; a retired
Open WebUI key remains inert in the old general key set.

## Request and execution boundaries

`litellm/app/patches/homeops_data_scope_guard.py` checks tool definitions, nested
ToolHive calls, results and history against the shared policy. It refuses private
tool history on general-only backends. Pasted private text and attachments are
outside its scope. General Paseo's authenticated key grants the native coding
tools listed in `policy.json`, including Anthropic tool-use blocks and Codex
namespaces/custom tools. General Memini is permitted on this key; private MCP
definitions, nested calls and history are still refused. Shell/file tools rely
on the separate execution environments for their data boundary.
The independently scoped public-repository review key retains an explicit
`allow_tool_policy_override`; interactive Paseo keys never get that override.

See [Paseo environments](../agents/README.md) for the separate homes and rollout.
General reaches Kubernetes through ToolHive; its pod has no automatic service-account
token or direct RBAC grants. ToolHive permissions, GitOps writes and retained
bootstrap credentials remain operational access paths. Backend services also have
in-cluster paths outside gateway authentication. See the linked environment guide
for the API egress restrictions and the remaining credential boundaries.

## Open WebUI retirement

Verify the current PostgreSQL and uploaded-file backups before rollout.
Paseo is the interactive interface. Open WebUI's HelmRelease, app route, stateless
Dragonfly instance and LiteLLM grants are removed. `open-webui/ks.yaml` remains a
**data retention** Kustomization: PostgreSQL, uploaded files, encryption key, OIDC
identity and backups remain managed. Do not remove it until intentionally retiring
the data. The former app manifests and presets are deleted; Git history retains
their previous definitions.
