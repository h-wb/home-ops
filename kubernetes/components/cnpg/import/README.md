---
area: "[[Homelab]]"
categories:
  - "[[Resources]]"
reviewed: 2026-11-24
summary: The CNPG bootstrap Component that seeds a new database with a logical dump of a live PostgreSQL, to move an app onto CNPG.
topics:
  - "[[Cluster]]"
created: 2026-05-28T19:17
---

# CNPG import Component

Adds `bootstrap.initdb.import` to the `Cluster` from [`base`](../README.md): on first boot CloudNativePG runs `pg_dump | pg_restore` from an external cluster named `source`, then the new database runs on its own. No app uses it today; it moved the apps off CrunchyData PGO in 2026-05.

## Variables

| Variable                      | Default                  | Holds                                            |
| ----------------------------- | ------------------------ | ------------------------------------------------ |
| `CNPG_IMPORT_HOST`            | `${APP}-primary`         | Source host                                      |
| `CNPG_IMPORT_USER`            | `postgres`               | Source user                                      |
| `CNPG_IMPORT_DBNAME`          | `postgres`               | Database to connect to on the source             |
| `CNPG_IMPORT_PASSWORD_SECRET` | `${APP}-pguser-postgres` | Secret with the source password under `password` |
| `CNPG_IMPORT_TYPE`            | `microservice`           | `monolith` to import several databases and roles |

The defaults are the service and Secret names CrunchyData PGO generated; set all of them for any other source. `CNPG_DATABASE` and `CNPG_USER` name the database that is imported and created.

The dump excludes the `pg_stat_statements` and `pgaudit` extensions and the `pgbouncer` schema, which a CrunchyData source carries and CloudNativePG does not load.

## Cut over

1. Stop writes to the source, or be ready to re-import: the import is a snapshot at bootstrap, and later writes to the source are not copied.
2. Deploy with `cnpg/import` and wait for the `Cluster` to be ready.
3. Point the app at `postgres-${APP}-app`.
4. When the first backup has completed, switch the app to `cnpg/restore`, so a recreated `Cluster` does not try to import from a source that is gone.

To import again before the cut-over, delete the `Cluster` and its PVCs and let Flux recreate them.
