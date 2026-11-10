#!/bin/sh
# Writes the shared skills folder (h-wb/dotfiles, conf.d/ai/skills), pinned, to the
# volume that each Hermes pod mounts read-only at /opt/dotfiles-skills. The agent
# pods never fetch it themselves: their egress is limited to DNS, LiteLLM, Memini
# and Telegram. Flux substitutes dollar-brace references in this file, so it uses
# only plain $VAR forms.
set -eu
base="https://codeload.github.com/h-wb/dotfiles/tar.gz/$DOTFILES_REF"
curl -fsSLo /tmp/dotfiles.tar.gz "$base"
echo "$DOTFILES_TAR_SHA256  /tmp/dotfiles.tar.gz" | sha256sum -c -
mkdir -p /tmp/dotfiles
tar -xzf /tmp/dotfiles.tar.gz -C /tmp/dotfiles
skills="/tmp/dotfiles/dotfiles-$DOTFILES_REF/conf.d/ai/skills"
# Fail instead of mounting an empty folder: every skill is a <name>/SKILL.md.
test -n "$(find "$skills" -name SKILL.md -print -quit)"
rm -rf /skills.new
cp -r "$skills" /skills.new
# The directory may predate this Job (kubelet creates mount points), so set files only.
chmod -R a+r,go-w /skills.new
# Swap, so a pod starting mid-sync never sees a half-written tree.
rm -rf /skills.old
if [ -d /skills ]; then mv /skills /skills.old; fi
mv /skills.new /skills
rm -rf /skills.old
echo "dotfiles skills $DOTFILES_REF written"
