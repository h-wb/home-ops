---
area: "[[Homelab]]"
categories:
  - "[[Resources]]"
summary: Shows how to source a whole Bitwarden secret or selected fields into a Kubernetes Secret and describes the local bootstrap tools.
topics:
  - "[[Cluster]]"
created: 2025-06-08T21:28
---

## Standalone

#### This one will use whole "secret" as secret.

```yaml
---
# yaml-language-server: $schema=https://k8s-schemas.home-operations.com/external-secrets.io/externalsecret_v1.json
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: &name app-secret
spec:
  secretStoreRef:
    name: bitwarden-store
    kind: ClusterSecretStore
  refreshInterval: 15m
  target:
    name: *name
  data:
    - secretKey: env
      remoteRef:
        key: bitwarden_name
```

## Template

#### This one can use one of these:

```yaml
key1: value1
key2: value2
```

```json
{
  "key1": "value1",
  "key2": "value2"
}
```

```yaml
---
# yaml-language-server: $schema=https://k8s-schemas.home-operations.com/external-secrets.io/externalsecret_v1.json
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: &name app-secret
spec:
  secretStoreRef:
    name: bitwarden
    kind: ClusterSecretStore
  target:
    name: *name
    template:
      data:
        env1: "{{ .key1 }}"
        env2: "{{ .key2 }}"
  dataFrom:
    - extract:
        key: bitwarden_name
```

[Source](https://github.com/vrozaksen/home-ops/blob/main/kubernetes/apps/external-secrets/store/README.md)

## Bootstrap and local secret tools

App ExternalSecrets usually live in `app/externalsecret.yaml` and extract a Bitwarden Secrets Manager item by name. The `bitwarden-secrets-manager` ClusterSecretStore uses Bitwarden, not 1Password.

SOPS uses the locally managed root `age.key`; never commit it. `mise run encrypt` and `mise run decrypt` handle `*.sops.yaml`. Bootstrap inputs (the Bitwarden machine token, Talos CAs and the age key) come from Proton Pass via [`fnox.toml`](../../../../../../fnox.toml) so they are available while the cluster is down.

Install or update dotfiles first: `mise run pass:login` extends its global `proton-login` task template, and secret-consuming tasks depend on login. This repo uses a separate pass-cli/fnox session (`PROTON_PASS_SESSION_DIR` in [`.mise.toml`](../../../../../../.mise.toml)). On macOS the `home-ops` agent token is read from the `pass-cli-home-ops` Keychain item and needs viewer access to the `Machines` vault. When that token expires (2027-10), run `pass-cli agent renew` outside the repo, then `mise run pass:login` inside it. On Linux in the workshop pod, login reads `PROTON_PASS_TOKEN`; that token has no `Machines` grant, so bootstrap and Talos tasks fail there by design.

For manual Bitwarden CLI use, run `mise run //docker/truenas:bws -- <args>`. The task reads `BWS_ACCESS_TOKEN` through fnox from the `Machines/bws-cli` Proton Pass item. Never put the token in `.mise.local.toml`.
