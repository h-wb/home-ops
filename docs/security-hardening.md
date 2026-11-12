# Security hardening plan

Working document from the audit of 2026-11-12 (auth, exposure, privileges, supply
chain). Steps are ordered by what an attacker gains. Each pull request that works
on a step ticks its boxes here.

How the findings were checked: the repo at `main`, the main cluster through the
read-only ToolHive tools, GitHub settings through the API, and upstream docs or
source for every app setting named below. The edge cluster was read from the repo
only.

## Step 1: a write to `main` is admin on everything

Flux applies `main` to both clusters and doco-cd applies it to the NAS
(`docker/truenas`, with `docker.sock`). Three things make that write easier to get
than it should be:

- The agent pod and the ToolHive GitHub server use tokens of the repository
  admin. The `main-require-review` ruleset lets the admin role bypass it, so those
  tokens can push to `main`, edit the ruleset and change workflows.
- Any branch pushed to this repository can run a workflow on `home-ops-runner`,
  which holds a Talos `os:admin` credential (machine config, admin kubeconfig).
- kritika's approval counts as the one required review on any home-ops pull
  request, not only on Renovate's.

Tasks:

- [ ] Agents get their own GitHub identity with the Write role, not the admin's
      (agreed 2026-11-12, scheduled for later; a machine user is the plan).
- [ ] Its token cannot change workflows or settings (classic `repo` without
      `workflow`). Replace `GH_TOKEN` in the `paseo-general` item and
      `GITHUB_TOKEN` in the `toolhive` item, then revoke the old tokens.
- [ ] Ruleset: the admin bypass stays for the human only. Agent pull requests are
      approved by the human, which works once the author is no longer the admin.
- [ ] kritika approves only the Renovate bot's pull requests
      (`pr.bot && pr.author` in `review.approve.when`), so an agent cannot merge on
      an AI approval.
- [ ] dotfiles: protect `master` the same way (neko re-executes it at every
      session start).
- [x] Talos API access allows `os:operator` (`talos/main/machineconfig.yaml.j2`).
      Apply the machine config to the control planes before the next box.
- [x] Runner's Talos ServiceAccount drops from `os:admin` to `os:operator`.
      `ImageService/Pull` accepts it (Talos v1.14 `machined.go`). What is left:
      reboot, shutdown, service stop, etcd snapshot (encrypted by secretbox). Gone:
      machine config, kubeconfig, upgrade, reset.
- [ ] NAS: doco-cd gets its own Bitwarden machine account limited to the stack
      secrets. Today it holds the cluster's token.

Done when: a pull request from the agent identity cannot merge without the human's
review, cannot touch `.github/workflows`, and `talosctl kubeconfig` fails with the
runner's credential.

## Step 2: code-server

Internet-facing, `--auth none` behind the gateway login, with a kubeconfig mounted.

- [ ] Gate on `admins`, not `users` (`OIDC_GROUP`).
- [ ] Add the `auth-gate` gatus probe (also missing for obsidian and prefect).
- [ ] Decide: internal gateway only, or keep external.
- [ ] Find out what the kubeconfig may do and reduce it, or remove it.
- [ ] NetworkPolicy: only the gateway reaches the pod.

## Step 3: endpoints that skip the gateway login

`LoadBalancer` services answer on the LAN (two also on the tailnet) with no login.
Neither cluster has a Talos host firewall.

| Service                | Address             | Open                                             |
| ---------------------- | ------------------- | ------------------------------------------------ |
| `prometheus-lb`        | 192.168.1.205:9090  | queries, `enableAdminAPI`, remote-write receiver |
| `victoria-logs-lb`     | 192.168.1.206:9428  | all logs, read and insert                        |
| edge `alertmanager-lb` | 192.168.18.79:9093  | alerts and silences                              |
| edge home-assistant    | 192.168.18.77:12321 | code-server sidecar, `--auth none`               |
| edge mosquitto         | 192.168.18.78:1883  | `allow_anonymous true`                           |

- [ ] Prometheus: admin API off; limit the service to the edge sender
      (`loadBalancerSourceRanges` or a Cilium policy).
- [ ] VictoriaLogs and edge Alertmanager: same source limit.
- [ ] Edge home-assistant: take 12321 off the service. The pod is
      `hostNetwork`, so also bind code-server to localhost or give it a password.
- [ ] Mosquitto: password file, anonymous off.

Internal gateway, no login at all:

- [ ] qBittorrent (the pod CIDR is in `AuthSubnetWhitelist`, and Envoy is a pod),
      slskd (`SLSKD_NO_AUTH`), zigbee2mqtt, edge `hass-code`: add
      `components/oidc/envoy`. The arr apps and qui use the Services, not the routes.
- [ ] komf, multiscrobbler, garage-webui: no auth settings in the manifests; check
      and gate.

## Step 4: flat pod network

Only `llm`, `kritika`, the runner and the dragonfly instances have policies. Every
other pod reaches every Service, so the gateway login protects against outside
traffic only: code-server, the arr apps (`AUTH__METHOD: External`), Prometheus and
qBittorrent are open to any compromised pod.

- [ ] Ingress policy for the pods whose only auth is the gateway: from the
      gateway and their named in-cluster clients.
- [ ] Egress policy for internet-facing pods that run as root or unhardened
      (nextcloud, paperless, collabora, komga, neko).
- [ ] Consider bjw-s' label-driven clusterwide policies as the general shape.

## Step 5: supply chain

