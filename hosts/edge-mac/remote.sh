#!/bin/sh
# Workstation side of the tasks in mise.toml. The Mac's address and its ssh key
# come from Proton Pass (item `edge-mac`, vault Automation General), so this
# runs the same from a workstation or a Paseo pod, with no ~/.ssh/config entry.
set -eu

cd "$(dirname "$0")"
fnox_toml="$(git rev-parse --show-toplevel)/fnox.toml"
secret() { fnox get -c "$fnox_toml" "$1"; }
mac="$(secret EDGE_MAC_USER)@$(secret EDGE_MAC_HOST)"

sock=$(mktemp -u "${TMPDIR:-/tmp}/edge-mac-agent.XXXXXX")
PASS_LOG_LEVEL=error pass-cli ssh-agent start --socket-path "$sock" \
	--vault-name "Automation General" >/dev/null 2>&1 &
agent=$!
trap 'kill "$agent" 2>/dev/null; rm -f "$sock"' EXIT
export SSH_AUTH_SOCK="$sock"
tries=20
until ssh-add -L >/dev/null 2>&1; do
	tries=$((tries - 1))
	[ "$tries" -gt 0 ] || { echo "no ssh key from Proton Pass: is the session logged in?" >&2; exit 1; }
	sleep 1
done

trust="StrictHostKeyChecking=accept-new"
mac_ssh() { ssh -o "$trust" -o ConnectTimeout=10 "$@"; }
bootstrap() { mise bootstrap remote --host "$mac" --ssh-option "$trust" --remote-env edge-mac "$@"; }

# Also what keeps `apply` from turning password login off before a key works.
case "${1:-}" in
ssh-setup) ;;
*)
	mac_ssh -o BatchMode=yes -o PreferredAuthentications=publickey "$mac" true || {
		echo "no key login to the Mac. Unreachable: from the tailnet the route runs through" >&2
		echo "the VM, so it has to be running. Key refused: mise run //hosts/edge-mac:ssh:setup" >&2
		exit 1
	}
	;;
esac

# shellcheck disable=SC2016  # expands on the Mac
kickstart_reboot='launchctl kickstart "gui/$(id -u)/dev.mise.edge-reboot"'

case "${1:-}" in
ssh-setup)
	ssh-copy-id -o "$trust" -o ConnectTimeout=10 "$mac"
	mac_ssh -o BatchMode=yes -o PreferredAuthentications=publickey "$mac" true
	;;
apply) bootstrap --skip task ;;
diff) bootstrap --skip task --dry-run ;;
check) bootstrap --only task ;;
reboot) mac_ssh "$mac" "$kickstart_reboot" ;;
ssh)
	shift
	mac_ssh "$mac" "$@"
	;;
*) echo "usage: $0 ssh-setup|apply|diff|check|reboot|ssh [command]" >&2; exit 2 ;;
esac
