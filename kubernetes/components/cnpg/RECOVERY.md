---
area: "[[Homelab]]"
categories:
  - "[[Resources]]"
reviewed: 2026-11-24
summary: Recovers one app's CNPG database to a point in time from its Barman backup, then returns it to normal restore.
topics:
  - "[[Cluster]]"
created: 2026-05-28T19:17
---

# Recover a CNPG database to a point in time

## When to use it

Data was deleted or a migration went wrong, and the database must go back to a moment before it. To get back the latest state after losing the `Cluster`, nothing is needed: an app on `cnpg/restore` recovers from the latest backup when Flux recreates it ([CNPG Components](README.md)).

The app must be on `cnpg/restore`, and a completed base backup must exist from before the target, with WAL archived up to it. Backups are daily and kept 30 days.

Recovery replaces the database: the app is down from step 3, and everything written after the target is lost. Run the commands from a workstation; examples use `myapp` in namespace `default`.

## Steps

1. Pick the target: a time (RFC 3339, with zone) before the incident, from the app's logs or `kubectl -n default logs postgres-myapp-1`. A named restore point, an LSN or a transaction id also work. List the backups:

   ```bash
   kubectl -n default get backup -l cnpg.io/cluster=postgres-myapp
   ```

2. Add a temporary Component in the app directory, `kubernetes/apps/main/default/myapp/pitr/kustomization.yaml`, and reference it in `ks.yaml` after `cnpg/restore`. It has to be a Component: the patches of `cluster-apps` replace any `spec.patches` in a child `ks.yaml`.

   ```yaml
   apiVersion: kustomize.config.k8s.io/v1alpha1
   kind: Component
   patches:
     - target:
         group: postgresql.cnpg.io
         kind: Cluster
       patch: |-
         - op: add
           path: /spec/bootstrap/recovery/recoveryTarget
           value:
             targetTime: "2026-11-20T14:30:00+01:00"
   ```

   ```yaml
   components:
     - ../../../../../components/cnpg/restore
     - ./pitr
   ```

   Other targets in `recoveryTarget`: `targetName` (from `pg_create_restore_point`), `targetLSN`, `targetXID`, `targetImmediate: true` (end of the base backup), `targetTLI`. With `targetName` or `targetXID`, also set `backupID` to a backup taken before the target.

3. Stop Flux from recreating the old database, then delete it. Deleting the `Cluster` deletes its PVCs; the backups stay in the object store.

   ```bash
   flux -n default suspend kustomization myapp
   kubectl -n default delete cluster postgres-myapp
   ```

4. Push the change, then resume. Flux creates the `Cluster` with the recovery target.

   ```bash
   flux -n flux-system reconcile source git flux-system
   flux -n default resume kustomization myapp
   kubectl -n default get cluster postgres-myapp -w
   ```

5. Remove `./pitr` from `ks.yaml`, delete the directory and push. The running database is not touched; the next recreation recovers the latest backup again instead of going back to the old target.

## Check it worked

- `kubectl -n default get cluster postgres-myapp` shows `Cluster in healthy state`.
- The logs of `postgres-myapp-1` show `starting point-in-time recovery to` the target and `archive recovery complete`.
- The data the incident removed is back: query it with `kubectl -n default exec postgres-myapp-1 -- psql -U postgres -d myapp`.
- A new backup completes the next day, on the new timeline.

## If it fails

- `no target backup found`: no completed backup is older than the target. Pick a later target.
- Recovery waits for WAL: the target is past the last archived WAL.
- `requested timeline N is not a child of this server's history`: an earlier recovery forked the timeline. Set `targetTLI` to the timeline the backup was taken on (from the error, or the `*.history` files under `s3://postgresql/myapp`).
- Before a risky migration, create a restore point to recover to: `kubectl -n default exec postgres-myapp-1 -- psql -U postgres -c "SELECT pg_create_restore_point('before-migration');"`.

Reference: [CloudNativePG recovery](https://cloudnative-pg.io/documentation/current/recovery/).
