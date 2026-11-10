# Paseo environments

The workshops of the [assistant design](../DESIGN.md). Two Paseo pods in the
`llm` namespace, **general** and **private**, with separate homes, credentials
and agent config. `PASEO_DATA_SCOPE` names the scope; both use dotfiles' `paseo`
mise class for CLIs, repos and shell only.

```text
paseo/
├── ks.yaml          # general and private Flux Kustomizations
├── common/          # shared HelmRelease and ExternalSecrets
├── general/
│   ├── config/      # paseo.json, opencode.json for this scope
│   └── ...          # GitHub/memory credentials, NFS and the API egress policy
└── private/
    ├── config/
    └── ...          # explicit Hermes token mount
```

Edit `ks.yaml` for names, scope, credential item, hostnames and backup
settings; `common/helmrelease.yaml` for shared pod settings; the overlay's
`helmrelease.yaml` for environment-specific values.

| Environment | Agents                          | Models (LiteLLM key)                         | Tools and data                                                                             |
| ----------- | ------------------------------- | -------------------------------------------- | ------------------------------------------------------------------------------------------ |
| General     | Claude Code, OpenCode           | Claude subscription, ChatGPT, Mistral, local | `toolhive` (mcp-general gateway), `memini` (memini-general), NFS, Tailscale                |
| Private     | OpenCode, Hermes (`llm/hermes`) | Mistral, local                               | `toolhive` (mcp-private gateway), `memini` (memini-private), Obsidian; no NFS or Tailscale |

## Agent config

The agents' MCP servers (ToolHive, Memini, the Chromium sidecar) are defined in
dotfiles (`conf.d/ai/`), the same definitions every workstation uses, and
rendered by the pod-start bootstrap for this pod's `PASEO_DATA_SCOPE`. Each
overlay's `config/` holds the rest. It becomes the `${APP}-config` ConfigMap,
mounted read-only at `/etc/paseo/config`:

- `opencode.json`: models and providers, read in place (`OPENCODE_CONFIG`).
  OpenCode layers it over dotfiles' `~/.config/opencode/opencode.json` and
  merges both, so the MCP servers stay out of it.
- `paseo.json`: merged into `~/.paseo/config.json`, where Paseo also keeps its
  own state. Our keys win; everything else is kept.

