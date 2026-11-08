#!/bin/sh
# `tools` init container: clone ~/.dotfiles on a fresh PVC and run its paseo-bootstrap
# (class `paseo`, which miserc.toml detects from this mount's /etc/paseo) for the CLIs,
# repos and shell. Agent config is home-ops': merge /etc/paseo/config (the overlay's
# config/ dir) into the files agents also keep state in. OpenCode reads its file in
# place through OPENCODE_CONFIG.
set -eu
if [ -d "$HOME/.dotfiles/.git" ]; then
	# paseo-bootstrap pulls too, but only once it exists in the checkout.
	git -C "$HOME/.dotfiles" pull --ff-only --quiet || echo "[warn] dotfiles pull failed"
else
	git clone https://github.com/h-wb/dotfiles.git "$HOME/.dotfiles"
fi
"$HOME/.dotfiles/conf.d/paseo/bin/paseo-bootstrap"

# Deep merge: our keys win, everything else the agents wrote is kept.
merge() {
	node -e '
const fs = require("fs"), path = require("path"), [dst, src] = process.argv.slice(1);
const read = (f) => fs.existsSync(f) ? JSON.parse(fs.readFileSync(f, "utf8")) : {};
const obj = (v) => v && typeof v === "object" && !Array.isArray(v);
const merge = (a, b) => { for (const [k, v] of Object.entries(b)) a[k] = obj(v) && obj(a[k]) ? merge(a[k], v) : v; return a; };
fs.mkdirSync(path.dirname(dst), { recursive: true });
fs.writeFileSync(dst, JSON.stringify(merge(read(dst), read(src)), null, 2) + "\n");
' "$1" "$2"
}
merge "$HOME/.paseo/config.json" /etc/paseo/config/paseo.json
# The image sets CLAUDE_CONFIG_DIR=~/.claude; Claude then reads its .claude.json there.
merge "${CLAUDE_CONFIG_DIR:-$HOME}/.claude.json" /etc/paseo/config/claude.json
