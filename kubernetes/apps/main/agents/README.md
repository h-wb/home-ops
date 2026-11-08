# Paseo environments

Both Paseo environments live under `paseo/`, with their instance settings together
in `paseo/ks.yaml`. Their homes, credentials and runtime configuration are separate.
Both use the `paseo` mise machine class; `PASEO_DATA_SCOPE` selects the data scope.

```text
paseo/
├── ks.yaml          # general, private and scratch Flux Kustomizations
├── common/          # shared HelmRelease, ExternalSecrets and bootstrap files
├── general/         # GitHub/memory credentials, NFS and the API egress policy
├── private/         # explicit Hermes token mount and home-retention patch
└── scratch/         # retained namespace and quotas, no agent RBAC grants
```

Edit `ks.yaml` for names, scope, credential item, hostnames, SSH IP and backup
settings. Edit `common/helmrelease.yaml` for shared pod settings and
`general/helmrelease.yaml` or `private/helmrelease.yaml` for environment-specific
values. Both overlays import `../common` as a normal Kustomize base; there is no
global Paseo component. Cross-app components for backup, Tailscale and the data
policy remain in `ks.yaml`.

The Flux names remain `paseo`, `paseo-private` and `paseo-scratch`. In particular,
general keeps its historical `paseo` release, service account and home PVC, so
moving these files does not rename persistent resources or client identities.

| Environment | Providers                             | Data                                       | Operational access                                                         |
| ----------- | ------------------------------------- | ------------------------------------------ | -------------------------------------------------------------------------- |
| General     | Claude, Codex, Mistral Vibe, OpenCode | Code, `memini-general`                     | Kubernetes through ToolHive, NFS, Tailscale                                |
| Private     | Mistral Vibe, Hermes (`llm/hermes`)   | Obsidian, personal tools, `memini-private` | A token for `exec` into llm's `hermes-private-0` only; no NFS or Tailscale |

All general providers use ToolHive's Kubernetes and Flux servers for cluster
operations. The general pod has no mounted service-account token or direct RBAC
grants, including in `agents-scratch`. Private retains its explicit token for the
Hermes provider. Backend services also retain in-cluster paths outside gateway
authentication.

## General cluster access through ToolHive

`common/helmrelease.yaml` disables token automounting for both environments,
including init containers and sidecars. General's Cilium policy denies
the local Kubernetes API entity on TCP 443/6443/7445 and denies TCP
6443/7445/50000 to all destinations (Kubernetes, KubePrism and Talos). Other
egress, including ToolHive HTTPS, providers, DNS and memory, remains available.
This is a direct-connection restriction, not a general ban on tunnels or proxies;
Tailscale and external tools remain available.

ToolHive retains its own `mcp-readonly` and `flux-mcp` service accounts and RBAC.
The kubectl server is read-only; Flux can still update Flux resource specs, not
just request reconciliation. These MCP permissions remain administrative in
effect and must be reviewed separately before claiming read-only cluster access.
GitHub credentials and GitOps writes also remain an operational access path.

Proton Pass access is deliberately retained. The general reader can still obtain
bootstrap credentials through its approved `Infrastructure/homeops-bootstrap`,
`Infrastructure/bws-cli`, `Infrastructure/talos-machine` and
`Infrastructure/talos-cluster` item grants. Neither disabling token automounting
nor removing fnox references revokes these grants. Cached sessions and previously
materialized credentials also remain. This change removes the pod identity's
permissions and blocks direct API connections; it does not establish a complete
credential boundary around the general environment.

For rollout:

1. Reconcile `agents/paseo` and `agents/paseo-scratch`. Their `prune: true`
   inventories remove `paseo-readonly`, `paseo-flux-write`,
   `paseo-pod-restart` (binding and role), and `agents-scratch/paseo-edit`.
   The HelmRelease change rolls the general pod; keep private untouched.
2. In the replacement general pod, verify the service-account directory is
   absent in app/init/sidecar specs, direct Kubernetes and Talos connections fail,
   and a Kubernetes read through ToolHive succeeds. From an operator session,
   verify `system:serviceaccount:agents:paseo` cannot read pods, update Flux
   objects, delete pods, or edit scratch workloads/Secrets.

