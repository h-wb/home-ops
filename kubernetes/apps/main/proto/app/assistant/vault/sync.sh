#!/bin/sh
# Keeps /data/vault in step with one Obsidian Sync vault, pull-only: this device downloads
# and never uploads or deletes, so nothing here can change the vault on other devices.
# Credentials come from the BWS item obsidian-headless (OBSIDIAN_AUTH_TOKEN, OBSIDIAN_VAULT,
# and OBSIDIAN_VAULT_PASSWORD for end-to-end encrypted vaults). Get the token by running
# `ob login` once anywhere, then copying ~/.config/obsidian-headless/auth_token.
# Flux substitutes dollar-brace references in this file, so it uses only plain $VAR forms.
set -e
umask 0002 # Seekstone runs as another uid in the same group and must read what ob writes.
export PATH="/tools/ob/node_modules/.bin:$PATH"
device=proto-headless

while [ -z "$OBSIDIAN_AUTH_TOKEN" ] || [ -z "$OBSIDIAN_VAULT" ]; do
  echo "waiting for the obsidian-headless secret (OBSIDIAN_AUTH_TOKEN, OBSIDIAN_VAULT)"
  sleep 300
done

mkdir -p /data/vault "$XDG_CONFIG_HOME"
if ! ob sync-list-local --json | grep -q '"/data/vault"'; then
  set -- --vault "$OBSIDIAN_VAULT" --path /data/vault --device-name "$device" --json
  [ -z "$OBSIDIAN_VAULT_PASSWORD" ] || set -- "$@" --password "$OBSIDIAN_VAULT_PASSWORD"
  ob sync-setup "$@"
fi
# .seekstone is the inbox instance's tool state; it must never become vault content.
ob sync-config --path /data/vault --mode pull-only --device-name "$device" --excluded-folders .seekstone
exec ob sync --path /data/vault --continuous
