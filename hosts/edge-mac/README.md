# Edge Mac

The Intel Mac that hosts the edge cluster: Talos runs as a UTM VM with the
Zigbee dongle passed through, next to the BlueBubbles server. This directory
makes the Mac come back on its own after a restart. It is also the always-on
Mac that sends Messages to the
[data warehouse](../../kubernetes/apps/main/automation/miroir/README.md).

It is a [mise bootstrap](https://mise.jdx.dev/bootstrap.html) project pushed
over ssh: `mise run //hosts/edge-mac:apply` packs the directory, stages mise on
the Mac for the run and applies `mise.edge-mac.toml`. The Mac needs no checkout
and no mise of its own. `diff` shows what `apply` would change.

| In `mise.edge-mac.toml`  | What it does                                                                                                                                              |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| packages                 | UTM and BlueBubbles, pinned to a GitHub release                                                                                                           |
| macOS defaults           | UTM stays open, keeps the Mac awake and powers the VM down on quit; lock after a minute                                                                   |
| agent `edge-vm`          | Every minute: open UTM, start the VM if it is not running, reconnect the dongle after                                                                     |
| agent `bluebubbles`      | Keeps BlueBubbles open                                                                                                                                    |
| agent `miroir-collector` | Every minute: send new messages and attachments to Miroir ([below](#miroir-collector))                                                                    |
| `/etc/hosts` block       | Miroir's and its bucket's names, pointed at the edge cluster's gateway                                                                                    |
| `post-tools` hook        | Installs the pinned `miroir-collector` with a Python of its own                                                                                           |
| sshd drop-in             | Key-only login                                                                                                                                            |
| `final` hook             | Never sleep (lid closed included); no self-installing macOS updates; a sudoers rule letting admins run `shutdown -r now` without a password, for `reboot` |
| `[doctor.checks]`        | What an unattended boot depends on, with the fix as each check's hint                                                                                     |

`files/vm.sh` is installed to `/usr/local/libexec/edge-mac`; the VM name and
the dongle's USB id are `[vars]`. `utmctl` refuses to work over ssh, and a
detached process does not outlive an ssh session there, so everything that
drives UTM or restarts the Mac is a LaunchAgent in the desktop session that ssh
only kickstarts.

| Task                | What it does                                                                         |
| ------------------- | ------------------------------------------------------------------------------------ |
| `apply`             | Applies `mise.edge-mac.toml`; asks for sudo on the Mac                               |
| `diff`              | What `apply` would change                                                            |
| `check`             | Runs the doctor checks on the Mac                                                    |
| `reboot`            | Stops the VM cleanly, then restarts the Mac; returns at once, allow five minutes     |
| `ssh`               | A shell on the Mac, or `mise run //hosts/edge-mac:ssh -- <command>`                  |
| `collector:secrets` | Puts the Miroir address and the Messages delivery token on the Mac; workstation only |
| `ssh:setup`         | Installs the ssh key on a Mac that does not have it yet                              |

From the tailnet (a Paseo pod), the route to this Mac is the subnet router
inside the VM: while the VM is down, only a machine on the Mac's own LAN
reaches it. Written against mise 2026.11.8: an older one ignores
`[bootstrap.settings.macos]`.

## ssh

The tasks get the Mac from the Proton Pass item `edge-mac` (vault
`Automation General`): its `destination` field (`user@host`) as the mise secret
`EDGE_MAC`, and its ssh key from the Proton Pass ssh agent. A workstation
already runs that agent; on a pod the hidden `ssh:agent` task starts one. No
`~/.ssh/config` entry and no key file anywhere.

`apply` leaves the Mac's sshd key-only and depends on `ssh:verify`, so it never
runs before a key login works. On a Mac that does not have the key yet,
`ssh:setup` copies it with `ssh-copy-id`, the one time the account password is
typed over ssh. `sudo` on the Mac still asks for the password.

## Once, by hand

macOS has no API for these without MDM. `check` reports the first one.

1. FileVault off, then Users & Groups → automatically log in. UTM and
   BlueBubbles are GUI apps, so both only start inside a login session.
2. Sharing → Remote Login, and Screen Sharing for the prompt below. Then
   `ssh:setup` from the workstation.
3. Lock Screen → require password immediately after the screen saver starts.
4. A firmware password (`sudo firmwarepasswd -setpasswd`), so the unencrypted
   disk cannot be read from Recovery or Target Disk Mode.
5. BlueBubbles: sign Messages in, grant the app Full Disk Access and
   Accessibility.
6. Turn off BlueBubbles' own auto-update: the pin here is its only updater.
7. After the first `apply`, approve the "control UTM" prompt on the Mac's
   screen. `apply` has to run while that user is logged in at the desktop:
   LaunchAgents only load into a live login session.
8. Full Disk Access for the collector's Python, so it may read the Messages
   database: Privacy & Security → Full Disk Access → `+`, then Cmd-Shift-G and
   the path that this prints:

   ```sh
   mise run //hosts/edge-mac:ssh -- 'readlink -f "$(head -1 ~/.local/bin/miroir-collector | cut -c3-)"'
   ```

   Granting it again is needed whenever that path changes, which a new Python
   patch release does and a new collector release does not.

## First apply

The apps on the Mac were installed by hand, and the pins match them (UTM
4.7.5, BlueBubbles 1.9.12). mise takes an app over only when it is identical
to the pinned release; otherwise `apply` stops at the packages step with
`cannot adopt`, before anything else changes. A BlueBubbles that has updated
itself always differs: its updater uses another archive than the release's
`.dmg`. Then quit the app,
move it out of `/Applications` under a name not ending in `.app`, and apply
again (for UTM, shut the VM down first). The VMs
(`~/Library/Containers/com.utmapp.UTM`) and the BlueBubbles data
(`~/Library/Application Support/bluebubbles-server`) are not in the bundle.
A replaced app may need its permissions granted again.

Amphetamine is what kept this Mac awake before; the `final` hook makes it
redundant.

## Miroir collector

[`miroir-collector`](https://github.com/h-wb/pipelines/tree/main/collector)
reads `~/Library/Messages/chat.db` in place, masks secrets, and delivers what
is new to Miroir's `messages` connection, with the attachment files. This Mac
suits it: it is always on, and Messages in iCloud is off here, so every
attachment stays on its disk. It has no contacts, so it sends no names.

```
launchd, every minute
  └─ miroir-collector run          ~/.local/bin, state in ~/Library/Application Support/miroir-collector
       └─ https://miroir.<domain>  /etc/hosts → the edge cluster's internal gateway (192.168.18.202)
            └─ miroir-relay pod    kubernetes/apps/edge/network/miroir-relay, over the tailnet
                 ├─ miroir-lb      main, 192.168.1.207: the Miroir server
                 └─ garage-lb      main, 192.168.1.208: the media bucket, for signed uploads
```

Miroir is not reachable from this site, and the Mac itself is not on the
tailnet, so the edge cluster relays it. The gateway's routes pass only a
connection's four device endpoints and uploads to signed links. While the VM,
the tailnet or Miroir is down the collector keeps its batch and tries again a
minute later; nothing is lost.

Two values are not in git: the domain and the delivery token. First time, in
this order:

1. On the main cluster's side, approve the routes `192.168.1.207/32` and
   `192.168.1.208/32` of the node `main` in the Tailscale admin console.
2. `mise run //hosts/edge-mac:collector:secrets`, from a workstation. It reads
   both from Proton Pass (`Machines`, so not from a Paseo pod) and writes
   `~/.config/miroir-collector/zone` and `token` on the Mac, readable by that
   user only. The disk is not encrypted; the token can only add data to that
   one connection.
3. `apply`. It renders the configuration and the `/etc/hosts` block from the
   address, installs the collector and loads the agent.
4. Full Disk Access, as in "Once, by hand".
5. `check`, a minute later: the four `collector` checks.

To watch it: `~/Library/Logs/miroir-collector.log` on the Mac (one line per
pass, never content), and the `messages` connection's page in Miroir, where
each pass reports. Miroir's alerts cover a collector that fails or goes
silent.

To move to another release, change `collector_version` and `apply`. The
collector carries on from its saved state. To send a range again:

```sh
mise run //hosts/edge-mac:ssh -- 'MIROIR_TOKEN_MESSAGES="$(cat ~/.config/miroir-collector/token)" ~/.local/bin/miroir-collector resend --config ~/.config/miroir-collector/config.json --source messages --from 2026-11-01'
```

## Upgrading an app

Change `version` and `sha256`, then:

- UTM: `mise run //hosts/edge-mac:ssh -- sh /usr/local/libexec/edge-mac/vm.sh request-stop`,
  then `-- killall UTM`, then `apply`. It reloads the agent, which opens the
  new UTM and starts the VM. From UTM 5 the quit policy in the defaults
  applies: a plain macOS restart then powers Talos down by itself.
- BlueBubbles: `apply`, then `mise run //hosts/edge-mac:ssh -- killall BlueBubbles`.
  The agent reopens it within a minute.
