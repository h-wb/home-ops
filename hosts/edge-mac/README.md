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
| `final` hook            | Never sleep (lid closed included); macOS updates do not install themselves              |
| `[doctor.checks]`       | What an unattended boot depends on, with the fix as each check's hint                   |

`files/vm.sh` (`up` for the agent, `usb`, `stop`) is installed to
`/usr/local/libexec/edge-mac`; its VM name and dongle match are `[vars]`.

Also `mise run //hosts/edge-mac:check | usb | reboot`. `check` runs the doctor
checks on the Mac, `usb` reconnects the dongle after a replug, `reboot` stops
the VM before restarting. All of it goes through the ssh alias `edge-mac`, and
was written against mise 2026.11.8: an older one ignores
`[bootstrap.settings.macos]`.

## Once, by hand

macOS has no API for these without MDM. `check` reports the first one.

1. FileVault off, then Users & Groups → automatically log in. UTM and
   BlueBubbles are GUI apps, so both only start inside a login session.
2. Sharing → Remote Login, and Screen Sharing for the prompt below.
3. Lock Screen → require password immediately after the screen saver starts.
4. A firmware password (`sudo firmwarepasswd -setpasswd`), so the unencrypted
   disk cannot be read from Recovery or Target Disk Mode.
5. BlueBubbles: sign Messages in, grant the app Full Disk Access and
   Accessibility.
6. Turn off BlueBubbles' own auto-update: the pin here is its only updater.
7. After the first `apply`, approve the "control UTM" prompt on the Mac's
   screen, and once more when `check` or `usb` first asks over ssh. `apply` has to run while that user is logged in at the desktop:
   LaunchAgents only load into a live login session.

## First apply

The apps on the Mac were installed by hand. mise takes one over only when it
is identical to the pinned release; otherwise `apply` stops at the packages
step with `cannot adopt`, before anything else changes. Either pin the
installed version instead, or shut the VM down, quit the app and delete it
from `/Applications`, then apply again. The VMs
(`~/Library/Containers/com.utmapp.UTM`) and the BlueBubbles data
(`~/Library/Application Support/bluebubbles-server`) are not in the bundle.
A replaced app may need its permissions granted again.

## Upgrading an app

Change `version` and `sha256`, then:

- UTM: `ssh edge-mac sh /usr/local/libexec/edge-mac/vm.sh stop`, then `apply`.
  It reloads the agent, which starts the VM on the new UTM.
- BlueBubbles: `apply`, then `ssh edge-mac killall BlueBubbles`. The agent
  reopens it within a minute.
