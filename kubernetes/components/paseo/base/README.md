# Paseo pod base (`components/paseo/base`)

Shared by the `paseo-general` and `paseo-private` apps. A consumer of this
base must provide:

| Provided by                 | What                                                                                                                                                                                                                                   |
| --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| consumer kustomization      | a `${APP}-scope` ConfigMap with keys `scope.json`, `claude.json`, `codex.toml` (see `components/agent-data-policy/scopes/<scope>/`), mounted by this base at `/etc/paseo/scope` and merged into the agent homes by dotfiles' bootstrap |
| consumer Flux Kustomization | `postBuild.substitute` vars: `APP`, `PASEO_DATA_SCOPE`, `PASEO_CREDENTIAL_ITEM`, `PASEO_HOSTNAMES`, `PASEO_SERVICE_DOMAIN`, `PASEO_SSH_IP`                                                                                             |
| cluster                     | `components/agent-data-policy` (mounts `/etc/paseo/policy.json`), `components/kopiur/backup`; general additionally `components/tailscale/client`                                                                                       |

The base itself ships only what is identical across scopes: the HelmRelease
pod template, `${APP}-provision` / `${APP}-sshd` ConfigMaps (`config/`),
ExternalSecrets, and the volume mounts. Kubernetes blocks the pod from starting
if the required `${APP}-scope` ConfigMap or one of its mounted keys is missing.
Kustomize does not validate that reference, so provide the ConfigMap when
adding the base to a new app.

The scope fragments are mounted read-only in `tools`, `app` and `sshd` so that
bootstrap and later dotfiles applies see the same inputs. Client environment
references in fragments must survive Flux substitution: write `$${MCP_API_KEY}`
in the source to deliver `${MCP_API_KEY}` to the client.

Fail-closed at runtime: dotfiles' mise bootstrap errors when
`/etc/paseo/scope` is absent, so a pod whose overlay is wrong refuses to
start rather than running with a stale or general config.
