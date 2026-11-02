# Models, tools and memory

Use **general** and **private** as data scopes. General includes operational
secrets and code; private includes personal notes, location, health and memory.
Direct Mistral and approved local inference may process both scopes. Claude and
Codex are general only. Mistral running in general still gets general credentials.

The shared eligibility policy is `kubernetes/components/agent-data-policy/policy.json`.
Paseo and LiteLLM mount it; dotfiles consumes it without another provider list.
Tool catalogs remain ToolHive's responsibility; model aliases and explicit client
grants remain LiteLLM's responsibility. Every deployment behind a private alias
must qualify. New backends require explicit classification.

| Scope   | Tool endpoint | Memory endpoint  | Paseo client keys                            |
| ------- | ------------- | ---------------- | -------------------------------------------- |
| General | `mcp-general` | `memini-general` | `mcp-paseo-general`, `litellm-paseo-general` |
| Private | `mcp-private` | `memini-private` | `mcp-paseo-private`, `litellm-paseo-private` |

Gateway keys identify consumers, not the models they currently use. Direct
Claude/Codex subscription calls bypass LiteLLM.

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
outside its scope. The independently scoped public-repository review key retains
an explicit `allow_tool_policy_override`; interactive Paseo keys never get it.

See [Paseo environments](../agents/README.md) for the separate homes and rollout.
General retains cluster administration as an accepted exception, and backend
services have in-cluster paths outside gateway authentication. This separates
normal workflows rather than enforcing isolation against a cluster administrator.

## Open WebUI retirement

Verify the current PostgreSQL and uploaded-file backups before rollout.
Paseo is the interactive interface. Open WebUI's HelmRelease, app route, stateless
Dragonfly instance and LiteLLM grants are removed. `open-webui/ks.yaml` remains a
**data retention** Kustomization: PostgreSQL, uploaded files, encryption key, OIDC
identity and backups remain managed. Do not remove it until intentionally retiring
the data. App manifests and presets are archived under `docs/archive/open-webui/`.
