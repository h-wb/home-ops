---
area: "[[Homelab]]"
categories:
  - "[[Resources]]"
reviewed: 2026-11-24
summary: How the NAS's Compose stacks are deployed from this repo, how to rebuild the NAS, and how to restore Garage.
topics:
  - "[[NAS]]"
created: 2026-09-26T12:37
---

# TrueNAS (doco-cd)

Every `NN-name/docker-compose.yaml` here is a stack deployed on the NAS by
[doco-cd](https://github.com/kimdre/doco-cd), polled from `main` every 5 min.
Add a folder to deploy, delete it to remove. Per-stack secrets are Bitwarden
Secrets Manager IDs in the stack's `.doco-cd.yaml` (plain values only — doco-cd
can't read fields out of the JSON-per-app secrets).

doco-cd (`.doco-cd/compose.main.yaml`) deploys the stacks and updates itself
(`SELF_UPDATE_ENABLED`). Keep it one container: a main and updater pair recreated
each other in the same poll and left both dead.

Stacks such as Plex, Garage and the exporters use `/mnt/ssd-storage/docker/<app>`
for app data rather than TrueNAS catalog apps. Do not add `# renovate:` comments to
Compose files: the built-in Compose manager already tracks their images, and the
generic regex manager would misparse `image:` lines.

## Rebuild the NAS

1. Apps → Settings: choose the `ssd-storage` pool (starts Docker). These steps were not checked against the NAS.
2. Create datasets `ssd-storage/docker/{doco-cd,plex,garage}`.
3. Create `/mnt/ssd-storage/docker/doco-cd/{data,secrets}` and, in
   `secrets/`, `api_secret` + `webhook_secret` (`openssl rand -hex 32`) and
   `bws_token` (`fnox get BITWARDEN_KUBERNETES_TOKEN`). All `chmod 600`.
4. From a checkout of this repo on the NAS, start doco-cd once:
   `docker compose -f docker/truenas/.doco-cd/compose.main.yaml up -d`.
   It deploys everything else, itself included from then on.

## Garage

The cluster reaches this S3 store at `garage.storage.svc`, a selector-less
Service with an EndpointSlice pointing to the NAS
([`kubernetes/apps/main/storage/garage`](../../kubernetes/apps/main/storage/garage/app/service.yaml)). The external endpoint is `s3.${SECRET_DOMAIN}`.
CNPG Barman and kopiur use separate buckets in the same store.

Offsite copy: Cloud Sync task 3 (not checked) on `/mnt/tank/backup/garage`:
`data/` (blocks), `snapshots/` (daily metadata snapshots) and `identity/`
(node key + layout; recopy from `/mnt/ssd-storage/docker/garage/meta` after
any layout change). The live metadata on the SSD is not synced on purpose.

### Restore with contents

Metadata lost, `data/` intact or restored:

1. Stop the stack, empty `/mnt/ssd-storage/docker/garage/meta`.
2. Copy `identity/*` into it, and the newest `snapshots/<date>/db.lmdb`
   as `meta/db.lmdb/data.mdb`.
3. Start the stack, then `docker exec garage /garage repair -a --yes blocks`.

### Fresh node

Buckets come back empty, and the Barman and Kopia backups in them are lost. Start the stack on empty `meta/` and `data/`, then run

```sh
mise run //docker/truenas:garage:bootstrap
```

Run it from a workstation: it reaches the NAS over ssh (`NAS_HOST`) and reads
Bitwarden through fnox. It assigns the layout, imports the key consumers already
use (BWS `postgresql-bucket`) and creates the `postgresql` and `kopiur` buckets.
Safe to re-run: every step skips what already exists.

### Miroir media

Screenshots and other files that warehouse rows point at. The same task creates the `miroir-media` bucket and imports a key that can read and
write that bucket only, once the BWS item `miroir` has
`MIROIR_MEDIA_ACCESS_KEY_ID` (`GK` + 24 hex characters) and
`MIROIR_MEDIA_SECRET_ACCESS_KEY` (64 hex characters):

```sh
printf 'GK%s\n' "$(openssl rand -hex 12)"   # key id
openssl rand -hex 32                        # secret
```

The Miroir server reads the same two fields from its environment
(`miroir-secret`). These objects are private screen captures, stored
unencrypted in `data/`, so they are in the offsite copy above; whether that copy
is encrypted is not checked here.
