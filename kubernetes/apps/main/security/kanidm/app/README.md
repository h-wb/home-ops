# Kanidm

Lightweight OIDC + LDAP identity provider, deployed alongside Authentik during migration
(parallel-then-remove). Served on `idm.${SECRET_DOMAIN}`.

- Kanidm terminates TLS itself → dedicated cert (`certificate.yaml`) mounted in-pod, and a
  `BackendTLSPolicy` makes envoy re-encrypt/validate to the 8443 backend.
- `provision` (kanidm-provision) reconciles groups/OIDC clients from ConfigMaps labeled
  `kanidm_config: "1"`, and writes generated client secrets back into the target namespace.

## First-boot bootstrap (one-time, manual)

The provisioning token can't exist before the DB does, so `provision` ships at `replicas: 0`.

1. Merge this app; wait for the `kanidm` StatefulSet pod to be Running (`/status` probe green).
2. Recover admin accounts:
   ```sh
   kubectl -n security exec -it sts/kanidm -c app -- kanidmd recover-account admin
   kubectl -n security exec -it sts/kanidm -c app -- kanidmd recover-account idm_admin
   ```
3. With the kanidm CLI (login as `idm_admin`), create a service account + API token for provisioning:
   ```sh
   kanidm service-account create provision "Provisioning" --name idm_admin
   kanidm service-account api-token generate provision provision --rw --name idm_admin
   ```
4. Store the printed token in Bitwarden Secrets Manager under key `kanidm`, field
   `KANIDM_PROVISION_TOKEN` (the `externalsecret.yaml` maps it to secret `kanidm-provision-token`).
5. Scale up provisioning: set `controllers.provision.replicas: 1` in `helmrelease.yaml`.

## PR 2 (cutover, follow-up)

- Uncomment `provisioning/oauth2.yaml` (+ its line in `kustomization.yaml`), fill romm's real OIDC
  redirect URI, and enable romm's native OIDC (`OIDC_*` in `../../media/romm/app/externalsecret.yaml`).
- Delete `../../media/romm/app/securitypolicy.yaml` (authentik forward-auth).
- Remove the `authentik` app and its `./authentik/ks.yaml` entry from the security kustomization.

## Verification

```sh
kubectl -n security get certificate idm-tls            # Ready=True
kubectl -n security get sts kanidm                     # 1/1
curl -sf https://idm.${SECRET_DOMAIN}/status           # 200 through the gateway (re-encrypt path)
```
