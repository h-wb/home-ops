# Edge Mac

The Intel Mac that hosts the edge cluster: Talos runs as a UTM VM with the
Zigbee dongle passed through, next to the BlueBubbles server. This directory
makes the Mac come back on its own after a restart.

It is a [mise bootstrap](https://mise.jdx.dev/bootstrap.html) project pushed
over ssh: `mise run //hosts/edge-mac:apply` packs the directory, stages mise on
the Mac for the run and applies `mise.edge-mac.toml`. The Mac needs no checkout
and no mise of its own. `diff` shows what `apply` would change.

| In `mise.edge-mac.toml` | What it does                                                                            |
| ----------------------- | --------------------------------------------------------------------------------------- |
| packages                | UTM and BlueBubbles, pinned to a GitHub release                                         |
| macOS defaults          | UTM stays open, keeps the Mac awake and powers the VM down on quit; lock after a minute |
| agent `edge-vm`         | Every minute: open UTM, start the VM if it is not running, reconnect the dongle after   |
| agent `bluebubbles`     | Keeps BlueBubbles open                                                                  |
| sshd drop-in            | Key-only login                                                                          |
| `final` hook            | Never sleep (lid closed included); macOS updates do not install themselves              |
| `[doctor.checks]`       | What an unattended boot depends on, with the fix as each check's hint                   |

`files/vm.sh` is installed to `/usr/local/libexec/edge-mac`; the VM name and
the dongle's USB id are `[vars]`. `utmctl` refuses to work over ssh, so
everything that drives UTM runs as a LaunchAgent in the desktop session, and
ssh only kickstarts it.

Also `mise run //hosts/edge-mac:check | reboot`. `check` runs the doctor checks
on the Mac; `reboot` stops the VM, then restarts, detached from the ssh session
(from the tailnet the route to this Mac runs through the VM, and drops with it). All of it goes through the
ssh alias `edge-mac`, and was written against mise 2026.11.8: an older one
ignores `[bootstrap.settings.macos]`.

## ssh

`apply` leaves the Mac's sshd key-only, so the key goes on first:
`mise run //hosts/edge-mac:ssh:setup` copies this workstation's keys with
`ssh-copy-id` (the one time the account password is typed over ssh) and checks
that a key login works. `apply` runs that check again and refuses without it.
`sudo` on the Mac still asks for the password.

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
`cannot adopt`, before anything else changes. BlueBubbles does: it updates
itself from a different archive than the release's `.dmg`. Then quit the app,
move it out of `/Applications` under a name not ending in `.app`, and apply
again (for UTM, shut the VM down first). The VMs
(`~/Library/Containers/com.utmapp.UTM`) and the BlueBubbles data
(`~/Library/Application Support/bluebubbles-server`) are not in the bundle.
A replaced app may need its permissions granted again.

Amphetamine is what kept this Mac awake before; the `final` hook makes it
redundant.

## Upgrading an app

Change `version` and `sha256`, then:

- UTM: `ssh edge-mac sh /usr/local/libexec/edge-mac/vm.sh request-stop`,
  `ssh edge-mac killall UTM`, then `apply`. It reloads the agent, which opens
  the new UTM and starts the VM. From UTM 5 the quit policy in the defaults
  applies: a plain macOS restart then powers Talos down by itself.
- BlueBubbles: `apply`, then `ssh edge-mac killall BlueBubbles`. The agent
  reopens it within a minute.
