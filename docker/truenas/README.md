# TrueNAS (doco-cd)

Every `NN-name/docker-compose.yaml` here is a stack deployed on the NAS by
[doco-cd](https://github.com/kimdre/doco-cd), polled from `main` every 5 min.
Add a folder to deploy, delete it to remove. Per-stack secrets are Bitwarden
Secrets Manager IDs in the stack's `.doco-cd.yaml` (plain values only — doco-cd
can't read fields out of the JSON-per-app secrets).

doco-cd runs as two instances that update each other from Git:
`.doco-cd/compose.main.yaml` (deploys the stacks + the updater) and
`.doco-cd/compose.updater.yaml` (deploys main via `.doco-cd.updater.yaml`).

## Rebuild the NAS

1. Apps → Settings: choose the `ssd-storage` pool (starts Docker).
2. Create datasets `ssd-storage/docker/{doco-cd,plex,garage}`.
3. Create `/mnt/ssd-storage/docker/doco-cd/{data,updater,secrets}` and, in
   `secrets/`, `api_secret` + `webhook_secret` (`openssl rand -hex 32`) and
   `bws_token` (`fnox get BITWARDEN_KUBERNETES_TOKEN`). All `chmod 600`.
4. From a checkout of this repo on the NAS, start the updater once:
   `docker compose -f docker/truenas/.doco-cd/compose.updater.yaml up -d`.
   It deploys main doco-cd, which deploys everything else.

## Garage

Offsite copy = Cloud Sync task 3 on `/mnt/tank/backup/garage`:
`data/` (blocks), `snapshots/` (daily metadata snapshots) and `identity/`
(node key + layout; recopy from `/mnt/ssd-storage/docker/garage/meta` after
any layout change). The live metadata on the SSD is not synced on purpose.

**Restore with contents** (metadata lost, `data/` intact or restored):

1. Stop the stack, empty `/mnt/ssd-storage/docker/garage/meta`.
2. Copy `identity/*` into it, and the newest `snapshots/<date>/db.lmdb`
   as `meta/db.lmdb/data.mdb`.
3. Start the stack, then `docker exec garage /garage repair -a --yes blocks`.

**Fresh node** (buckets come back empty — existing Barman/Kopia backups are lost):
start the stack on empty `meta/` and `data/`, then run

```sh
mise run //docker/truenas:garage:bootstrap
```

It assigns the layout, imports the key consumers already use (BWS
`postgresql-bucket`) and creates the `postgresql` and `kopiur` buckets.
Safe to re-run: every step skips what already exists.
