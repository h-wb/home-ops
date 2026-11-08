# Models, tools and memory

Use **general** and **private** as data scopes. General includes operational
secrets and code; private includes personal notes, location, health and memory.
Cloud models (Claude, ChatGPT) are general only; direct Mistral and local
inference serve both.

Scopes are enforced per client: each LiteLLM virtual key lists the models it may
use, each Memini has its own client keys, ToolHive has one gateway per scope, and
each Paseo scope is a separate pod. No private-scope key lists a cloud model.

| Scope   | Tool endpoint (in-cluster)         | Memory endpoint  | Paseo client key        |
| ------- | ---------------------------------- | ---------------- | ----------------------- |
| General | `mcp-general` (`vmcp-mcp-ops`)     | `memini-general` | `litellm-paseo-general` |
| Private | `mcp-private` (`vmcp-mcp-gateway`) | `memini-private` | `litellm-paseo-private` |

ToolHive's gateways take callers anonymously, so who reaches each one is the
boundary. In-cluster clients (Hermes, Paseo, Open WebUI) call the service with no
key, and `toolhive/config/networkpolicy.yaml` admits only that scope's pods.
Clients outside the cluster go through Envoy (`mcp-<scope>.${SECRET_DOMAIN}`),
which checks `x-api-key` against that gateway's own list.

Client keys are per holder (what you'd revoke if it leaked), shared by every
agent on it, and named `<SCOPE>_<HOLDER>` in Bitwarden:

| Item       | Fields                                                                                                                                               |
| ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| `toolhive` | `GENERAL_WORKSTATION`, `PRIVATE_WORKSTATION` (Envoy client `workstation`), `REDIS_PASSWORD` (the gateways' session store)                            |
| `memini`   | `GENERAL_ADMIN`, `GENERAL_WORKSTATION`, `GENERAL_PASEO`, `GENERAL_HERMES`, `PRIVATE_ADMIN`, `PRIVATE_HERMES`, `PRIVATE_WORKSTATION`, `PRIVATE_PASEO` |

The workstation keys reach the workstations through Proton Pass
(`Automation/toolhive`, `Automation/memini`, fields `general`/`private`). The
litellm key is consumed directly: its CR lives beside the pods, so the operator
writes the Secret into the agents namespace and the helmrelease binds it by name.

## Agent model gateway

Agents use the Service, `http://litellm.llm.svc.cluster.local:4000`, like every other in-cluster client.

| Client      | Route                    | Provider credentials                                                                                                                                        |
| ----------- | ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Claude Code | Root URL, `anthropic/*`  | Claude Code owns its subscription login; LiteLLM forwards it. `ANTHROPIC_CUSTOM_HEADERS` carries the LiteLLM key                                            |
| OpenCode    | `/v1`, explicit aliases  | LiteLLM owns the shared `chatgpt/*` login and local/Qwen; Mistral goes direct via the pod's `MISTRAL_API_KEY`, native provider with thinking off by default |
| Codex       | `/v1`, `gpt-*`/`codex-*` | Codex owns its subscription sign-in, LiteLLM forwards it; requests without one ride the shared `chatgpt/*` login                                            |
| Hermes      | In-cluster `/v1`         | Separate general/private keys, Mistral only                                                                                                                 |

Claude's URL and header are injected into general's containers. Keep
`ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN` and `apiKeyHelper` unset. The gateway
holds no Anthropic key, so a request without a subscription token fails rather
than billing. Confirm subscription use with `used_client_oauth_token=true` in
LiteLLM's logs; Claude dollar costs shown there are API-price equivalents, not a
bill. See [Claude subscriptions](https://docs.litellm.ai/docs/tutorials/claude_code_max_subscription).

OpenCode's ChatGPT models are the proxy-owned `chatgpt/*` aliases, sharing one
login and quota with karakeep, lingarr and kritika.

The ChatGPT subscription is also exposed as the wildcard deployments in
`litellm/app/models/subscriptions.yaml` (`gpt-*`, `codex-*`): a Codex client
supplies its own sign-in and LiteLLM forwards it, while a request without one
is served by the shared gateway login. Unlike the `chatgpt/*` aliases they
declare no guards (272k window, per-key fencing), so OpenCode's Sol/Terra
picks use the new aliases in `models/chatgpt.yaml` and the wildcards are left
to Codex-style clients keeping their own sign-in (`codex-*` carries Codex's
own slugs, such as `codex-auto-review`). Both surfaces need LiteLLM >= 1.109.0
(proxy pinned to the latest dev release) and share one subscription quota.
See [ChatGPT subscription](https://docs.litellm.ai/docs/tutorials/openai_codex_byok).

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
