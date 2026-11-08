# Paseo environments

Two Paseo pods, **general** and **private**, with separate homes, credentials and
agent config. `PASEO_DATA_SCOPE` names the scope; both use dotfiles' `paseo` mise
class for CLIs, repos and shell only.

```text
paseo/
├── ks.yaml          # general, private and scratch Flux Kustomizations
├── common/          # shared HelmRelease, ExternalSecrets, provision.sh, authorized_keys
├── general/
│   ├── config/      # paseo.json, claude.json, opencode.json for this scope
│   └── ...          # GitHub/memory credentials, NFS and the API egress policy
├── private/
│   ├── config/
│   └── ...          # explicit Hermes token mount and home-retention patch
└── scratch/         # retained namespace and quotas, no agent RBAC grants
```

Edit `ks.yaml` for names, scope, credential item, hostnames, SSH IP and backup
settings; `common/helmrelease.yaml` for shared pod settings; the overlay's
`helmrelease.yaml` for environment-specific values.

| Environment | Agents                          | Models (LiteLLM key)                         | Tools and data                                  |
| ----------- | ------------------------------- | -------------------------------------------- | ----------------------------------------------- |
| General     | Claude Code, OpenCode           | Claude subscription, ChatGPT, Mistral, local | `mcp-general`, `memini-general`, NFS, Tailscale |
| Private     | OpenCode, Hermes (`llm/hermes`) | Mistral, local                               | `mcp-private`, Obsidian; no NFS or Tailscale    |

## Agent config

Each overlay's `config/` is the only place agent config lives. It becomes the
`${APP}-config` ConfigMap, mounted read-only at `/etc/paseo/config`:

- `opencode.json`: read in place (`OPENCODE_CONFIG`).
- `paseo.json` and `claude.json`: deep-merged by `common/config/provision.sh` into
  `~/.paseo/config.json` and `~/.claude.json` on every pod start, since agents
  keep their own state in those files. Our keys win; everything else is kept.

The files hold no secrets. Credentials come from ExternalSecrets as environment
variables and are referenced by name: `{env:LITELLM_API_KEY}` for OpenCode,
`$${MCP_API_KEY}` for Claude (Flux substitution turns `$$` into `$`). Config
changes roll the pod (Reloader); start new agent sessions to pick them up.

## Scope separation

Separation is enforced by what each pod can reach, not by request inspection:

- Each pod has its own LiteLLM, ToolHive and Memini keys. Only `paseo-general`'s
  LiteLLM key is granted cloud models (`anthropic/*`, `chatgpt/*`); private's key
  has local and Mistral models only.
- General has no private ToolHive or Memini credentials; private has no GitHub token.
- Pasted text is not covered: don't paste private data into general.

## General cluster access through ToolHive

`common/helmrelease.yaml` disables token automounting for both environments. General
has no direct RBAC grants, including in `agents-scratch`. Its Cilium policy denies
the Kubernetes API entity on TCP 443/6443/7445 and TCP 6443/7445/50000 to all
destinations (Kubernetes, KubePrism and Talos); other egress stays open. Private
projects one token, for `exec` into `llm/hermes-private-0` only.

ToolHive keeps its own `mcp-readonly` and `flux-mcp` service accounts. Flux MCP can
update Flux resource specs, so it is still administrative in effect. GitHub
credentials and GitOps writes are another operational path.

Proton Pass access is deliberately retained: general can still read
`Infrastructure/homeops-bootstrap`, `Infrastructure/bws-cli`,
`Infrastructure/talos-machine` and `Infrastructure/talos-cluster`. This is not a
complete credential boundary around general.

## Credentials and identities

Bitwarden JSON items `paseo-general` and `paseo-private` hold everything their
pod consumes (jory-shape): `GIT_EMAIL`, `MISTRAL_API_KEY`, `PROTON_PASS_TOKEN`,
`PASEO_PASSWORD`, `KEYSEED` and the client keys `LITELLM_API_KEY` and
`MCP_API_KEY`, whose values the cluster generated elsewhere (the
litellm-operator's virtual keys, ToolHive's CreatedOnce VMCP keys) and were
pasted in once. General additionally holds `GH_TOKEN`, `OPENCODE_API_KEY` and
`MEMINI_API_KEY`. Proton Pass serves fnx repository credentials through
item-level viewer grants (`pass://<item-share-id>/<item-id>/<field>`).

General keeps its historical `paseo` release, service account, PVC and backup
identity, plus the `paseo.<domain>` and `svc` aliases. Private uses `paseo-private`
and `svc-private`.

## Checks

`python3 -B -m unittest discover -s tests -p test_paseo.py` (rendered permission
boundaries and key grants; needs the repo's Kustomize, Flux and yq), then
`flate test all --path kubernetes/clusters/main --no-progress` and the same for
`edge`.
