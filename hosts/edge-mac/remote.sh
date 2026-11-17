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
bootstrap() { mise bootstrap remote --host "$mac" --ssh-option "$trust" --remote-env edge-mac "$@"; }
key_login() { ssh -o "$trust" -o BatchMode=yes -o PreferredAuthentications=publickey "$mac" true; }

case "${1:-}" in
ssh-setup)
	ssh-copy-id -o "$trust" "$mac"
	key_login
	;;
apply)
	# The Mac's sshd is key-only once applied: never apply without a key login.
	key_login || { echo "no key login to the Mac: run \`mise run //hosts/edge-mac:ssh:setup\`" >&2; exit 1; }
	bootstrap --skip task
	;;
diff) bootstrap --skip task --dry-run ;;
check) bootstrap --only task ;;
reboot) ssh -o "$trust" "$mac" 'launchctl kickstart "gui/$(id -u)/dev.mise.edge-reboot"' ;;
ssh)
	shift
	ssh -o "$trust" "$mac" "$@"
	;;
*) echo "usage: $0 ssh-setup|apply|diff|check|reboot|ssh [command]" >&2; exit 2 ;;
esac
