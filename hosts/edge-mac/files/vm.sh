#!/bin/sh
# The Talos VM in UTM. `up` is the edge-vm LaunchAgent's body.
set -eu

here=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=/dev/null
. "$here/config.env"
utmctl=/Applications/UTM.app/Contents/MacOS/utmctl
label=dev.mise.edge-vm

status() { "$utmctl" status "$VM_NAME" 2>/dev/null || true; }

wait_for() {
	want=$1 tries=$2
	while [ "$tries" -gt 0 ]; do
		[ "$(status)" = "$want" ] && return 0
		sleep 2
		tries=$((tries - 1))
	done
	return 1
}

# UTM forgets USB passthrough at every VM start and every replug.
usb() {
	devices=$("$utmctl" usb list | grep -i -- "$USB_MATCH" | grep -Eo '[0-9A-Fa-f]{4}:[0-9A-Fa-f]{4}' | sort -u)
	[ -n "$devices" ] || { echo "no USB device matching '$USB_MATCH'" >&2; return 1; }
	for device in $devices; do
		"$utmctl" usb connect "$VM_NAME" "$device"
		echo "$(date '+%F %T') connected $device to $VM_NAME"
	done
}

up() {
	pgrep -xq UTM || { open -gja UTM; sleep 10; }
	case "$(status)" in
	started | starting) return 0 ;;
	esac
	"$utmctl" start "$VM_NAME"
	wait_for started 60 || { echo "$VM_NAME did not start: $(status)" >&2; return 1; }
	echo "$(date '+%F %T') started $VM_NAME"
	sleep 5
	usb
}

# Boots out the keep-alive agent first or it would start the VM again; the
# agent comes back at the next login.
stop() {
	launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
	[ "$(status)" = stopped ] && return 0
	"$utmctl" stop "$VM_NAME" --request
	wait_for stopped 90 && return 0
	echo "$VM_NAME ignored the shutdown request, forcing" >&2
	"$utmctl" stop "$VM_NAME"
	wait_for stopped 30
}

case "${1:-}" in
up | usb | stop | status) "$1" ;;
*) echo "usage: $0 up|usb|stop|status" >&2; exit 2 ;;
esac
