# Hermes: the assistant

The assistant of the [design](../DESIGN.md), running as `hermes-private-0` in
`llm`. Surrounding services and data scopes are in
[Models, tools and memory](../README.md).

| Path                           | What it holds                                     |
| ------------------------------ | ------------------------------------------------- |
| `app/config.yaml`              | Models, tools, approvals, dashboard; read-only    |
| `app/helmrelease.yaml`         | The pod, its messaging settings and the dashboard |
| `app/externalsecret.yaml`      | Messaging, dashboard and workshop credentials     |
| `app/networkpolicy.yaml`       | What the pod may reach, and who may reach it      |
| `app/SOUL.md`, `app/routines/` | Standing instructions and scheduled routines      |

## Messaging

- **Telegram**: long polling; nothing connects in. Routines deliver here for now.
- **Matrix**: the bot `@hermes:matrix.<domain>` on our own homeserver,
  [Continuwuity](../../default/continuwuity/) in `default`, reached in-cluster.
  End-to-end encrypted (`MATRIX_E2EE_MODE=required`), one conversation per
  room. You talk to it from Beeper (a Beeper account is a Matrix account) or
  from any Matrix app signed in to an account on our server.

The homeserver is public on `matrix.<domain>`, which is also its server name,
because Beeper's server reaches it over federation. It federates with
`beeper.com` only, and registration is closed unless a token is set.

### Matrix setup

1. On a fresh database the server prints a one-time registration token in its
   log. In Element web, choose `matrix.<domain>` as the homeserver and register
   `admin` with it; the first account is the server admin and is invited to
   the Admin Room. (Later, `REGISTRATION_TOKEN` in the Bitwarden item
   `continuwuity` opens registration again; keep that item as `{}`.)
2. In the Admin Room: `!admin users create-user hermes`. It replies with a
   password.
3. Sign in to Element web as `hermes`, set up recovery (Settings → Encryption)
   and keep the recovery key.
4. Log in once more for Hermes's own device. Don't reuse Element's token: two
   clients on one device break its encryption.

   ```sh
   read -rs PW; curl -s https://matrix.<domain>/_matrix/client/v3/login \
     -H 'Content-Type: application/json' \
     -d "{\"type\":\"m.login.password\",\"identifier\":{\"type\":\"m.id.user\",\"user\":\"hermes\"},\"password\":\"$PW\",\"initial_device_display_name\":\"Hermes\"}" \
     | jq -r .access_token; unset PW
   ```

   Then sign `hermes` out of Element, so the account has Hermes's device only.

5. Add the Matrix fields below to the Bitwarden item `hermes`.
6. In Beeper Desktop or Android (iOS cannot start Matrix chats), start a chat
   with `@hermes:matrix.<domain>`. Hermes accepts the invite; expect a reply to a
   message. The chat then shows on every Beeper device.

If Beeper cannot reach the bot, check federation at
<https://federationtester.matrix.org> with `matrix.<domain>`.

### Other clients

Any Matrix app works with an account on our server; no federation is involved.
Element X (iOS) needs simplified sliding sync, which the server supports.

1. In the Admin Room: `!admin users create-user <name>`.
2. Add `@<name>:matrix.<domain>` to `MATRIX_ALLOWED_USERS` (comma-separated).
3. Sign in to the app with the server `matrix.<domain>` and start a chat with
   `@hermes:matrix.<domain>`.

Beeper cannot sign in to this server, so that is a second account and a second
conversation; Hermes's memory spans both. An account on another server (e.g.
matrix.org) also needs its server added to `CONTINUWUITY_ALLOWED_REMOTE_SERVER_NAMES`.
A new device reads only messages sent after it joined, unless it is verified with
the recovery key.

The bot's crypto store lives on Hermes's data volume
(`platforms/matrix/store/`). Losing it means a new token (a new device); old
messages stay unreadable to the bot.

## Dashboard

`https://hermes.<domain>` on `envoy-internal`: LAN and tailnet only,
username `hermes`. It serves the browser dashboard and the iOS clients (Hermes
Mobile, Hermex), which connect to the same address.

The password is an admin login: the dashboard edits Hermes's own settings and
runs chats with the assistant's tools. The managed config (`/etc/hermes`) still
wins over anything set there.

## Credentials

All in the Bitwarden item `hermes`. Telegram's three fields are required; the
rest are optional, and each feature stays off until its fields exist.

| Field                      | Value                                                                                  |
| -------------------------- | -------------------------------------------------------------------------------------- |
| `TELEGRAM_BOT_TOKEN`       | From BotFather                                                                         |
| `TELEGRAM_ALLOWED_USERS`   | Numeric user IDs it answers, comma-separated                                           |
| `TELEGRAM_HOME_CHANNEL`    | The chat routines deliver to                                                           |
| `MATRIX_ACCESS_TOKEN`      | From step 4; withheld until `MATRIX_ALLOWED_USERS` is set                              |
| `MATRIX_ALLOWED_USERS`     | Full Matrix IDs it answers, comma-separated: `@you:beeper.com`, `@you:matrix.<domain>` |
| `MATRIX_RECOVERY_KEY`      | From step 3; lets the bot verify its own device                                        |
| `DASHBOARD_PASSWORD`       | Starts the dashboard                                                                   |
| `DASHBOARD_SESSION_SECRET` | Any random string; keeps sign-ins across restarts                                      |
