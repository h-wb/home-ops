#!/bin/sh
# LaunchAgent body: reopen the GUI apps in KEEP_OPEN when they are not running.
set -eu

here=$(cd "$(dirname "$0")/.." && pwd)
# shellcheck source=/dev/null
. "$here/config.env"

for app in $KEEP_OPEN; do
	pgrep -xq "$app" && continue
	open -gja "$app"
	echo "$(date '+%F %T') opened $app"
done
