#!/bin/sh
# `tools` init container: clone ~/.dotfiles on a fresh PVC, then hand over to its
# paseo-bootstrap (class `paseo`, which miserc.toml detects from this mount's
# /etc/paseo). Tools, repos and agent configs all live there. Keep this file dumb.
set -eu
[ -d "${HOME}/.dotfiles/.git" ] || git clone https://github.com/h-wb/dotfiles.git "${HOME}/.dotfiles"
exec "${HOME}/.dotfiles/conf.d/paseo/bin/paseo-bootstrap"
