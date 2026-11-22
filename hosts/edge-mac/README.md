# Edge Mac

The Intel Mac that hosts the edge cluster: Talos runs as a UTM VM with the
Zigbee dongle passed through, next to the BlueBubbles server. This directory
makes the Mac come back on its own after a restart.

It is a [mise bootstrap](https://mise.jdx.dev/bootstrap.html) project pushed
over ssh: `mise run //hosts/edge-mac:apply` packs the directory and applies
`mise.edge-mac.toml`. It leaves mise installed for the collector. The Mac
needs no checkout. `diff` previews configuration changes without checking tool
installs.

| In `mise.edge-mac.toml` | What it does                                                                                                                                              |
| ----------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| packages                | UTM and BlueBubbles, pinned to a GitHub release                                                                                                           |
| macOS defaults          | UTM stays open, keeps the Mac awake and powers the VM down on quit; lock after a minute                                                                   |
| agent `edge-vm`         | Every minute: open UTM, start the VM if it is not running, reconnect the dongle after                                                                     |
| agent `bluebubbles`     | Keeps BlueBubbles open                                                                                                                                    |
| Messages collector      | Sends messages and attachments to [Miroir](#miroir-collector) over WireGuard                                                                              |
| sshd drop-in            | Key-only login                                                                                                                                            |
| `final` hook            | Never sleep (lid closed included); no self-installing macOS updates; a sudoers rule letting admins run `shutdown -r now` without a password, for `reboot` |
| `[doctor.checks]`       | What an unattended boot depends on, with the fix as each check's hint                                                                                     |

`files/vm.sh` is installed to `/usr/local/libexec/edge-mac`; the VM name and
the dongle's USB id are `[vars]`. `utmctl` refuses to work over ssh, and a
detached process does not outlive an ssh session there, so everything that
drives UTM or restarts the Mac is a LaunchAgent in the desktop session that ssh
only kickstarts.

| Task        | What it does                                                                     |
| ----------- | -------------------------------------------------------------------------------- |
| `apply`     | Applies `mise.edge-mac.toml`; asks for sudo on the Mac                           |
| `diff`      | Configuration changes `apply` would make                                         |
| `check`     | Runs the doctor checks on the Mac                                                |
| `reboot`    | Stops the VM cleanly, then restarts the Mac; returns at once, allow five minutes |
| `ssh`       | A shell on the Mac, or `mise run //hosts/edge-mac:ssh -- <command>`              |
| `secrets`   | Provisions the collector and WireGuard secrets; workstation only                 |
| `ssh:setup` | Installs the ssh key on a Mac that does not have it yet                          |

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

The [collector](https://github.com/h-wb/pipelines/tree/main/collector) sends
new messages and locally stored attachments to Miroir every minute.
`/etc/hosts` resolves Miroir and its bucket without changing the Mac's DNS.

1. Create a dedicated WireGuard peer. Save its config in the note field of
   `Machines/wireguard-edge-mac` in Proton Pass. Set
   `AllowedIPs = 192.168.1.201/32, 192.168.1.202/32` (bucket and Miroir) and
   `PersistentKeepalive = 25`. Omit `DNS` and default routes so the Mac stays
   reachable on the edge LAN. If supported, restrict the peer to HTTPS on
   those two addresses on the WireGuard server.
2. Sign in to the App Store on the Mac and claim WireGuard if the account
   hasn't already. From a workstation, run `mise run //hosts/edge-mac:secrets`,
   then `mise run //hosts/edge-mac:apply`. If `apply` skips WireGuard because
   `mas` isn't installed yet, rerun it: mise installs tools after packages.
3. In WireGuard, import `~/.config/wireguard/wg-main.conf` and allow the VPN
   configuration. When rotating the peer, rerun `secrets` and reimport it.
4. On the Mac, open Privacy & Security → Full Disk Access. Add the collector's
   Python (not `/bin/sh`) using Cmd-Shift-G and the path printed by:

   ```sh
   mise run //hosts/edge-mac:ssh -- 'collector=$("$HOME/.local/bin/mise" -C "$HOME" which miroir-collector) && "$(dirname "$collector")/../miroir-collector/bin/python" -c "import sys; from pathlib import Path; print(Path(sys.executable).resolve())"'
   ```

   Renew the grant if an upgrade changes the resolved Python path.

5. After a minute, run `mise run //hosts/edge-mac:check`. For delivery status,
   see the `messages` connection in Miroir or `~/Library/Logs/miroir-collector.log`.

To upgrade the collector, change the pin in `files/collector.toml` and rerun
`apply`.

## Upgrading an app

Change `version` and `sha256`, then:

- UTM: `mise run //hosts/edge-mac:ssh -- sh /usr/local/libexec/edge-mac/vm.sh request-stop`,
  then `-- killall UTM`, then `apply`. It reloads the agent, which opens the
  new UTM and starts the VM. From UTM 5 the quit policy in the defaults
  applies: a plain macOS restart then powers Talos down by itself.
- BlueBubbles: `apply`, then `mise run //hosts/edge-mac:ssh -- killall BlueBubbles`.
  The agent reopens it within a minute.
