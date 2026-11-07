#!/bin/sh
# Installs Seekstone from the lockfiles in git into the shared tools volume, so the
# Seekstone pods need no registry access. Same node image as the runtime pods:
# better-sqlite3 is a native module. The vault sync no longer goes through this Job:
# the Belphemur image ships the `ob` CLI itself (helmrelease.yaml).
# Flux substitutes dollar-brace references in this file, so it uses only plain $VAR forms.
set -eu
rm -rf /tmp/build/seekstone && mkdir -p /tmp/build/seekstone
cp /src/seekstone-package.json /tmp/build/seekstone/package.json
cp /src/seekstone-package-lock.json /tmp/build/seekstone/package-lock.json
(cd /tmp/build/seekstone && npm ci --omit=dev --no-audit --no-fund)
rm -rf /tools/seekstone.new && cp -a /tmp/build/seekstone /tools/seekstone.new
rm -rf /tools/seekstone && mv /tools/seekstone.new /tools/seekstone
echo "seekstone installed"
/tools/seekstone/node_modules/.bin/seekstone --version
