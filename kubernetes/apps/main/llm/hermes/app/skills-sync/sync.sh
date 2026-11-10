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
# Everything is written inside the volume: the root filesystem is read-only and
# /skills is a mount point, so it cannot be renamed. Each skill is swapped by
# rename, so a pod reading mid-sync never sees a half-written one.
rm -rf /skills/.new /skills/.old
cp -r "$skills" /skills/.new
chmod -R a+r,go-w /skills/.new
for new in /skills/.new/*; do
  name=$(basename "$new")
  if [ -e "/skills/$name" ]; then mv "/skills/$name" /skills/.old; fi
  mv "$new" "/skills/$name"
  rm -rf /skills/.old
done
rmdir /skills/.new
# Skills that left dotfiles leave the volume too.
for old in /skills/*; do
  [ -e "$skills/$(basename "$old")" ] || rm -rf "$old"
done
echo "dotfiles skills $DOTFILES_REF written"
