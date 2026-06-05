# home-ops — AI Assistant Guide

Home Kubernetes monorepo managed with GitOps. Read this before suggesting changes to the repo.

## Repository layout

```
home-ops/
├── kubernetes/
│   ├── apps/            # per-namespace apps, split per cluster
│   │   ├── main/        # main cluster (3x Talos: tal0s/1s/2s, all control-plane)
│   │   └── edge/        # edge cluster
│   ├── clusters/        # one dir per cluster, holds cluster-apps Flux Kustomization
│   │   ├── main/
│   │   └── edge/
│   └── components/      # reusable kustomize Components consumed by app ks.yaml's
├── talos/               # Talos Linux machine configs (one dir per cluster)
├── bootstrap/           # one-time cluster bootstrap (helmfile.d + mise)
├── scripts/             # bootstrap-apps.sh + lib/
├── docs/                # mdBook
├── Taskfile.yml         # entrypoint for ops tasks (see `.taskfiles/`)
├── .mise.toml           # tool versions + env (sets KUBECONFIG from $CLUSTER)
└── age.key              # SOPS age private key (gitignored in spirit; managed locally)
```

## Clusters

| Cluster  | Nodes                                                                       | Purpose                                              |
| -------- | --------------------------------------------------------------------------- | ---------------------------------------------------- |
| **main** | 3× Talos (tal0s, tal1s, tal2s — all control-plane, NVMe storage, Rook/Ceph) | Production homelab — auth, photos, media, automation |
| **edge** | 1× node                                                                     | Edge services / lighter workloads                    |

Switch clusters by setting `CLUSTER=edge` (or `main`) in the shell or `.mise.toml`. That swaps `KUBECONFIG`, `TALOSCONFIG`, and the apps tree mise sees.

## Key technologies

| Category            | Tool                                                                                              | Notes                                                           |
| ------------------- | ------------------------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| OS                  | Talos Linux                                                                                       | configs in `talos/`                                             |
| GitOps              | Flux                                                                                              | recursive scan of `kubernetes/apps/${CLUSTER}/`                 |
| Networking          | Cilium (eBPF)                                                                                     | CNI                                                             |
| Gateway             | Envoy Gateway                                                                                     | `envoy-internal` + `envoy-external` Gateways in `network` ns    |
| DNS                 | external-dns                                                                                      | syncs HTTPRoutes to Cloudflare / k8s-gateway                    |
| Secrets             | external-secrets + **Bitwarden Secrets Manager** (`bitwarden-secrets-manager` ClusterSecretStore) | not 1Password                                                   |
| Sensitive Git files | SOPS + age (`age.key` at repo root)                                                               |                                                                 |
| Postgres            | **CloudNativePG** + plugin-barman-cloud                                                           | migrated off CrunchyData PGO in 2026-05                         |
| Caches/KV           | Dragonfly                                                                                         | redis-compatible                                                |
| Block storage       | Rook-Ceph (`ceph-block`, `ceph-filesystem`, `ceph-bucket`)                                        | hyper-converged on the 3 Talos nodes                            |
| Local hostpath      | `local-hostpath` storage class (`WaitForFirstConsumer`)                                           | used by CNPG, etc.                                              |
| Backup              | volsync (Kopia repo on NFS), CNPG → Barman → Garage S3                                            |                                                                 |
| Object storage      | Garage (`s3.${SECRET_DOMAIN}`)                                                                    | for CNPG Barman + other                                         |
| OCI mirror          | spegel                                                                                            | per-node local image cache                                      |
| CI                  | Renovate + GitHub Actions                                                                         |                                                                 |
| App chart           | bjw-s `app-template` (v5.x)                                                                       | shared OCIRepository at `components/common/repos/app-template/` |

## GitOps flow

```
git push → Flux GitRepository fetches → cluster-apps Kustomization reconciles →
  child ks.yaml's reconcile → HelmReleases / raw manifests → k8s resources
```

