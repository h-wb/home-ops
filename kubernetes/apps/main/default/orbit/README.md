# Orbit

Orbit runs on the main cluster at `https://orbit.${SECRET_DOMAIN}` (internal
gateway only). After the first rollout, get the one-time setup URL with
`kubectl -n default logs deployment/orbit | grep -F 'Initial setup URL'`.
Open it to create the root account and first workspace. Treat the URL as a
credential; do not share it in issues or logs. Open registration is disabled.

The `orbit` PVC holds the SQLite database, attachments, and local Orbit
backups. Kopiur snapshots the PVC hourly. Keep the SOPS age recovery key
available outside the cluster: restoring Orbit's encrypted backups requires
the original `ORBIT_APP_KEY` from `app/secret.sops.yaml`.
