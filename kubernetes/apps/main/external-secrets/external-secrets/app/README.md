---
area: "[[Homelab]]"
categories:
  - "[[Resources]]"
reviewed: 2026-11-24
summary: How an app turns a Bitwarden Secrets Manager item into a Kubernetes Secret, and which local tools hold the bootstrap secrets.
topics:
  - "[[Cluster]]"
created: 2025-06-08T21:28
---

# External Secrets

External Secrets Operator syncs Bitwarden Secrets Manager items into Kubernetes Secrets through the ClusterSecretStore `bitwarden-secrets-manager` (`clustersecretstore.yaml`). An app's ExternalSecret usually lives in its `app/externalsecret.yaml` and names a Bitwarden item by its key. Most items hold JSON (`{"KEY1": "value1", "KEY2": "value2"}`), or `key: value` lines.

## Every field of an item

```yaml
---
# yaml-language-server: $schema=https://k8s-schemas.home-operations.com/external-secrets.io/externalsecret_v1.json
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: &name myapp-secret
spec:
  secretStoreRef:
    kind: ClusterSecretStore
    name: bitwarden-secrets-manager
  refreshInterval: 15m
  target:
    name: *name
  dataFrom:
    - extract:
        key: myapp
```

## Selected fields, renamed

```yaml
spec:
  secretStoreRef:
    kind: ClusterSecretStore
    name: bitwarden-secrets-manager
  target:
    name: myapp-secret
    template:
      engineVersion: v2
      data:
        DB_PASSWORD: "{{ .KEY1 }}"
        API_KEY: "{{ .KEY2 }}"
  dataFrom:
    - extract:
        key: myapp
```

The whole item as one value, without parsing it: `data: [{secretKey: env, remoteRef: {key: myapp}}]` instead of `dataFrom`.

## Bootstrap and local secret tools

SOPS uses the locally managed root `age.key`; never commit it. `mise run encrypt` and `mise run decrypt` handle `*.sops.yaml`. Bootstrap inputs (the Bitwarden machine token, Talos CAs and the age key) come from Proton Pass via [`fnox.toml`](../../../../../../fnox.toml) so they are available while the cluster is down.

Install or update dotfiles first: `mise run pass:login` extends its global `proton-login` task template, and secret-consuming tasks depend on login. This repo uses a separate pass-cli/fnox session (`PROTON_PASS_SESSION_DIR` in [`.mise.toml`](../../../../../../.mise.toml)). On macOS the `home-ops` agent token is read from the `pass-cli-home-ops` Keychain item and needs viewer access to the `Machines` vault (not checked). When that token expires (2027-10, not checked), run `pass-cli agent renew` outside the repo, then `mise run pass:login` inside it. On Linux in the workshop pod, login reads `PROTON_PASS_TOKEN`; that token has no `Machines` grant, so bootstrap and Talos tasks fail there by design.

For manual Bitwarden CLI use, run `mise run //docker/truenas:bws -- <args>`. The task reads `BWS_ACCESS_TOKEN` through fnox from the `Machines/bws-cli` Proton Pass item. Never put the token in `.mise.local.toml`.
