# CNPG Initdb Component

This component adds the `initdb` bootstrap method to a CNPG cluster — a fresh, empty database.

## What it does

Patches the cluster spec to add:

```yaml
spec:
  bootstrap:
    initdb:
      database: ${CNPG_DATABASE:=${APP}}
      owner: ${CNPG_USER:=${APP}}
```

## Usage

Automatically includes:

- `cnpg/base` — Cluster, ObjectStore, Pooler, ScheduledBackup, ExternalSecret

**Do NOT use with:**

- `cnpg/restore` — uses `bootstrap.recovery` instead
- `cnpg/import` — uses `bootstrap.initdb.import` instead

## When to pick this

- Brand-new app with no existing database to import from and no Barman backup to recover from.
- Once the first daily backup has landed, switch to `cnpg/restore` so that a torn-down cluster rebuilds from the backup instead of coming back empty.

## Variables

- `CNPG_DATABASE` — Database name (default: `${APP}`)
- `CNPG_USER` — Database owner username (default: `${APP}`)

## Generated resources

CNPG automatically creates:

- Database user with secure random password
- Database owned by that user
- Secret `postgres-${APP}-app` with connection credentials (keys: `uri`, `jdbc-uri`, `username`, `password`, `host`, `port`, `dbname`, `pgpass`)