- [ ] Renovate: a global `minimumReleaseAge` (today only GitHub Actions wait).
- [ ] Digest-pin the remaining images (63 of 164 are pinned).
- [ ] Actions settings: default workflow permissions `read`, workflows may not
      approve pull requests, allowed actions limited to the ones in use.
- [ ] Pin `talosctl` in `image-pull.yaml` (`latest` on the runner that holds the
      Talos credential).

## Step 6: Pod Security

Admission is off (`disablePodSecurityPolicy: true`) and no namespace enforces a
level. 53 of 118 app-template containers set no `securityContext`.

| Could take `baseline` now                                                                                                          | Need exemptions or moves first                                                                                                            |
| ---------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| automation, default, media, security, games, kritika, database, cert-manager, external-secrets, flux-system, actions-runner-system | downloads (VPN sidecars), llm and observability (tailscale sidecars, exporters), network, storage, kube-system, rook-ceph, system-upgrade |

- [ ] Label the left column `enforce: baseline`, `warn: restricted`.
- [ ] Give the unhardened containers the usual block (non-root, no privilege
      escalation, drop ALL, read-only root where the app allows).
- [ ] Internet-facing and still root: nextcloud, paperless, komga, collabora, neko.

## Step 7: client address trust at the gateway

- [ ] `ClientTrafficPolicy`: `trustedCIDRs` (the pod CIDR, where cloudflared
      runs) instead of `numTrustedHops: 1`. Six of the reference repos do this.

## Step 8: kanidm as the only login

Where the web UI and the machine clients share `/api`, a gateway login with an
open `/api` route leaves the password endpoint exposed. Those apps get OIDC-only
login in the app. A route split is for apps whose machine paths are separate.

| App                                    | Today                             | Change                                                                                                                                    | Stays reachable without kanidm                                                            |
| -------------------------------------- | --------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| Kavita                                 | external, password only           | native OIDC, then "Disable Password Authentication" (UI)                                                                                  | OPDS `/api/opds/{key}`, Kobo `/kobo/{key}`, KOReader `/api/koreader/{key}` (auth keys)    |
| Karakeep                               | OIDC and password                 | `DISABLE_PASSWORD_AUTH`, `OAUTH_AUTO_REDIRECT`; drop `OAUTH_ALLOW_DANGEROUS_EMAIL_ACCOUNT_LINKING` once linked                            | Bearer API keys (test: the docs do not say whether the switch affects them)               |
| RomM                                   | OIDC and password                 | `DISABLE_USERPASS_LOGIN`; `OIDC_PROVIDER: generic`                                                                                        | client tokens and device pairing under `/api` (test Basic auth)                           |
| Immich                                 | password only in the repo         | OAuth and `passwordLogin.enabled: false` in the config file; no gateway login in front                                                    | mobile via `app.immich:///oauth-callback` or `/api/oauth/mobile-redirect`; `/share/<key>` |
| Paperless                              | password only                     | allauth OIDC, `PAPERLESS_DISABLE_REGULAR_LOGIN`, `PAPERLESS_REDIRECT_LOGIN_TO_SSO`; block `/admin/` on the external route                 | `/api/` tokens (the switch does not disable API password login)                           |
| Dawarich                               | password only                     | `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_ISSUER`, `ALLOW_EMAIL_PASSWORD_LOGIN=false` (read from master; confirm on the deployed tag) | trackers on `/api/v1/…` with `api_key`; `/s/:id`                                          |
| Komga                                  | OIDC and password, no off switch  | UI on the internal gateway; an external hostname with the machine paths only (as n8n does)                                                | `/opds/`, `/kobo/`, `/koreader`; `/api/` only for a remote reader app                     |
| Calibre-Web-Automated                  | internal, own login               | if it goes external: gateway login on the UI, sibling route for machines                                                                  | `/opds`, `/kobo/`, `/kosync`                                                              |
| konflate, kritika                      | whole UI external                 | external route for the webhook path only                                                                                                  | konflate `/hooks`; kritika's path to confirm                                              |
| Prometheus, VictoriaLogs, Alertmanager | gateway login, open on the LAN IP | step 3                                                                                                                                    | remote write and log ingest from edge                                                     |

No change planned: Plex, Overseerr, continuwuity (registration needs a token),
Garage S3, the gatus and kromgo status pages, the n8n and Flux webhooks, neko.
Nextcloud is not checked yet.

kanidm itself: 1.12 requires MFA for every person by default and the repo sets no
policy. Confirm the live policy, and that `guests` stays empty or view-only.

- [ ] One pull request per app, in the table's order.

## Step 9: secret scope

- [ ] One Bitwarden project behind one `ClusterSecretStore`: any namespace's
      `ExternalSecret` reads every secret. Split by project, or namespaced stores
      for the sensitive items.
- [ ] `kanidm-provision` can create and patch Secrets cluster-wide: a Role per
      client namespace (vrozaksen's shape).
- [ ] headlamp's `cluster-admin` ServiceAccount and the Flux MCP write role:
      keep, narrow or drop.

## Step 10: cleanup

- [ ] `default`: `debug-ssh` and three finished `node-debugger` pods.
- [ ] Namespaces `kube-tools` and `longhorn-system`; about 55 finished prefect
      flow pods in `automation`.
- [ ] Review the gitleaks history findings privately and confirm everything
      found is retired.

## Later, if wanted

Talos disk encryption (none of the reference repos has it), apiserver OIDC
through kanidm so kubeconfigs stop being long-lived admin certificates (vrozaksen),
a gateway-level default policy.

## Not verified

- The edge cluster's live state.
- What the code-server kubeconfig may do.
- qBittorrent without login, in a browser.
- kanidm's live account policy.