- Cluster entry point: `kubernetes/clusters/${CLUSTER}/ks.yaml` (the `cluster-apps` Flux Kustomization).
- That parent does **postBuild substitution** (Level 1) for variables that appear in child `ks.yaml` files themselves.
- It also applies a **strategic-merge patch** to every child Kustomization that injects defaults — including `spec.patches` (with HelmRelease default install/upgrade settings).
- ⚠️ **Gotcha**: because of that parent patch, **`spec.patches` you set in a child `ks.yaml` gets overwritten** (kustomize replaces the list, doesn't merge). If you need to patch a kustomize resource, do it via a **Component** (`components: [...]`), not via `spec.patches` in the child ks. (Components' own `patches:` blocks survive — they're applied during the kustomize build, before the parent override touches anything.)

## Postgres (CNPG, post-2026-05 migration)

`kubernetes/components/cnpg/` — vrozaksen-style structure:

```
cnpg/
├── base/              # Cluster (no bootstrap), ObjectStore, ScheduledBackup, ExternalSecret
├── initdb/            # bootstrap.initdb (plain empty DB) — for net-new apps
├── import/            # bootstrap.initdb.import (one-shot live import from external Postgres)
├── restore/           # bootstrap.recovery from Barman ← default for steady-state apps
├── pooler/            # opt-in PgBouncer Pooler (only authentik uses it today)
└── extensions/
    └── vchord/        # PG 18 extension-mount for VectorChord (immich)
```

Apps pick the bootstrap mode by directory reference:

```yaml
# kubernetes/apps/main/<ns>/<app>/ks.yaml
components:
  - ../../../../../components/cnpg/restore # production default
dependsOn:
  - name: plugin-barman-cloud # gates transitively on cloudnative-pg
    namespace: database
healthCheckExprs:
  - apiVersion: postgresql.cnpg.io/v1
    kind: Cluster
    failed: status.conditions.filter(e, e.type == 'Ready').all(e, e.status == 'False')
    current: status.conditions.filter(e, e.type == 'Ready').all(e, e.status == 'True')
postBuild:
  substitute:
    APP: <app>
    # Optional: CNPG_IMAGE, CNPG_VERSION, CNPG_SIZE, CNPG_POOLER_MODE, etc.
```

- Cluster names: `postgres-${APP}`. Generated app secret: `postgres-${APP}-app` with `uri`, `host`, `password`, `username`, `port`, `dbname`, `pgpass`, `jdbc-uri`.
- Connect direct via `postgres-${APP}-rw.${NS}.svc`. Pooler (when present) is `pooler-${APP}-rw`.
- Extensions: standard CNPG postgres image is used; per-app extension `.so` files are mounted from separate `vchord-scratch`-style images via `spec.postgresql.extensions` (PG 18 feature). See `cnpg/extensions/vchord/` for the pattern — it's a Component you reference alongside `cnpg/restore` and the Cluster picks up the patch.
- Image override (PostGIS, etc.): pass `CNPG_IMAGE: ghcr.io/cloudnative-pg/postgis` + `CNPG_VERSION: 18-3-system-trixie` in the app's `postBuild.substitute`. No variant Component needed.

## Secrets

- **Bitwarden Secrets Manager** is the ClusterSecretStore. Per-app secrets are usually `ExternalSecret`s under each app's `app/externalsecret.yaml`, extracting from a Bitwarden item by name.
- The CNPG component's S3 creds (`postgresql-bucket` Bitwarden item) are shared across all apps.
- SOPS-encrypted secrets in Git use the age key at `age.key`. Tasks have a `sops:` namespace.

## Conventions

- One directory per app: `kubernetes/apps/${CLUSTER}/${ns}/${app}/{ks.yaml, app/{helmrelease.yaml, kustomization.yaml, ...}}`.
- App namespace and Flux Kustomization name match the app name.
- Almost everything is a `HelmRelease`, mostly using bjw-s `app-template` v5.x (shared OCIRepository at `components/common/repos/app-template/`). A few use upstream charts (nextcloud, cloudnative-pg, authentik, kube-prometheus-stack, etc.).
- Reusable Components live at `kubernetes/components/{cnpg,common,volsync,zeroscaler,gpu}/`. App ks.yaml's reference them via relative paths.
- `${SECRET_DOMAIN}`, `${NFS_ADDR}`, `${CLUSTER}` come from cluster-level postBuild substitution.
- Memory: set **explicit `requests.memory`** lower than `limits.memory`. Kubernetes defaults request=limit if request is omitted, which over-commits the scheduler. (Learned the hard way after `Cluster has overcommitted memory` alert.)

## Operations

- **Status**: `flux get all -A` ; `kubectl get events -A --sort-by=.lastTimestamp | tail`
- **Reconcile a thing**: `flux -n <ns> reconcile kustomization <name>` (use `--force` for `HelmRelease`)
- **Fetch latest git**: `flux -n flux-system reconcile source git flux-system`
- **App in trouble**: check `kubectl get hr -n <ns> <app>`, then pod logs, then events.
- **Mise/Taskfile**: `task` lists; tasks live under `.taskfiles/{ExternalSecrets,Flux,Kubernetes,sops,volsync}/`.
- **Stale pod blocking PVC**: usually `kubectl delete pod -n <ns> <pod>` and CNPG/whoever owns it will recreate. For wedged CNPG bootstrap, `kubectl delete pvc -l cnpg.io/cluster=<cluster>` and the operator re-bootstraps.

## Common pitfalls

- **Helm-managed config files persist** beyond chart values. Apps like Nextcloud write to `config.php` on the persistent volume during _initial install only_ — later `externalDatabase.host` changes in the HR are ignored. Override via the app's own `local.config.php` (or equivalent) instead of relying on Helm regenerating.
- **`spec.patches` on child Kustomizations doesn't stick** (see Gotcha above). Use a Component.
- **JSON Patch target name** in kustomize patches uses the _literal pre-substitution_ name. The Cluster's `metadata.name` is `postgres-${APP}` during kustomize, before Flux postBuild. Target by group+kind (and skip `name:`) to avoid this footgun.
- **`local-hostpath` is `WaitForFirstConsumer`**: PVCs stay Pending until a pod is scheduled. If the pod can't schedule (memory pressure, anti-affinity), the PVC also hangs.
- **Pod anti-affinity `required`** on CNPG instances forces one-per-node. If a node is full and the cluster has 3 instances, instance 3 will be unschedulable. Either soften to `preferred` per-app (`CNPG_ANTI_AFFINITY: preferred` substitute) or free memory.

## When in doubt

- Mirror conventions from existing apps under the same namespace.
- Reference `vrozaksen/home-ops` (vrozaksen) for vrozaksen's CNPG patterns; `joryirving/home-ops` (jory) for renovate/PR-review patterns. Both cloned at `~/Repositories/{jory,vrozaksen}` locally.
- Don't introduce a pattern just because it's elsewhere. Compare effort vs value before adopting.
