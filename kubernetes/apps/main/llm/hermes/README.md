# Hermes: the assistant

The assistant of the [design](../DESIGN.md), running as `hermes-private-0` in
`llm`. It talks through Telegram and iMessage, uses its private LiteLLM key,
and acts through the assistant's ToolHive gateway. The surrounding services
and data scopes are described in [Models, tools and memory](../README.md).

This page describes the configuration in Git. The BlueBubbles connection needs
the values and one-time registration below before it can be used.

## Where things live

| Path                           | What it holds                                              |
| ------------------------------ | ---------------------------------------------------------- |
| `ks.yaml`                      | The assistant's Flux Kustomization                         |
| `app/config.yaml`              | Models, tools, approvals and messaging behaviour           |
| `app/helmrelease.yaml`         | The pod, its mounts and the public iMessage callback       |
| `app/externalsecret.yaml`      | Messaging and workshop credentials from Bitwarden          |
| `app/networkpolicy.yaml`       | The pod's allowed connections                              |
| `app/bluebubbles-network.yaml` | A child Flux Kustomization for BlueBubbles egress          |
| `bluebubbles/`                 | The egress policy, with app-specific hostname substitution |
| `app/SOUL.md`, `app/routines/` | Standing instructions and scheduled routines               |

The managed config is mounted read-only at `/etc/hermes`. The assistant keeps
its own state on the data volume; it cannot rewrite the managed configuration.

## Messaging

Telegram uses long polling: the assistant calls Telegram and needs no inbound
connection. Scheduled routines still deliver there.

iMessage uses BlueBubbles on the MacBook in Toronto. There are two connections,
both over public HTTPS; neither needs WireGuard or Tailscale:

```text
iMessage -> BlueBubbles on the Mac -> public callback -> Hermes in France
Hermes -> BlueBubbles server URL -> Messages on the Mac -> iMessage
```

Only `POST /bluebubbles-webhook` on `hermes.${SECRET_DOMAIN}` reaches the pod,
through `envoy-external` to port 8645. Other paths and methods are not routed.
The pod accepts that port only from the external gateway's pods. Outbound
BlueBubbles traffic is limited to its configured hostname on TCP 443.

The allowed-sender list decides who can use the assistant. Other senders get
no reply or pairing code. Group chats also require a Hermes mention. Read
receipts are off, so the assistant does not mark the Mac's conversations read.

### Credentials

All BlueBubbles values belong to the existing Bitwarden Secrets Manager item
`hermes` (JSON). Leave its Telegram fields in place.

| Field                       | Value                                                         |
| --------------------------- | ------------------------------------------------------------- |
| `BLUEBUBBLES_SERVER_URL`    | The stable public HTTPS server URL, on port 443               |
| `BLUEBUBBLES_PASSWORD`      | The BlueBubbles Server API password                           |
| `BLUEBUBBLES_ALLOWED_USERS` | Allowed sender emails or E.164 phone numbers, comma-separated |

Only these three fields are needed: the egress hostname is derived from the
server URL automatically (lowercased, `:443` stripped). The URL must be a bare
`https://<hostname>[:443][/]` - no userinfo, query, fragment, other port, IP or
wildcard. Unsupported URLs derive `bluebubbles.invalid`, leaving the network
policy closed; the adapter may still report connection errors. The server URL
must not require an interactive Cloudflare Access login.

External Secrets writes two Secrets. `hermes-bluebubbles` holds the URL,
password and sender list; an empty sender list withholds the URL so the adapter
stays off. `hermes-bluebubbles-network` holds only the hostname, derived from
the server URL by the ExternalSecret template. The
child Flux Kustomization substitutes it into the egress policy; the pod uses it
to bypass its closed outbound proxy. No field is added to `CLUSTER_SECRETS`.

Until the URL is valid, the policy uses `bluebubbles.invalid` and admits no
BlueBubbles traffic. Missing BlueBubbles credentials do not block Telegram.
Values stay out of Git, but the hostname is visible in the live policy and pod
environment.

The separate hostname Secret keeps passwords out of Flux's substitution input.
Only the egress policy needs the child Kustomization: the cluster's parent
overwrites substitution sources on app-level Kustomizations. The rest of
Hermes stays under its existing Kustomization.

### Register the callback

Keep the Mac awake and online, with BlueBubbles running and Messages signed
in. A background or fast-switched macOS user needs the BlueBubbles Private API
helper for reliable sending. Hermes ignores messages marked `isFromMe`, so
test from a different Apple ID.

Before registering the real password, verify the deployed route and log filter:
an unauthenticated POST to `/bluebubbles-webhook` must return 401, other paths
and a GET must return 404, and a test callback query must not appear in Envoy's
access log. A 503 means the adapter or backend is not ready, not that the
authentication check passed.

Hermes v0.23.1 cannot advertise a public HTTPS callback, so the manual webhook
below is a temporary workaround. Revisit it when a Hermes release supports a
separate public callback URL; no monkeypatch or proxy is used. Register **one**
webhook in BlueBubbles Server > Settings > API > Webhooks:

| Setting | Value                                                                         |
| ------- | ----------------------------------------------------------------------------- |
| URL     | `https://hermes.<domain>/bluebubbles-webhook?password=<URL-encoded password>` |
| Events  | `new-message` only                                                            |

Encode the password locally without putting it in shell history:

```sh
python3 -c 'import getpass, urllib.parse; print(urllib.parse.quote(getpass.getpass("BlueBubbles password: "), safe=""))'
```

The output is a credential too. Use it only in BlueBubbles, then clear it from
the terminal and clipboard. Do not add the HTTPS entry twice or subscribe it
to `updated-message`; either can cause duplicate replies.

Hermes also creates a `http://localhost:8645` webhook on the BlueBubbles server.
That address reaches the Mac, not France. Hermes reuses it on restart and
removes only that entry on clean shutdown; the manual HTTPS entry remains.
Do not run another listener on the Mac's port 8645: it would receive those
local deliveries, including the password.

### Check the connection

Send a message from an allowed address on a different Apple ID. Expect one
reply, no read receipt, and Telegram unchanged. A connection log or webhook
registration alone does not prove incoming messages reach Hermes.

If it fails, check the two directions separately: Hermes must reach the
BlueBubbles server URL, and the Mac must reach the public callback. Compare
the URL's hostname with the generated Secret's `BLUEBUBBLES_HOST`, then check
the ExternalSecrets, the `hermes-bluebubbles-network` Flux Kustomization and
gateway route status.

## Trust boundary

The BlueBubbles webhook API authenticates with the server password in a query
parameter. Hermes disables its callback access log; Envoy excludes the exact
callback path from its access log. Confirm that exclusion before using the
real password.

HTTPS does not hide the URL from a TLS terminator. Cloudflare can see the
callback password, as can trusted cluster administrators inspecting secrets
or traffic. Keeping values out of Git and access logs does not remove that
trust requirement.
