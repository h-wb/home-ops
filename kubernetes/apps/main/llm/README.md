# Models, tools and memory

Use **general** and **private** as data scopes. General includes operational
secrets and code; private includes personal notes, location, health and memory.
Cloud models (Claude, ChatGPT) are general only; direct Mistral and local
inference serve both.

Scopes are enforced by per-client credentials: each LiteLLM virtual key lists the
models it may use, ToolHive and Memini keys are per scope, and each Paseo scope is
a separate pod. No private-scope key lists a cloud model.

| Scope   | Tool endpoint | Memory endpoint  | Paseo client keys                            |
| ------- | ------------- | ---------------- | -------------------------------------------- |
| General | `mcp-general` | `memini-general` | `mcp-paseo-general`, `litellm-paseo-general` |
| Private | `mcp-private` | `memini-private` | `mcp-paseo-private`, `litellm-paseo-private` |

## Agent model gateway

Agents use `https://litellm.${SECRET_DOMAIN}` (internal route; both Paseo pods
carry an Envoy host alias for it).

| Client      | Route                   | Provider credentials                                                                                             |
| ----------- | ----------------------- | ---------------------------------------------------------------------------------------------------------------- |
| Claude Code | Root URL, `anthropic/*` | Claude Code owns its subscription login; LiteLLM forwards it. `ANTHROPIC_CUSTOM_HEADERS` carries the LiteLLM key |
| OpenCode    | `/v1`, explicit aliases | LiteLLM owns upstream credentials (Mistral API key, the shared `chatgpt/*` login)                                |
| Hermes      | In-cluster `/v1`        | Separate general/private keys, Mistral only                                                                      |

Claude's URL and header are injected into general's containers. Keep
`ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN` and `apiKeyHelper` unset. The gateway
holds no Anthropic key, so a request without a subscription token fails rather
than billing. Confirm subscription use with `used_client_oauth_token=true` in
LiteLLM's logs; Claude dollar costs shown there are API-price equivalents, not a
bill. See [Claude subscriptions](https://docs.litellm.ai/docs/tutorials/claude_code_max_subscription).

OpenCode's ChatGPT models are the proxy-owned `chatgpt/*` aliases, sharing one
login and quota with karakeep, lingarr and kritika.

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

## Execution boundaries

See [Paseo environments](../agents/README.md). General reaches Kubernetes through
ToolHive; its pod has no service-account token or direct RBAC grants. ToolHive
permissions, GitOps writes and retained bootstrap credentials remain operational
access paths. Backend services also have in-cluster paths outside gateway
authentication.

## Open WebUI retirement

Verify the current PostgreSQL and uploaded-file backups before rollout.
Paseo is the interactive interface. Open WebUI's HelmRelease, app route, stateless
Dragonfly instance and LiteLLM grants are removed. `open-webui/ks.yaml` remains a
**data retention** Kustomization: PostgreSQL, uploaded files, encryption key, OIDC
identity and backups remain managed. Do not remove it until intentionally retiring
the data. The former app manifests and presets are deleted; Git history retains
their previous definitions.
