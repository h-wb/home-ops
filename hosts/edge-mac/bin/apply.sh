#!/bin/sh
# Idempotent host setup. `--user` skips the sudo half (what pull.sh runs).
set -eu

here=$(cd "$(dirname "$0")/.." && pwd)
uid=$(id -u)
log="$HOME/Library/Logs/home-ops-edge-mac.log"

system() {
	# One key per call: a key this model lacks must not drop the others.
	for setting in "sleep 0" "disksleep 0" "displaysleep 5" "standby 0" "autopoweroff 0" \
		"powernap 0" "womp 1" "autorestart 1" "disablesleep 1"; do
		# shellcheck disable=SC2086
		sudo pmset -a $setting || echo "pmset: '$setting' not applied" >&2
	done
	# macOS updates reboot the host: install them on purpose, not overnight.
	sudo defaults write /Library/Preferences/com.apple.SoftwareUpdate AutomaticallyInstallMacOSUpdates -bool false
}

# pull.sh re-applies from inside its own agent, and booting that agent out
# would kill the run before it loads the new one: SELF_LABEL is left alone.
agent() {
	label=$1 interval=$2 script=$3 arg=${4:-}
	plist="$HOME/Library/LaunchAgents/$label.plist"
	tmp=$(mktemp)
	cat >"$tmp" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>Label</key>
	<string>$label</string>
	<key>ProgramArguments</key>
	<array>
		<string>/bin/sh</string>
		<string>$here/bin/$script</string>
		${arg:+<string>$arg</string>}
	</array>
	<key>RunAtLoad</key>
	<true/>
	<key>StartInterval</key>
	<integer>$interval</integer>
	<key>StandardOutPath</key>
	<string>$log</string>
	<key>StandardErrorPath</key>
	<string>$log</string>
</dict>
</plist>
PLIST
	if cmp -s "$tmp" "$plist" && launchctl print "gui/$uid/$label" >/dev/null 2>&1; then
		rm -f "$tmp"
		return 0
	fi
	if [ "$label" = "${SELF_LABEL:-}" ]; then
		rm -f "$tmp"
		echo "$label changed: run apply.sh by hand to reload it" >&2
		return 0
	fi
	mkdir -p "$HOME/Library/LaunchAgents"
	mv "$tmp" "$plist"
	launchctl bootout "gui/$uid/$label" 2>/dev/null || true
	launchctl bootstrap "gui/$uid" "$plist"
	echo "loaded $label"
}

[ "${1:-}" = --user ] || system
agent home-ops.edge-mac.vm 60 vm.sh up
agent home-ops.edge-mac.apps 60 apps.sh
agent home-ops.edge-mac.pull 900 pull.sh