Scratch namespace, quotas and existing workloads are retained, without a
general-agent edit grant. The shared pod base still supports private's explicit
Hermes token.

## Policy and stable identities

`kubernetes/components/agent-data-policy/policy.json` declares backend eligibility,
provider grants, endpoints and LiteLLM's general tool prefixes. LiteLLM mounts
it read-only. Each scope's agent config fragments live next to it in
`components/agent-data-policy/scopes/<scope>/{scope.json,claude.json,codex.toml}`;
each app references its scope's files in a `${APP}-scope` ConfigMap mounted at
`/etc/paseo/scope`, and dotfiles' mise bootstrap merges them into the agent
homes, which pins private metadata to Mistral and disables general-only
providers. `tests/test_data_scopes.py` keeps the fragments and the policy in
sync.

The local common base mounts these fragments read-only in `tools`, `app` and
`sshd`, alongside its bootstrap and data-policy ConfigMaps. A missing scope mount
fails dotfiles bootstrap. Client environment references must survive Flux
substitution: write `$${MCP_API_KEY}` to deliver `${MCP_API_KEY}` to the client.

Use `<service>-<scope>` for environments/endpoints and `<service>-<client>-<scope>`
for client credentials. General includes operational secrets; it does not mean public.

The existing general release, Flux Kustomization, service account, PVC and backup
identity remain `paseo`. Its old hostname and `svc` wildcard remain aliases.
Private uses new `paseo-private` resources and a `svc-private` wildcard, added to
the gateway certificate. These historical exceptions prevent data recreation,
SSH key changes and client re-pairing merely to standardize naming.

## Coordinated rollout

These changes are a draft across home-ops, dotfiles and obsidian-workspace.
The policy and the per-scope pod config fragments ship together in home-ops,
so no cross-repo ordering applies to them; merge the three when their own
prerequisites are met.
Start new agent sessions after rollout; existing sessions keep their launch
configuration.

