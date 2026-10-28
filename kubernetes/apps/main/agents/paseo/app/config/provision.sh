#!/bin/sh
# `tools` init container: clone ~/.dotfiles on a fresh PVC, then hand over to its
# paseo-bootstrap (class `paseo`, which miserc.toml detects from this mount's
# /etc/paseo). Tools, repos and agent configs all live there. Keep this file dumb.
set -eu
if [ -d "${HOME}/.dotfiles/.git" ]; then
	# paseo-bootstrap pulls too, but only once it exists in the checkout.
	git -C "${HOME}/.dotfiles" pull --ff-only --quiet || echo "[warn] dotfiles pull failed"
else
	git clone https://github.com/h-wb/dotfiles.git "${HOME}/.dotfiles"
fi
exec "${HOME}/.dotfiles/conf.d/paseo/bin/paseo-bootstrap"
