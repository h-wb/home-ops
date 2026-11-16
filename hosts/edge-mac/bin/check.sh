#!/bin/sh
# Reports what would stop this Mac coming back up unattended. Changes nothing.
set -u

here=$(cd "$(dirname "$0")/.." && pwd)
# shellcheck source=/dev/null
. "$here/config.env"
utmctl=/Applications/UTM.app/Contents/MacOS/utmctl
uid=$(id -u)
failed=0

check() {
	name=$1
	shift
	if "$@" >/dev/null 2>&1; then
		echo "ok    $name"
	else
		echo "FAIL  $name"
		failed=1
	fi
}

# shellcheck disable=SC2329  # all invoked through check()
{
pm() { [ "$(pmset -g | awk -v key="$1" '$1 == key { print $2 }')" = "$2" ]; }
filevault_off() { fdesetup status | grep -q "FileVault is Off"; }
autologin() { [ "$(defaults read /Library/Preferences/com.apple.loginwindow autoLoginUser)" = "$(id -un)" ]; }
no_auto_os_update() { [ "$(defaults read /Library/Preferences/com.apple.SoftwareUpdate AutomaticallyInstallMacOSUpdates)" = 0 ]; }
vm_started() { [ "$("$utmctl" status "$VM_NAME")" = started ]; }
usb_present() { "$utmctl" usb list | grep -qi -- "$USB_MATCH"; }
loaded() { launchctl print "gui/$uid/$1"; }
}

check "FileVault is off (auto-login needs it)" filevault_off
check "auto-login is set to $(id -un)" autologin
check "system sleep is disabled" pm sleep 0
check "lid-closed sleep is disabled" pm SleepDisabled 1
check "macOS updates do not install themselves" no_auto_os_update
check "Remote Login (ssh) answers" nc -z 127.0.0.1 22
check "UTM VM '$VM_NAME' is started" vm_started
check "a USB device matching '$USB_MATCH' is plugged in" usb_present
check "agent home-ops.edge-mac.vm is loaded" loaded home-ops.edge-mac.vm
check "agent home-ops.edge-mac.pull is loaded" loaded home-ops.edge-mac.pull

exit "$failed"
