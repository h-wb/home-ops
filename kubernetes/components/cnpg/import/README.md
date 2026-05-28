# CNPG Import Component

This component adds the `initdb.import` bootstrap method to a CNPG cluster — a fresh cluster that's seeded by `pg_dump | pg_restore` from a live external Postgres source. Used to migrate a database from one Postgres install to another (originally added for the CPGO → CNPG migration in this repo).

## What it does

Patches the cluster spec to add:

```yaml
spec:
  bootstrap:
    initdb:
      database: ${CNPG_DATABASE:=${APP}}
      owner: ${CNPG_USER:=${APP}}
      import:
        type: ${CNPG_IMPORT_TYPE:=microservice}
        databases:
          - ${CNPG_DATABASE:=${APP}}
        source:
          externalCluster: source
        pgDumpExtraOptions:
          - --exclude-extension=pg_stat_statements
          - --exclude-extension=pgaudit
          - --exclude-schema=pgbouncer
  externalClusters:
    - name: source
      connectionParameters:
        host: ${CNPG_IMPORT_HOST:=${APP}-primary}
        ...
```

## Usage

Automatically includes:

- `cnpg/base` — Cluster, ObjectStore, Pooler, ScheduledBackup, ExternalSecret

**Do NOT use with:**

- `cnpg/initdb` — uses plain `bootstrap.initdb` instead
- `cnpg/restore` — uses `bootstrap.recovery` from Barman archive

## When to pick this

- Migrating an app's DB from CPGO (or any other live Postgres) to CNPG. The new CNPG cluster pulls a logical dump of the source on first boot, then runs alongside the source until the app is cut over.
- After the migration is complete and the first Barman backup has landed, the consuming app should switch its `components` reference to `cnpg/restore` so a torn-down cluster rebuilds from the backup instead of trying to re-import from a source that may no longer exist.

## Variables

- `CNPG_DATABASE` — Database name (default: `${APP}`)
- `CNPG_USER` — Database owner username (default: `${APP}`)
- `CNPG_IMPORT_TYPE` — Import type, `microservice` (single DB) or `monolith` (multi-DB) (default: `microservice`)
- `CNPG_IMPORT_HOST` — Source Postgres service hostname (default: `${APP}-primary` — the CPGO primary svc)
- `CNPG_IMPORT_USER` — User to connect to the source as (default: `postgres`)
- `CNPG_IMPORT_DBNAME` — DB to connect to on the source for the dump (default: `postgres`)
- `CNPG_IMPORT_PASSWORD_SECRET` — Secret containing the source password (default: `${APP}-pguser-postgres` — CPGO's auto-generated superuser secret)

## Excluded from the dump

Things in the CPGO source that would break or be irrelevant on the CNPG destination:

- Extension `pg_stat_statements` — Crunchy preloads this; on CNPG it's not in `shared_preload_libraries` by default
- Extension `pgaudit` — Crunchy-only
- Schema `pgbouncer` — CPGO's PgBouncer auth schema, irrelevant on CNPG

## Generated resources

CNPG creates:

- Database user with secure random password
- Database owned by that user, populated by `pg_dump | pg_restore` from the source
- Secret `postgres-${APP}-app` with connection credentials

## Stale-data warning

The import is a one-shot snapshot at cluster bootstrap. Any writes made to the source between the import completing and the app being cut over to the new CNPG cluster are **not** in CNPG. For a clean cutover, either freeze writes to the source before importing, or re-bootstrap the CNPG cluster (delete the `Cluster` CR + PVCs and let Flux recreate) right before flipping the app's DB URL.
