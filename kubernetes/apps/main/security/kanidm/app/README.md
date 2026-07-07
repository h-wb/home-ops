# Kanidm

Cluster identity provider — **replaced Authentik**. Built on `bjw-s/app-template` and adapted to
home-ops conventions (Bitwarden Secrets Manager, Envoy Gateway, cert-manager, ceph-block).

- **Host:** `idm.${SECRET_DOMAIN}` via `envoy-external`.
- **TLS:** Kanidm terminates its own TLS (mandatory — it won't serve plaintext). cert-manager
  `Certificate/idm` → secret `idm-tls` mounted at `/certs`. A `BackendTLSPolicy` makes Envoy
  **re-encrypt** to the HTTPS backend and validate the LE cert (`wellKnownCACertificates: System`).
- **Storage:** `/data` on a `ceph-block` PVC (app-template VolumeClaimTemplate, 2Gi). Backups are
  handled in-app (`[online_backup]` in `server.toml`), not Volsync.
- **Provisioning:** `m00nwtchr/kanidm-provision` runs as a second controller — declarative groups
  and OAuth2 clients from ConfigMaps labelled `kanidm_config: "1"`, writing generated client
  secrets back into the target namespace. Shipped at `replicas: 0` until the token existed; now `1`.

## Bootstrap (one-time — already done; kept for disaster recovery)

### 1. Recover the built-in admin accounts

```sh
kubectl exec -n security -it statefulset/kanidm -c app -- kanidmd recover-account admin
kubectl exec -n security -it statefulset/kanidm -c app -- kanidmd recover-account idm_admin
```

Each prints a `new_password`. **This is a password to LOG IN with, not a `/ui/reset` token** — use
it directly. (`/ui/reset` only accepts credential-reset tokens from
`kanidm person credential create-reset-token`, used later for personal accounts / passkeys.)

- `admin` — manages system config and OAuth2 resource servers.
- `idm_admin` — manages people and groups (day-to-day identity admin).

The kanidm **client** CLI (`brew install kanidm`, separate from the distroless server image) needs a
server URL on every call. Set it once so the cached login token persists:

```sh
export KANIDM_URL="https://idm.${SECRET_DOMAIN}"
kanidm login --name idm_admin        # paste the idm_admin new_password
```

### 2. Create the provision service account + token

```sh
kanidm service-account create kanidm-provision "Kanidm Provision" idm_admins -D idm_admin
kanidm group add-members idm_admins kanidm-provision -D idm_admin
kanidm service-account api-token generate --readwrite kanidm-provision provision-token -D idm_admin
```

Store the printed token in **Bitwarden Secrets Manager** under key `kanidm`, field
`KANIDM_PROVISION_TOKEN`. `externalsecret.yaml` (store `bitwarden-secrets-manager`) maps it into
secret `kanidm-provision-token`. Then set `controllers.provision.replicas: 1` in `helmrelease.yaml`.

## Day-2: managing groups and OAuth2 clients

Once the provision controller is running, **manage everything declaratively** — don't use the CLI.
Add a ConfigMap under `provisioning/` labelled `kanidm_config: "1"`:

- `provisioning/groups.yaml` — base groups (`users`, `admins`).
- `provisioning/oauth2.yaml` — OAuth2 clients. One ConfigMap **per target namespace**
  (`data.targetNamespace` is ConfigMap-level, not per-client — the provisioner overwrites any
  per-client value, so split by namespace). For each client the provisioner writes secret
  `kanidm-<name>-oidc` into that namespace with the keys named by `k8s.clientIdKey` /
  `k8s.clientSecretKey`; the app consumes it via `envFrom`.

Current clients: **`romm`** (media ns) — `OIDC_CLIENT_ID`/`OIDC_CLIENT_SECRET` → `kanidm-romm-oidc`.
RomM has no PKCE, so the client sets `allowInsecureClientDisablePkce: true`; RomM's env uses
`OIDC_PROVIDER: pocket-id` (closest standards-pure analog — no kanidm option exists) and userpass
login stays enabled as a fallback. See the [oddlama/kanidm-provision state schema][schema] for all
fields.

Provisioning **cannot set user passwords** (credentials are self-service by design). See below.

## Creating a personal login (to actually sign in via OIDC)

An app OIDC client is not a user — you need a person in the `users` group (the group RomM's scope
map grants) with a credential. The admin creates the person; the user sets their own password:

```sh
kanidm person create <user> "<Display Name>" -D idm_admin
kanidm person update <user> --mail <user>@${SECRET_DOMAIN} -D idm_admin   # must match RomM email
kanidm group add-members users <user> -D idm_admin
kanidm person credential create-reset-token <user> -D idm_admin          # → /ui/reset?token=… link
```

Open the printed reset link in a browser to set a password / passkey. That credential is what you
use at RomM's "Login with OIDC" button. The email must match the account in RomM.

## Design notes

- **`server.toml`** (ConfigMap → `/data/server.toml`, the image's default path) enables what env
  vars can't:
  - `[online_backup]` — SQLite-consistent dumps to `/data/backups` every 6h, keep 14.
  - `[http_client_address_info]` — trusts `X-Forwarded-For` from the pod CIDR (`10.42.0.0/16`,
    Cilium native routing) so audit logs / rate-limiting see the real client IP, not the Envoy pod.
- **`priorityClassName: system-cluster-critical`** — protects the IdP from eviction under memory
  pressure. (No control-plane pinning / netpol here, unlike the reference — kept minimal to match
  repo convention; control-planes are already schedulable.)
- **RBAC** (secrets create/patch, configmaps read) is scoped to the `provision` ServiceAccount
  only; the internet-facing server pod uses a separate powerless `kanidm` SA.
- **`/status`** is a public, unauthenticated health endpoint (used by the probes).
- **LDAP** (`:3636`) is served but not routed externally — no consumers yet.
- **No metrics/OTEL** — Kanidm exposes no Prometheus `/metrics`; OTLP would need a collector we
  don't run.

## References

- Deploy + cutover PRs: #3605 (deploy), #3607 (enable provision), #3608 (romm OIDC + remove authentik).
- Verify each client's redirect URL against the app's real callback before enabling it.

[schema]: https://github.com/oddlama/kanidm-provision#state-schema
