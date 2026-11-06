#!/bin/sh
# Installs obsidian-headless and Seekstone from the lockfiles in git into the shared tools
# volume, so the vault and Seekstone pods need no registry access (the vault pod's egress is
# Obsidian Sync only). Same node image as the runtime pods: better-sqlite3 is a native module.
# Flux substitutes dollar-brace references in this file, so it uses only plain $VAR forms.
set -eu
for p in ob seekstone; do
  rm -rf "/tmp/build/$p" && mkdir -p "/tmp/build/$p"
  cp "/src/$p-package.json" "/tmp/build/$p/package.json"
  cp "/src/$p-package-lock.json" "/tmp/build/$p/package-lock.json"
  (cd "/tmp/build/$p" && npm ci --omit=dev --no-audit --no-fund)
  rm -rf "/tools/$p.new" && cp -a "/tmp/build/$p" "/tools/$p.new"
  rm -rf "/tools/$p" && mv "/tools/$p.new" "/tools/$p"
  echo "$p installed"
done
/tools/ob/node_modules/.bin/ob --version
