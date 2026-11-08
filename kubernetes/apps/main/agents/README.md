# Paseo environments

Two Paseo pods, **general** and **private**, with separate homes, credentials and
agent config. `PASEO_DATA_SCOPE` names the scope; both use dotfiles' `paseo` mise
class for CLIs, repos and shell only.

```text
paseo/
├── ks.yaml          # general, private and scratch Flux Kustomizations
├── common/          # shared HelmRelease, ExternalSecrets, authorized_keys
├── general/
│   ├── config/      # paseo.json, opencode.json for this scope
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

The agents' MCP servers (ToolHive, Memini, the Chromium sidecar) are defined in
dotfiles (`conf.d/ai/`), the same definitions every workstation uses, and
rendered by the pod-start bootstrap for this pod's `PASEO_DATA_SCOPE`. Each
overlay's `config/` holds the rest. It becomes the `${APP}-config` ConfigMap,
mounted read-only at `/etc/paseo/config`:

- `opencode.json`: models and providers, read in place (`OPENCODE_CONFIG`).
  OpenCode layers it over dotfiles' `~/.config/opencode/opencode.json` and
  merges both, so the MCP servers stay out of it.
- `paseo.json`: merged into `~/.paseo/config.json` on every pod start by the
  dotfiles `[dotfiles]` merge entry (`conf.d/paseo/mise.paseo-overlay.toml`),
  applied by the `tools` init container's `mise bootstrap --from` — Paseo keeps
  its own state in that file, so only the overlay's keys are written. Our keys
  win; everything else is kept.

The files hold no secrets. Credentials come from ExternalSecrets as environment
variables and are referenced by name (`{env:LITELLM_API_KEY}` for OpenCode). The
ToolHive gateways need none: the pods call them in-cluster and
`llm/toolhive/config/networkpolicy.yaml` admits only this scope's pod. Config
changes roll the pod (Reloader); start new agent sessions to pick them up.

## Scope separation

Separation is enforced by what each pod can reach, not by request inspection:

- Each pod has its own LiteLLM and Memini keys, and only its own scope's ToolHive
  gateway admits it (NetworkPolicy, no key). Only `paseo-general`'s
  LiteLLM key is granted cloud models (`anthropic/*`, `chatgpt/*`); private's key
  has local and Mistral models only.
- General cannot reach the private gateway and has no private Memini credentials;
  private has no GitHub token.
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

Bitwarden JSON items `paseo-general` and `paseo-private` hold the human
credentials `GIT_EMAIL`, `MISTRAL_API_KEY`, `PROTON_PASS_TOKEN`, `PASEO_PASSWORD`
and `KEYSEED` (an old `MCP_API_KEY` field is unused: the pods reach ToolHive
without a key). General additionally holds `GH_TOKEN`, `OPENCODE_API_KEY` and
`LITELLM_API_KEY` — the last one only composes Claude Code's `x-litellm-api-key`
header, the raw virtual key never passing through Bitwarden: the
litellm-operator writes its Secret into the pods' own namespace from the
`virtualkey.yaml` CR beside them, and the helmrelease binds it directly. The
general pod's agent keys (GH, opencode, memini, the Claude header) come out of
the `paseo-agents` Secret, whose single ExternalSecret extracts the credential
and `memini` items together — memini's client key lives once, in the
`memini` item, read by the server and the pod alike. Proton Pass serves fnx
repository credentials through item-level viewer grants
(`pass://<item-share-id>/<item-id>/<field>`).

General keeps its historical `paseo` release, service account, PVC and backup
identity, plus the `paseo.<domain>` and `svc` aliases. Private uses `paseo-private`
and `svc-private`.

## Checks

`python3 -B -m unittest discover -s tests -p test_paseo.py` (rendered permission
boundaries and key grants; needs the repo's Kustomize, Flux and yq), then
`flate test all --path kubernetes/clusters/main --no-progress` and the same for
`edge`.