The existing host must receive the required `/etc/paseo/scope` mounts before
updating dotfiles. [PR 4758](https://github.com/h-wb/home-ops/pull/4758) staged
these inputs using the current MCP endpoint and credentials; its pod rollout
and mounted files were verified on 2026-11-03. This rollout replaces that
transitional component with the per-scope fragments below.

1. Create separate scoped Proton Pass agents with item-level viewer grants. Keep
   the existing `Personal/Obsidian` login and grant it only to private. Machine-only
   external/workstation credentials live in `Automation`; approve each item for
   its consumers rather than granting general the entire vault. Administrative
   bootstrap/recovery credentials stay in `Infrastructure`. No dedicated Paseo
   vaults or duplicate login items are needed.
   External personal account logins, including Obsidian, stay in `Personal`;
   `Homelab` holds logins to self-hosted services. Repository references follow
   the canonical item location.
   Item grants expose direct item shares rather than the containing vault. Use
   `pass://<item-share-id>/<item-id>/<field>` in the consumer's fnox references;
   get identifiers with `pass-cli personal-access-token access list-access
   --personal-access-token-name <agent> --output json`. Name-based vault
   references require vault access and will not resolve for an item-only token.
   The home-ops root and pipelines configs select the native `paseo-general`
   fnox profile from their mise environment on the scoped general host. Dotfiles
   does the same for its host-owned Sento map. Its managed pipelines checkout
   explicitly selects `paseo-general-cluster`, combining the scoped reader with
   the existing in-cluster Prefect endpoint. Other hosts keep their default
   named-vault references. Direct fnox honors `FNOX_PROFILE`; mise grants use an
   explicit nearest `[secrets.fnox].profile` when configured.
   Apply grants and update/verify consumer references before switching tokens.
2. Create Bitwarden JSON items `paseo-general` and `paseo-private`. Both need
   `GIT_EMAIL`, `MISTRAL_API_KEY`, `PROTON_PASS_TOKEN`, `PASEO_PASSWORD`, `KEYSEED`;
   general also needs `GH_TOKEN`. The existing general BWS item has been renamed
   to `paseo-general`; both scoped tokens and their exact item grants are verified.
   The current host reads its temporary `PROTON_PASS_TOKEN_LEGACY` field, while
   this rollout consumes the new `PROTON_PASS_TOKEN`. Remove the legacy field
   only after the new reader and consumers work. Copy the existing general password and SSH
   KEYSEED unchanged. Generate independent private credentials. ExternalSecrets
   expose explicit fields, never the whole account item.
3. Confirm `192.168.1.212` is available for private SSH. General keeps `.204`.
4. Merge dotfiles first, then the Obsidian and pipelines tooling changes. The
   Obsidian tooling repository is private (`h-wb/obsidian-workspace`); copy the checkout over SSH or use a
   repository-scoped read-only credential on private. Never copy the general
   GitHub token or publish the gitignored vault.
5. Merge home-ops when ready for a general pod restart. Generated per-scope MCP
   and LiteLLM keys are published to Bitwarden and consumed in `agents`; allow
   that initial reconciliation to finish. General Memini's existing `codex` key
   is published as `memini-paseo-general` without rotating any memory credentials.
6. Connect `paseo-private.<domain>`, clone the Obsidian tooling there, complete its
   one-time sync setup (including 2FA when needed), create a Local workspace and
   start the continuous sync script.

## Validation and cleanup

Check that private mounts only its own home/credentials, enables only Mistral and
uses private tools/memory/metadata. Confirm Mistral in general uses general tools
and memory. The private policy disables automatic agent creation/handoffs; keep
private summaries in that environment and do not configure private as an
automatic general-host delegation destination.

Dotfiles supplies the global `proton-login` mise task template. The pod's
bootstrap and repository `pass:login` tasks share it; repositories only declare
their session name. On macOS it reads `pass-cli-<session>` from Keychain; pods
use `PROTON_PASS_TOKEN`. It checks fingerprints on login, refreshes expired
sessions, and clears the named cache when credentials are missing or rejected.
Secret-consuming tasks depend on login. The required pod credential Secret
must exist before provisioning starts.

The two stores have distinct roles: Bitwarden supplies workload credentials
through External Secrets; Proton Pass supplies fnox repository credentials
and operator bootstrap/recovery material. Proton's `Infrastructure` vault includes
Bitwarden administration tokens, so vault-wide access is administrative.
Item-level viewer grants can limit a consumer to its required credentials. Separate
session directories do not restrict token grants. Give private only its approved
private resources; review general's retained operational grants explicitly.

The 2026-11-03 Proton organization moved the existing infrastructure/bootstrap
items into `Infrastructure`, machine integrations into `Automation`, and the
Paseo website login into `Homelab/Paseo`. The old `env-home-ops`, `env-dotfiles`
and `env-dlt` vaults have no active items. Existing reader tokens must be granted
their approved items in the new locations; session directories do not migrate
grants. Use normal viewer agent tokens at runtime, never the short-lived
administrative PAT used for the move. Only the account owner can delete the
empty old vaults; their deletion is not required to resolve the new references.

Old broad sessions
can still remain under `.local/state/pass-cli/paseo` and repository-specific
session directories. After replacement tokens work, revoke the broad token and
log out/remove its old sessions. If general has an Obsidian vault/login, validate
private sync before removing the old vault and `.config/obsidian-headless`.
Never delete the only copy of unsynced notes. Backups can retain historical
private data and remain under operator administrative control.

Checks: `python3 -B -m unittest discover -s tests -p test_data_scopes.py` (policy
invariants, fragment/policy sync, rendered authentication references and scope
mounts; requires the repo's Kustomize, Flux and yq tools); run `flate test all --path
kubernetes/clusters/main --no-progress` and the same for `edge`.

Rollback by reverting the home-ops configuration commits (the policy, the
scope fragments and the pod templates roll back together) and reverting the
dotfiles revision before rolling pods. Preserve the private PVC if notes have
synced into it; a pruning revert is not a data migration.
