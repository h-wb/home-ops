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
rendered by the pod-start bootstrap for this pod's `PASEO_DATA_SCOPE`. The
private pod also gets general memory as a read-only server (`MEMINI_GENERAL_URL`
and a read-only key). Each
overlay's `config/` holds the rest. It becomes the `${APP}-config` ConfigMap,
mounted read-only at `/etc/paseo/config`:

- `opencode.json`: models and agents, read in place (`OPENCODE_CONFIG`). The
  gateway is its only provider; private allows no other (`enabled_providers`),
  because OpenCode's own free hosted models need no key.
  OpenCode layers it over dotfiles' `~/.config/opencode/opencode.json` and
  merges both, so the MCP servers stay out of it.
- `paseo.json`: merged into `~/.paseo/config.json`, where Paseo also keeps its
  own state. Our keys win; everything else is kept.

## Profiles

A profile is a saved provider, model and mode with a "when to use" note. You
pick one in the model picker; an agent that delegates reads the notes
(`list_profiles`) and launches the worker that fits. They are declared in
`paseo.json` (`daemon.agentProfiles`):

| Profile     | For                                                       | General                             | Private                            |
| ----------- | --------------------------------------------------------- | ----------------------------------- | ---------------------------------- |
| Orchestrate | A change of more than one step: plans, delegates, decides | Claude Code, Fable, auto mode       | None                               |
| Plan        | Hard design or debugging questions; no edits              | Claude Code, Opus, plan mode        | OpenCode, Mistral Large, plan mode |
| Explore     | Where and how is X: paths and line numbers; no edits      | OpenCode, Mistral Medium, plan mode | None                               |
| Build       | A well-specified change                                   | OpenCode, Mistral Large             | OpenCode, Mistral Large            |
| Review      | An independent read of a diff or plan; no edits           | OpenCode, GLM, plan mode            | OpenCode, GLM, plan mode           |

Plan mode is the read-only one in both agents.

- Orchestrate is [flow H](../docs/flows.md#h-a-larger-change-orchestrated): the
  strongest model takes the few turns that plan and decide, and starts Explore,
  Build and Review for the many turns of reading, editing and checking. The
  order is the `orchestrate` skill in dotfiles (`conf.d/paseo/skills`). A small
  change does not need it: start Build, or any agent, directly.
- Orchestrate comes in three: Fable for a hard or vague change, Opus for the
  everyday one (it draws less of the Claude window), and Sol, which is OpenCode's
  `coordinator` on the ChatGPT subscription.
- The Claude subscription carries Orchestrate and Plan only. When its window
  is used up, OpenCode's `coordinator` mode is the same idea in one agent: GPT
  Sol, with its own explorer (Mistral Medium) and reviewer (GLM).
- Each general profile's note ends with a fallback, a provider, model and mode on
  the other subscription or API, for when its own is at a limit. The
  `orchestrate` skill starts the same prompt there once. Private has none: its
  data stays on Mistral.
- Private has no Orchestrate or Explore: no agent there starts another, so you
  pick the profile, and OpenCode's own Plan mode is the cheap reader.
- Review runs on a different model family from Plan and Build, so it does not
  share their blind spots.
- The list is an array, and the merge replaces an array whole: a profile made
  in the app is gone at the next pod start. Add it here.
- In general, agents can act on the notes: Paseo's tools are injected there (an
  app setting, **Settings → host → Agents → Enable Paseo tools**). In private
  they are not, and OpenCode's `create_agent` and `send_agent_prompt` stay
  disabled, so no agent there starts or prompts another one, the assistant
  included. The profiles are for you to pick.
- Paseo's own skills (`/paseo-advisor`, `/paseo-committee`, `/paseo-handoff`)
  read the same notes before they choose a worker.

Provisioning is the `tools` init container, on the app's image: `mise -E
paseo,paseo-overlay bootstrap --from` the dotfiles at the cluster's pinned commit
(`DOTFILES_REF`, `components/dotfiles/README.md`) into `~/.dotfiles`, an
`emptyDir` cloned fresh at every start and read-only in the app container;
`--save-env` keeps the declared environment for the app container. A failed
bootstrap logs one line and the pod starts. mise itself is the `ghcr.io/jdx/mise`
image mounted at `/opt/mise` in both containers, so its shims resolve
everywhere. Work on dotfiles in `~/Repositories/dotfiles`. Dotfiles does the
merge (`conf.d/paseo/mise.paseo-overlay.toml`), and that mount path is the only
thing the two repos share. Private adds `--skip=repos,task`: it has no GitHub
credential, and no Proton Pass secrets to log in for. The workstation pods
(code-server, neko) use `components/dotfiles`; this stays on mise's own
`--from` because there is no secrets session to protect, the checkout is
already fresh and read-only, and mise comes from an image rather than the volume.

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
credentials `GIT_EMAIL`, `PROTON_PASS_TOKEN` and `PASEO_PASSWORD`. Old `KEYSEED`
(the removed sshd), `MCP_API_KEY` (the pods reach ToolHive without a key) and
`MISTRAL_API_KEY` (every model call goes through LiteLLM) fields are unused.
General additionally holds `OPENCODE_API_KEY` and `GH_TOKEN` (the owner's
personal token, no longer in the pod; see below).
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

General's GitHub identity is the GitHub App `bot-tintin`: Contents, Pull requests
and Issues write; Actions, Checks and Statuses read; no Workflows, because
home-ops runs a self-hosted runner on PRs and holds the Renovate key as a repo
secret. external-secrets mints a 1h installation token every 30m and renders it
as gh's `hosts.yml` in the `bot-tintin-token` Secret, mounted read-only at
`/var/run/secrets/bot-tintin` with `GH_CONFIG_DIR` pointing there; git uses it
through `gh auth git-credential`. Reloader is told to ignore that Secret, or every
refresh would recreate the pod. `GH_TOKEN` is not set in the pod: gh would prefer
it. There is no fallback: without the Secret, gh and git fail as not logged in
rather than act as the owner. The config dir is read-only, so gh commands that
write config (`gh auth login`, `gh config set`, `gh alias set`) fail there. The
personal token still sits in the `paseo-agents`
Secret and the Bitwarden item, unused, until the owner removes it. Workflow-file
changes go to the owner as a PR-comment patch, applied with the dotfiles `land <pr>`
task from his own environment (code-server, workstation or neko), never from the Paseo pod. The app's three fields live in the
Bitwarden item `bot-tintin` (JSON:
`APP_ID`, `INSTALLATION_ID`, `PRIVATE_KEY`), named after the identity so other
consumers can read it through their own ExternalSecret.

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
