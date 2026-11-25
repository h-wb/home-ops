#!/bin/sh
# Writes the skills of the groups the assistant takes (SKILL_GROUPS, in job.yaml),
# from h-wb/skills at a pinned commit, to the volume that each Hermes pod mounts
# read-only at /opt/shared-skills. A group is groups/<group>/<name> in the
# catalogue, a relative link to skills/<name>; the volume gets the skill itself.
# The agent pods never fetch it themselves: their egress is limited to DNS,
# LiteLLM, Memini and Telegram. Flux substitutes dollar-brace references in this
# file, so it uses only plain $VAR forms.
set -eu
base="https://codeload.github.com/h-wb/skills/tar.gz/$SKILLS_REF"
curl -fsSLo /tmp/skills.tar.gz "$base"
echo "$SKILLS_TAR_SHA256  /tmp/skills.tar.gz" | sha256sum -c -
mkdir -p /tmp/skills
tar -xzf /tmp/skills.tar.gz -C /tmp/skills
groups="/tmp/skills/skills-$SKILLS_REF/groups"
# Fail before touching the volume if a declared group is not in the catalogue,
# or one of its entries is not a skill. A skill in two groups is taken once.
names=""
sources=""
for group in $SKILL_GROUPS; do
  test -d "$groups/$group" || { echo "no group $group at $SKILLS_REF"; exit 1; }
  for entry in "$groups/$group"/*; do
    name=$(basename "$entry")
    test -f "$entry/SKILL.md" || { echo "group $group: no skill $name at $SKILLS_REF"; exit 1; }
    case " $names " in *" $name "*) continue ;; esac
    names="$names $name"
    sources="$sources $entry"
  done
done
# Everything is written inside the volume: the root filesystem is read-only and
# /skills is a mount point, so it cannot be renamed. Each skill is swapped by
# rename, so a pod reading mid-sync never sees a half-written one.
rm -rf /skills/.new /skills/.old
mkdir /skills/.new
for entry in $sources; do
  cp -RL "$entry" "/skills/.new/$(basename "$entry")"  # the skill, not the group's link
done
chmod -R a+r,go-w /skills/.new
for name in $names; do
  if [ -e "/skills/$name" ]; then mv "/skills/$name" /skills/.old; fi
  mv "/skills/.new/$name" "/skills/$name"
  rm -rf /skills/.old
done
rmdir /skills/.new
# A skill no longer in a taken group leaves the volume too.
for old in /skills/*; do
  case " $names " in *" $(basename "$old") "*) ;; *) rm -rf "$old" ;; esac
done
echo "skills $names (groups $SKILL_GROUPS) from h-wb/skills $SKILLS_REF written"
