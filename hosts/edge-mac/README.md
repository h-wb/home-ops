# Edge Mac

The Intel Mac that hosts the edge cluster: Talos runs as a UTM VM with the
Zigbee dongle passed through, next to the BlueBubbles server. This directory
makes the Mac come back on its own after a restart.

It is a [mise bootstrap](https://mise.jdx.dev/bootstrap.html) project pushed
over ssh: `mise run //hosts/edge-mac:apply` packs the directory, stages mise on
the Mac for the run and applies `mise.edge-mac.toml`. The Mac needs no checkout
and no mise of its own. `diff` shows what `apply` would change.

| Piece               | What it does                                                                          |
| ------------------- | ------------------------------------------------------------------------------------- |
| agent `edge-vm`     | Every minute: open UTM, start the VM if it is not running, reconnect the dongle after |
| agent `bluebubbles` | Keeps BlueBubbles open                                                                |
| `final` hook        | Never sleep (lid closed included); macOS updates do not install themselves            |
| `files/vm.sh`       | `up` (the agent), `usb`, `stop`; installed to `/usr/local/libexec/edge-mac`           |
| `files/check.sh`    | Read-only report of everything an unattended boot depends on                          |

Also `mise run //hosts/edge-mac:check | usb | reboot`. `reboot` shuts Talos
down cleanly first; a restart from the Apple menu can stall on UTM's quit
prompt. All of it goes through the ssh alias `edge-mac`.

## Once, by hand

macOS has no API for these without MDM. `check` reports the first two.

1. FileVault off, then Users & Groups → automatically log in. UTM and
   BlueBubbles are GUI apps, so both only start inside a login session.
2. Sharing → Remote Login, and Screen Sharing for the prompt below.
3. Lock Screen → require password immediately, screen saver after a minute.
4. A firmware password (`sudo firmwarepasswd -setpasswd`), so the unencrypted
   disk cannot be read from Recovery or Target Disk Mode.
5. BlueBubbles: sign Messages in, grant the app Full Disk Access and
   Accessibility.
6. After the first `apply`, approve the "control UTM" prompt on the Mac's
   screen. `apply` has to run while that user is logged in at the desktop:
   LaunchAgents only load into a live login session.
