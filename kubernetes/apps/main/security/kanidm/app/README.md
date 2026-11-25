---
area: "[[Homelab]]"
categories:
  - "[[Resources]]"
reviewed: 2026-11-24
summary: How Kanidm, the cluster's identity provider, is deployed, how apps get an OIDC client from it, and how to recover its admin accounts.
topics:
  - "[[Cluster]]"
created: 2026-07-06T16:56
---

# Kanidm

The cluster's identity provider, on `bjw-s/app-template` in namespace `security`.

- Host: `idm.${SECRET_DOMAIN}` on `envoy-external`.
- TLS: Kanidm serves only HTTPS. cert-manager `Certificate/idm` writes `idm-tls`, mounted at `/certs`. A `BackendTLSPolicy` makes Envoy re-encrypt to the backend and validate its certificate (`wellKnownCACertificates: System`).
- Storage: `/data` on the `kanidm` `ceph-block` PVC from the kopiur backup component (2Gi, hourly snapshots, restored automatically on a rebuild). `[online_backup]` in `server.toml` dumps to `/data/backups` every six hours, keeping 14, and the dumps ride along in each snapshot.
- Provisioning: [`kanidm-provision`](https://github.com/oddlama/kanidm-provision) runs as a second controller. It applies every ConfigMap in `security` labelled `kanidm_config: "1"` and writes each client's secret into the app's namespace. Groups (`users`, `admins`, `guests`) are in `provisioning/groups.yaml`.

## Give an app an OIDC client

Add a Component to the app's `ks.yaml`:

- `components/oidc`: a Kanidm OAuth2 client for an app that speaks OIDC itself.
- `components/oidc/envoy`: the same client, plus an Envoy `SecurityPolicy` that puts the login in front of the app's `HTTPRoute`, for an app with no login of its own.

The Component creates a Flux Kustomization `kanidm-${APP}-oidc` in `security`, which renders a ConfigMap of the same name for the provisioner. The provisioner writes the Secret `kanidm-${APP}-oidc` into `${APP_NAMESPACE}`, with the client id and secret under `client-id` and `client-secret` (`OIDC_CLIENT_ID_KEY`, `OIDC_CLIENT_SECRET_KEY` rename them). The issuer is `https://idm.${SECRET_DOMAIN}/oauth2/openid/${APP}`.

The app sets `APP_NAMESPACE` and the `OIDC_*` variables in `postBuild.substitute`. The usual ones are `OIDC_DISPLAY_NAME`, `OIDC_CALLBACK` (default `/oauth2/callback`), `OIDC_SHORT_USERNAME`, `OIDC_DISABLE_PKCE` for clients without PKCE, `OIDC_GROUP` (default `users`) and `OIDC_CLAIM_MAPS`; all of them, with defaults, are in [`components/oidc/base/ks.yaml`](../../../../../components/oidc/base/ks.yaml). Check the callback against the app's real redirect URL before enabling login.

Provisioning cannot set passwords; credentials are self-service.

## Add a person

A person in `users` with a credential can sign in to every client that maps `users`:

```sh
export KANIDM_URL="https://idm.${SECRET_DOMAIN}"
kanidm login --name idm_admin
kanidm person create <user> "<Display Name>" -D idm_admin
kanidm person update <user> --mail <user>@${SECRET_DOMAIN} -D idm_admin
kanidm group add-members users <user> -D idm_admin
kanidm person credential create-reset-token <user> -D idm_admin
```

Open the printed `/ui/reset?token=…` link to set a password or passkey. Apps that match accounts by email (RomM) need the same address there. The `kanidm` client comes from the root `.mise.toml` on macOS (`cargo:kanidm_tools`); the server image has none.

## Recover the admin accounts

Done once at the first deployment; repeat after losing the admin credentials.

```sh
kubectl exec -n security -it statefulset/kanidm -c app -- kanidmd recover-account admin
kubectl exec -n security -it statefulset/kanidm -c app -- kanidmd recover-account idm_admin
```

Each prints a `new_password` to log in with directly; it is not a `/ui/reset` token. `admin` manages system settings and OAuth2 clients, `idm_admin` people and groups.

If the provisioner's token is lost, create a new one and store it in the Bitwarden item `kanidm`, field `KANIDM_PROVISION_TOKEN`; `externalsecret.yaml` maps it into `kanidm-provision-token`:

```sh
kanidm service-account create kanidm-provision "Kanidm Provision" idm_admins -D idm_admin
kanidm group add-members idm_admins kanidm-provision -D idm_admin
kanidm service-account api-token generate --readwrite kanidm-provision provision-token -D idm_admin
```

## Design notes

- `server.toml` (ConfigMap at `/data/server.toml`) also trusts `X-Forwarded-For` from the pod network `10.42.0.0/16`, so audit logs and rate limits see the client, not the Envoy pod.
- `priorityClassName: system-cluster-critical` keeps the identity provider from eviction under memory pressure.
- The provisioner's ServiceAccount alone may create and patch Secrets and read ConfigMaps; the internet-facing server runs under a separate `kanidm` ServiceAccount with no rights.
- `/status` is public and unauthenticated; the probes use it.
- LDAP (`:3636`) is served but not routed outside the cluster; nothing uses it.
- Kanidm exposes no Prometheus metrics.
