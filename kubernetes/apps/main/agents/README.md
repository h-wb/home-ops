# Paseo environments

`paseo-general` and `paseo-private` share `kubernetes/components/paseo/base`.
Their homes, credentials and runtime configuration are separate. Both use the
`paseo` mise machine class; `PASEO_DATA_SCOPE` selects the data scope.

| Environment | Providers                             | Data                                       | Operational access                                                           |
| ----------- | ------------------------------------- | ------------------------------------------ | ---------------------------------------------------------------------------- |
| General     | Claude, Codex, Mistral Vibe, OpenCode | Code, `memini-general`                     | Existing cluster permissions, scratch workloads, NFS, Tailscale              |
| Private     | Mistral Vibe, Hermes (proto)          | Obsidian, personal tools, `memini-private` | A token for `exec` into proto's `hermes-private-0` only; no NFS or Tailscale |

Mistral in general gets general data and credentials. Claude/Codex retain cluster
administration as requested. This separates normal workflows; it does not stop
an administrator deliberately reaching private workloads. Backend services also
retain in-cluster paths outside gateway authentication.

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