Provisioning is the `tools` init container, on the app's image: `mise bootstrap
--from` the dotfiles repo into `~/.dotfiles`, an `emptyDir` cloned fresh at every
start and read-only in the app container. mise itself is the `ghcr.io/jdx/mise`
image mounted at `/opt/mise` in both containers, so its shims resolve
everywhere. Work on dotfiles in `~/Repositories/dotfiles`. Dotfiles does the
merge (`conf.d/paseo/mise.paseo-overlay.toml`), and that mount path is the only
thing the two repos share. Private adds `--skip=repos,task`: it has no GitHub
credential, and no Proton Pass secrets to log in for.

The files hold no secrets. Credentials come from ExternalSecrets as environment
variables and are referenced by name (`{env:LITELLM_API_KEY}` for OpenCode). The
ToolHive gateways need none: the pods call them in-cluster and
`llm/toolhive/config/networkpolicy.yaml` admits only this scope's pod. Config
changes roll the pod (Reloader); start new agent sessions to pick them up.

## Scope separation

Separation is enforced by what each pod can reach, not by request inspection:

- Each pod has its own LiteLLM and Memini keys, and only its own scope's ToolHive
  gateway admits it (NetworkPolicy, no key). Only `paseo-general`'s
  LiteLLM key lists models outside the trusted set (`anthropic/*`, `chatgpt/*`); private's key
  has local and Mistral models only.
- General cannot reach the private gateway and has no private Memini credentials;
  private has no GitHub token.
- Pasted text is not covered: don't paste private data into general.

## General cluster access through ToolHive

`common/helmrelease.yaml` disables token automounting for both environments. General
has no direct RBAC grants. Its Cilium policy denies
the Kubernetes API entity on TCP 443/6443/7445 and TCP 6443/7445/50000 to all
destinations (Kubernetes, KubePrism and Talos); other egress stays open. Private
projects one token, for `exec` into `hermes-private-0` only.

ToolHive keeps its own `mcp-readonly` and `flux-mcp` service accounts. Flux MCP can
update Flux resource specs, so it is still administrative in effect. GitHub
credentials and GitOps writes are another operational path.

In the pod there is **no kubeconfig**: token automounting is off, Cilium denies the
API, and `kubernetes/clusters/*/kubeconfig` is gitignored (workstation-only), so the
`KUBECONFIG` that `.mise.toml` sets points at nothing and bare `kubectl`/`flux`
fall back to localhost:8080. Run cluster operations through the ToolHive MCP tools
instead (`kubectl_kubectl_get`, `kubectl_get_custom_resource`, `flux_get_kubernetes_resources`,
`flux_reconcile_flux_resource`, …) — e.g. reconciling an app is
`flux_reconcile_flux_resource(kind=Kustomization, name=<app>, namespace=<ns>, with_source=true)`
then the same for `kind=HelmRelease`, which replaces
`mise exec -- flux reconcile ks <app> -n <ns> --with-source` + `flux reconcile hr <app> -n <ns>`
from a workstation.

General's Proton Pass token is granted only the `Automation General` vault
(repository credentials). Home-ops' bootstrap and Talos material
(`homeops-bootstrap`, `bws-cli`, `talos-machine`, `talos-cluster`) lives in
`Machines`, read by workstations only: either would hand a pod every Bitwarden
secret or the cluster CAs.

## Credentials and identities

Bitwarden JSON items `paseo-general` and `paseo-private` hold the human
credentials `GIT_EMAIL`, `MISTRAL_API_KEY`, `PROTON_PASS_TOKEN` and
`PASEO_PASSWORD`. Old `KEYSEED` (the removed sshd) and `MCP_API_KEY` (the pods
reach ToolHive without a key) fields are unused. General additionally holds `GH_TOKEN` and `OPENCODE_API_KEY`.
The LiteLLM virtual key never passes through Bitwarden: the litellm-operator
writes its Secret into the pods' own namespace from the `virtualkey.yaml` CR
beside them, the helmrelease binds it as `LITELLM_API_KEY` and builds Claude
Code's `x-litellm-api-key` header from it (`$(LITELLM_API_KEY)`), so a rotation
needs nothing. The
general pod's agent keys (GH, opencode, memini) come out of
the `paseo-agents` Secret, whose single ExternalSecret extracts the credential
and `memini` items together — memini's client key lives once, in the
`memini` item, read by the server and the pod alike. Proton Pass serves the
repositories' credentials from the `Automation General` vault, through one vault
grant and readable `pass://Automation General/<item>/<field>` references.

General keeps its historical `paseo` release, service account, PVC and backup
identity, plus the `paseo.<domain>` and `svc` aliases. Private uses `paseo-private`
and `svc-private`.

## Home volumes

Each home is a `ceph-block` PVC from the kopiur backup component, backed up
daily and annotated so Flux never prunes it.

- A restore runs as the uid recorded on the backup (overlay patch on the
  `Restore`). Without it every file comes back owned by the mover's uid, and
  mise refuses a home it cannot chmod.
- Backups skip directories that carry a `CACHEDIR.TAG`: uv virtualenvs
  (project `.venv`, mise's pipx tools), Cargo and Gradle caches. After a
  restore, mise still reports those tools as installed; reinstall them with
  `mise install --force <tool>` and re-run `uv sync` in the repos.
- The backups are filed under `<app>@agents`, the namespace the pods ran in
  until 2026-11-09. The overlays pin that identity, so the history stays in one
  piece, and make a restore fail when it finds no backup: a home never comes
  back empty without anyone noticing.

## Checks

`python3 -B -m unittest discover -s tests -p test_paseo.py` (rendered permission
boundaries and key grants; needs the repo's Kustomize, Flux and yq), then
`flate test all --path kubernetes/clusters/main --no-progress` and the same for
`edge`.
