#!/bin/sh
# Writes the skills the assistant declares (SKILLS, in job.yaml), from h-wb/skills
# at a pinned commit, to the volume that each Hermes pod mounts read-only at
# /opt/shared-skills. The agent pods never fetch it themselves: their egress is
# limited to DNS, LiteLLM, Memini and Telegram. Flux substitutes dollar-brace
# references in this file, so it uses only plain $VAR forms.
set -eu
base="https://codeload.github.com/h-wb/skills/tar.gz/$SKILLS_REF"
curl -fsSLo /tmp/skills.tar.gz "$base"
echo "$SKILLS_TAR_SHA256  /tmp/skills.tar.gz" | sha256sum -c -
mkdir -p /tmp/skills
tar -xzf /tmp/skills.tar.gz -C /tmp/skills
catalogue="/tmp/skills/skills-$SKILLS_REF/skills"
# Fail before touching the volume if a declared skill is not in the catalogue.
for name in $SKILLS; do
  test -f "$catalogue/$name/SKILL.md" || { echo "no skill $name at $SKILLS_REF"; exit 1; }
done
# Everything is written inside the volume: the root filesystem is read-only and
# /skills is a mount point, so it cannot be renamed. Each skill is swapped by
# rename, so a pod reading mid-sync never sees a half-written one.
rm -rf /skills/.new /skills/.old
mkdir /skills/.new
for name in $SKILLS; do
  cp -r "$catalogue/$name" "/skills/.new/$name"
done
chmod -R a+r,go-w /skills/.new
for name in $SKILLS; do
  if [ -e "/skills/$name" ]; then mv "/skills/$name" /skills/.old; fi
  mv "/skills/.new/$name" "/skills/$name"
  rm -rf /skills/.old
done
rmdir /skills/.new
# A skill no longer declared leaves the volume too.
for old in /skills/*; do
  case " $SKILLS " in *" $(basename "$old") "*) ;; *) rm -rf "$old" ;; esac
done
echo "skills $SKILLS from h-wb/skills $SKILLS_REF written"
