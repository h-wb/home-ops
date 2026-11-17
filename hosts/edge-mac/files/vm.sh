#!/bin/sh
# The Talos VM in UTM. utmctl only works inside the desktop session, never over
# ssh, so `up` and `stop` are LaunchAgent bodies; `request-stop` and `reboot`
# are the ssh side.
set -eu

here=$(cd "$(dirname "$0")" && pwd)
# Rendered from [vars] in mise.edge-mac.toml.
# shellcheck source=/dev/null
. "$here/config.env"
utmctl=/Applications/UTM.app/Contents/MacOS/utmctl
# Under sudo (`reboot`), the agents are the desktop user's.
uid=$(id -u)
[ "$uid" != 0 ] || uid=$(stat -f %u /dev/console)
domain="gui/$uid"

status() { "$utmctl" status "$VM_NAME" 2>/dev/null || true; }
running() { pgrep -qf QEMULauncher; }

wait_for() {
	want=$1 tries=$2
	while [ "$tries" -gt 0 ]; do
		[ "$(status)" = "$want" ] && return 0
		sleep 2
		tries=$((tries - 1))
	done
	return 1
}

up() {
	pgrep -xq UTM || { open -gja UTM; sleep 10; }
	case "$(status)" in
	started | starting) return 0 ;;
	esac
	"$utmctl" start "$VM_NAME"
	wait_for started 60 || { echo "$VM_NAME did not start: $(status)" >&2; return 1; }
	echo "$(date '+%F %T') started $VM_NAME"
	# UTM reconnects the devices it has saved; this covers the case where it
	# does not, and fails harmlessly when it already has.
	sleep 5
	"$utmctl" usb connect "$VM_NAME" "$USB_DEVICE" || true
}

# Boots out the keep-alive agent first or it would start the VM again; apply
# or the next login loads it back.
stop() {
	launchctl bootout "$domain/dev.mise.edge-vm" 2>/dev/null || true
	[ "$(status)" = stopped ] && return 0
	"$utmctl" stop "$VM_NAME" --request
	wait_for stopped 90 && return 0
	echo "$VM_NAME ignored the shutdown request, forcing" >&2
	"$utmctl" stop "$VM_NAME"
	wait_for stopped 30
}

request_stop() {
	running || return 0
	launchctl kickstart "$domain/dev.mise.edge-vm-stop"
	tries=75
	while running && [ "$tries" -gt 0 ]; do
		sleep 2
		tries=$((tries - 1))
	done
	! running || { echo "$VM_NAME is still running: see ~/Library/Logs/edge-mac.log" >&2; return 1; }
}

case "${1:-}" in
up | stop) "$1" ;;
request-stop) request_stop ;;
reboot) request_stop && shutdown -r now ;;
*) echo "usage: $0 up|stop|request-stop|reboot" >&2; exit 2 ;;
esac
