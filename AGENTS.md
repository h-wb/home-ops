# home-ops

Home Kubernetes and NAS GitOps monorepo; start with the [handbook](https://github.com/h-wb/handbook).

Private data only reaches trusted models. This repository is public and general: do not write personal details, private domain names, addresses, or secrets here. Use `${SECRET_DOMAIN}` for the deployment domain.

## Layout and cluster selection

- `kubernetes/apps/${CLUSTER}/`: apps by namespace; `kubernetes/clusters/${CLUSTER}/`: Flux entry points; `kubernetes/components/`: reusable Kustomize Components.
- `talos/`: machine configs and [renewing the admin certificates](docs/admin-certificates.md); `bootstrap/`: one-time cluster setup (Helmfile and mise); [hosts/edge-mac](hosts/edge-mac/README.md): edge host power settings and LaunchAgents.
- [docker/truenas](docker/truenas/README.md): NAS Compose stacks; doco-cd deploys from `main`, so merging can deploy or remove a stack.
- [`.mise.toml`](.mise.toml): tool versions, environment and tasks; [bootstrap and secret tools](kubernetes/apps/main/external-secrets/external-secrets/app/README.md#bootstrap-and-local-secret-tools): fnox, Proton Pass, Bitwarden and local `age.key`.
- See the [README](README.md#kubernetes) for the cluster topology and platform stack.

Set `CLUSTER=edge` or `CLUSTER=main` in the shell or `.mise.toml` to switch `KUBECONFIG`, `TALOSCONFIG` and the apps tree seen by mise.

## GitOps

After a push, Flux fetches Git and reconciles `cluster-apps` at `kubernetes/clusters/${CLUSTER}/ks.yaml`. Its postBuild substitution resolves values in child `ks.yaml` files first. Each child then builds its app resources and runs its own postBuild substitution with inherited cluster values and app overrides before applying HelmReleases and raw manifests. `${SECRET_DOMAIN}`, `${NFS_ADDR}`, `${CLUSTER}` and `${DOTFILES_REF}` are cluster-level inputs. `${DOTFILES_REF}` is the one dotfiles commit every pod bootstraps from; a pod declares only its `DOTFILES_ENV` (`kubernetes/components/dotfiles/README.md`).

The parent strategic-merge patch supplies Helm install and upgrade defaults and replaces the child `spec.patches` list. Put app resource patches in a Kustomize Component referenced under `components`; the Component's own `patches` run in the child build.

## New apps

- Use `kubernetes/apps/${CLUSTER}/${ns}/${app}/ks.yaml` and `app/{helmrelease.yaml,kustomization.yaml,...}`. Match the Flux Kustomization name to the app name and use the enclosing namespace.
- Most apps use a HelmRelease with bjw-s `app-template` v5.x and the [shared OCIRepository](kubernetes/components/common/repos/app-template/). Reference Components by relative path. Apps that need an upstream chart use it directly.
- Set explicit `requests.memory` lower than `limits.memory`. Without a request, Kubernetes uses the limit as the request, which can overcommit the cluster and block scheduling.
- Keep `cnpg/restore` for steady-state databases; see the [CNPG reference](kubernetes/components/cnpg/README.md) for bootstrap, recovery and scheduling.
- Use `mise run encrypt` and `mise run decrypt` for SOPS files. Bootstrap and Talos tasks that need the `Machines` vault are workstation-only.

## Check a change

- Find scoped tasks with `mise tasks ls --all`; run them as `mise run //bootstrap:default` or `mise run //docker/truenas:garage:bootstrap`. Config roots also include `hosts/edge-mac`, `kubernetes` and `talos`.
- On a workstation, check `flux get all -A` and `kubectl get events -A --sort-by=.lastTimestamp | tail`. For an unhealthy app, inspect `kubectl get hr -n <ns> <app>`, then pod logs and events.
- Reconcile the Git source with `flux -n flux-system reconcile source git flux-system` and an app with `flux -n <ns> reconcile kustomization <name>`. Use `flux -n <ns> reconcile helmrelease <name> --force` only when forcing a Helm release action is intended.
- A workshop pod has no kubeconfig. Use the [ToolHive tool gateway](kubernetes/apps/main/llm/paseo/README.md#general-cluster-access-through-toolhive), not bare `kubectl` or `flux`.

## Pitfalls

- Kustomize patch targets use literal names before Flux substitution. Omit `name` and match by group and kind only if that selects the intended resource.
- `local-hostpath` uses `WaitForFirstConsumer`: if a pod cannot schedule, its PVC stays Pending.
- Helm values may not overwrite app-generated config on persistent volumes; use the app's own override mechanism. See the [Nextcloud example](kubernetes/components/cnpg/README.md#when-it-goes-wrong).
- Do not add `# renovate:` comments to NAS Compose files; the [Compose manager](docker/truenas/README.md) already tracks their images. See [upgrade review](.kritika/renovate.md) before approving Renovate PRs.

When in doubt, mirror the neighbouring app.
