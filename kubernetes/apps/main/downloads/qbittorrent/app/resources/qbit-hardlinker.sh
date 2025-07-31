#!/bin/bash

set -euo pipefail

torrentName=$1      # "%N" - Torrent name
torrentPath=$2      # "%D" - Torrent data directory
torrentCategory=$3  # "%L" - Torrent category
torrentTags=$4      # "%G" - Tags (comma-separated)

logDir="$(dirname "$0")"
logFile="$logDir/qbit-games-importer.log"

# Only proceed if the category is 'games'
if [[ "$torrentCategory" != "games" ]]; then
  echo "[!] Skipped \"$torrentName\" - category is \"$torrentCategory\"" >> "$logFile"
  exit 0
fi

# Set default destination
destDir="/data/Games/Library/import"

# Look for tag matching roms:$platform
IFS=',' read -ra tagArray <<< "$torrentTags"
for tag in "${tagArray[@]}"; do
  if [[ "$tag" =~ ^roms:(.+)$ ]]; then
    platform="${BASH_REMATCH[1]}"
    destDir="/data/Games/Library/roms/$platform"
    echo "[+] Matched platform tag: $platform" >> "$logFile"
    break
  fi
done

srcPath="${torrentPath}/${torrentName}"

echo "[+] Importing \"$torrentName\" to \"$destDir\"" >> "$logFile"
mkdir -p "$destDir"

# Hardlink recursively, preserving structure
cp -vrl "$srcPath" "$destDir" >> "$logFile" 2>&1

echo "[✔] Successfully hardlinked \"$torrentName\"" >> "$logFile"