---
area: "[[Homelab]]"
categories:
  - "[[Resources]]"
reviewed: 2026-11-24
summary: The CNPG bootstrap Component that creates an empty database for a new app, to be replaced by restore after the first backup.
topics:
  - "[[Cluster]]"
created: 2026-05-28T19:17
---

# CNPG initdb Component

Adds `bootstrap.initdb` to the `Cluster` from [`base`](../README.md): an empty database `${CNPG_DATABASE:=${APP}}` owned by `${CNPG_USER:=${APP}}`, with a generated password in `postgres-${APP}-app`. It sets `cnpg.io/skipEmptyWalArchiveCheck` because the backup path may already hold WAL from an earlier cluster of the same name.

Use it for a brand-new app with no data and no backup to recover from. Once the first backup has completed, switch the app's `ks.yaml` to `cnpg/restore`; if the `Cluster` is ever recreated while `initdb` is still referenced, it comes back empty. Reference `extensions/postgis` after this Component if the app needs PostGIS.

Do not use it together with `restore`. Variables, connection and backups: [CNPG Components](../README.md).
