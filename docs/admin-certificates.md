---
area: "[[Homelab]]"
categories:
  - "[[Resources]]"
reviewed: 2026-11-25
summary: Renews the one-year Talos and Kubernetes admin client certificates of a cluster, and how you are warned before they expire.
topics:
  - "[[Cluster]]"
created: 2026-11-25T03:30
---

# Renew the admin certificates

## When to use it

Entering home-ops in a shell with `mise activate` prints a warning when an admin certificate of `main` or `edge` expires within 30 days, or has expired:

```
expires  main  Dec  5 03:26:24 2026 GMT  kubernetes/clusters/main/kubeconfig
Admin certificates of main are due. Renew: CLUSTER=main mise run //talos:renew-certs (docs/admin-certificates.md)
```

`mise run //talos:certs` lists every certificate it finds with its expiry date. Both certificates last one year, the `talosctl` default, and nothing renews them:

| Certificate              | In this checkout                           | Other copies                                                                                                                                                                    |
| ------------------------ | ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Talos admin (`os:admin`) | `talos/<cluster>/talosconfig`              | None: each checkout generates its own from the PKI secrets                                                                                                                      |
| Kubernetes admin         | `kubernetes/clusters/<cluster>/kubeconfig` | The Proton Pass item `Machines/kubeconfig`, one field per cluster, which dotfiles renders to `~/.kube/<cluster>.yaml` on each workstation (MacBook, code-server, neko, CachyOS) |

The check reads this checkout's files and `~/.kube/<cluster>.yaml`. The Paseo pods hold none of them and reach the clusters through the tool gateway.

In-cluster jobs (the CI runner, tuppr, the Talos tool) do not use these files. Their Talos credentials come from Talos `ServiceAccount` resources: Talos issues a certificate valid for six hours into a Secret and replaces it about an hour before it expires. The CI runner and the Talos tool mount that Secret as a volume, without `subPath`, so they read the new one.

## Steps

On a workstation with a home-ops checkout, for each cluster that is due:

1. `CLUSTER=<cluster> mise run //talos:renew-certs`. It:
   - re-signs `talos/<cluster>/talosconfig` from the PKI secrets in Proton Pass (`//talos:gen-talosconfig`). This works after the old certificate has expired;
   - fetches a new admin kubeconfig through Talos into `kubernetes/clusters/<cluster>/kubeconfig` (`//bootstrap:kubeconfig`);
   - asks, then writes that kubeconfig to the field `<cluster>` of `Machines/kubeconfig` with `pass-cli item update`. The value passes on pass-cli's command line, so it shows in the process list while it runs. If the write fails, paste the file into that field in Proton Pass.
2. On each workstation, `mise run apply` in dotfiles, so `~/.kube/<cluster>.yaml` takes the new kubeconfig.
3. Another home-ops checkout warns on its own: run step 1 there too, and answer no to the Proton Pass write.

## Check it worked

`mise run //talos:certs` shows `ok` with a date a year away for every file of the cluster.
