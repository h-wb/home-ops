# Paseo environments

`paseo-general` and `paseo-private` share `kubernetes/components/paseo/base`.
Their homes, credentials and runtime configuration are separate. Both use the
`paseo` mise machine class; `PASEO_DATA_SCOPE` selects the data scope.

| Environment | Providers                             | Data                                       | Operational access                                              |
| ----------- | ------------------------------------- | ------------------------------------------ | --------------------------------------------------------------- |
| General     | Claude, Codex, Mistral Vibe, OpenCode | Code, `memini-general`                     | Existing cluster permissions, scratch workloads, NFS, Tailscale |
| Private     | Mistral Vibe                          | Obsidian, personal tools, `memini-private` | No mounted service-account token, NFS or Tailscale              |

Mistral in general gets general data and credentials. Claude/Codex retain cluster
administration as requested. This separates normal workflows; it does not stop
an administrator deliberately reaching private workloads. Backend services also
retain in-cluster paths outside gateway authentication.

## Policy and stable identities

`kubernetes/components/agent-data-policy/policy.json` declares backend eligibility,
provider grants, endpoints and LiteLLM's general tool prefixes. LiteLLM mounts
it read-only. Each Paseo app overlay ships a static per-scope fragment
(`paseo-<scope>/app/{scope.json,claude.json,codex.toml}`, ConfigMap mounted at
`/etc/paseo/scope`); dotfiles' mise bootstrap merges it into the agent homes,
which pins private metadata to Mistral and disables general-only providers.
`tests/test_data_scopes.py` keeps the fragments and the policy in sync.

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

1. Create `env-paseo-general` and `env-paseo-private` Proton Pass vaults and separate
   scoped agents. General may retain approved operational vaults, but must not
   read the Obsidian item. Move that item to `env-paseo-private` with the fields
   referenced by obsidian-workspace's fnox map.
2. Create Bitwarden JSON items `paseo-general` and `paseo-private`. Both need
   `GIT_EMAIL`, `MISTRAL_API_KEY`, `PROTON_PASS_TOKEN`, `PASEO_PASSWORD`, `KEYSEED`;
   general also needs `GH_TOKEN`. Copy the existing general password and SSH
   KEYSEED unchanged. Generate independent private credentials. ExternalSecrets
   expose explicit fields, never the whole account item.
3. Confirm `192.168.1.212` is available for private SSH. General keeps `.204`.
4. Merge dotfiles and the Obsidian tooling changes. The tooling repository is
   private (`h-wb/obsidian-workspace`); copy the checkout over SSH or use a
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

Per-scope Pass sessions check a token fingerprint at bootstrap. Old broad sessions
can still remain under `.local/state/pass-cli/paseo` and repository-specific
session directories. After replacement tokens work, revoke the broad token and
log out/remove its old sessions. If general has an Obsidian vault/login, validate
private sync before removing the old vault and `.config/obsidian-headless`.
Never delete the only copy of unsynced notes. Backups can retain historical
private data and remain under operator administrative control.

Checks: `python3 -m unittest discover -s tests -p test_data_scopes.py` (policy
invariants and fragment/policy sync); run `flate test all --path
kubernetes/clusters/main --no-progress` and the same for `edge`.

Rollback by reverting the home-ops configuration commits (the policy, the
scope fragments and the pod templates roll back together) and reverting the
dotfiles revision before rolling pods. Preserve the private PVC if notes have
synced into it; a pruning revert is not a data migration.
