#!/bin/bash

set -euo pipefail

torrentName=$1
torrentPath=$2
torrentCategory=$3

logDir="$(dirname "$0")"
logFile="$logDir/qbit-games-importer.log"

# Only proceed if the category is 'games'
if [[ "$torrentCategory" != "games" ]]; then
  echo "[!] Skipped \"$torrentName\" - category is \"$torrentCategory\"" >> "$logFile"
  exit 0
fi

srcPath="${torrentPath}/${torrentName}"
destDir="/data/Games/Library/import"

echo "[+] Importing \"$torrentName\" to \"$destDir\"" >> "$logFile"

# Hardlink recursively, preserving structure
cp -vrl --no-dereference "$srcPath" "$destDir" >> "$logFile" 2>&1

echo "[✔] Successfully hardlinked \"$torrentName\"" >> "$logFile"