#!/bin/sh
# LaunchAgent body: fast-forward the checkout; re-apply the agents when this
# directory changed. The scripts run from the checkout, so a pull alone
# already updates them.
set -eu

here=$(cd "$(dirname "$0")/.." && pwd)
cd "$here"

before=$(git rev-parse HEAD)
git pull --ff-only --quiet
after=$(git rev-parse HEAD)
[ "$before" = "$after" ] && exit 0

echo "$(date '+%F %T') pulled $before..$after"
git diff --quiet "$before" "$after" -- . || SELF_LABEL=home-ops.edge-mac.pull sh bin/apply.sh --user
