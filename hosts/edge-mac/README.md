# Edge Mac

The Intel Mac that hosts the edge cluster: Talos runs as a UTM VM named in
`config.env`, with the Zigbee dongle passed through. This directory makes the
Mac come back on its own after a restart, and keeps it converged on `main`.

| Piece          | What it does                                                                                              |
| -------------- | --------------------------------------------------------------------------------------------------------- |
| `bin/apply.sh` | Power settings (never sleep, lid closed included), no self-installing macOS updates, the two LaunchAgents |
| `bin/vm.sh up` | Agent, every minute: open UTM, start the VM if it is not running, reconnect the dongle after a start      |
| `bin/pull.sh`  | Agent, every 15 min: fast-forward the checkout, re-apply the agents when this directory changed           |
| `bin/check.sh` | Read-only report of everything an unattended boot depends on                                              |

From a workstation: `mise run //hosts/edge-mac:check | apply | usb | reboot`
(ssh alias `edge-mac`, see `mise.toml`). `reboot` shuts Talos down cleanly
first; a restart from the Apple menu can stall on UTM's quit prompt.

## Once, by hand

macOS has no API for these without MDM. `check.sh` reports the first three.

1. FileVault off, then Users & Groups → automatically log in. UTM is a GUI
   app, so the VM only starts inside a login session.
2. Sharing → Remote Login, and Screen Sharing for the prompts below.
3. Lock Screen → require password immediately, screen saver after a minute.
4. A firmware password (`sudo firmwarepasswd -setpasswd`), so the unencrypted
   disk cannot be read from Recovery or Target Disk Mode.
5. Clone this repo to `~/home-ops` (not under Documents, Desktop or Downloads:
   LaunchAgents cannot read those) and run `sh hosts/edge-mac/bin/apply.sh`
   on the Mac's own screen. Approve the "control UTM" prompt it raises; a
   later one from ssh needs approving the same way.

The pull agent runs whatever `main` holds as the logged-in user, the same
trust Flux already has. The sudo half of `apply.sh` only ever runs by hand.
