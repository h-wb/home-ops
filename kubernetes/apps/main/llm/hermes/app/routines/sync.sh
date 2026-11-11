#!/bin/sh
# Runs before the assistant starts: keeps Hermes's bundled skills out, lays out the
# skills in this folder and creates the scheduled jobs for those that have a schedule. Never fails the pod: a broken
# routine must not keep the assistant down, so read this container's log.
# Flux substitutes dollar-brace references in this file, so it uses only plain $VAR forms.
hermes=/opt/hermes/bin/hermes
failed=0

mkdir -p "$HERMES_HOME"
$hermes --version
touch "$HERMES_HOME/.no-bundled-skills"
$hermes skills opt-out --remove --yes || failed=1

# Hermes reads its skills settings from its own config file only, not from the
# managed one, so copy that block over. Without it no routine's skill is found.
# Plain awk: the image's Python has no YAML module outside the hermes command.
own="$HERMES_HOME/config.yaml"
touch "$own"
{
  awk '/^skills:/ {skip = 1; next} skip && /^[^ \t]/ {skip = 0} !skip' "$own"
  awk '/^skills:/ {keep = 1; print; next} keep && /^[^ \t]/ {keep = 0} keep' /etc/hermes/config.yaml
} > "$own.new" && cat "$own.new" > "$own" && rm "$own.new" || failed=1
grep -A4 '^skills:' "$own" || failed=1

# A routine is a skill in this folder, shipped as one flat file. Lay each out as
# <name>/SKILL.md, where Hermes looks for skills.
src=/opt/hermes-routines/src
skills=/opt/hermes-routines/skills
for file in "$src"/*.md; do
  name=$(basename "$file" .md)
  mkdir -p "$skills/$name" && cp "$file" "$skills/$name/SKILL.md" || failed=1
done

# A skill with a schedule in its front matter gets a job that loads it, on your
# clock. Jobs are rebuilt on every start; one whose skill is gone is removed.
zone=$(sed -n 's/^timezone: //p' /etc/hermes/config.yaml)
mine="$HERMES_HOME/.routine-jobs"
if [ -f "$mine" ]; then
  while read -r name; do $hermes cron remove "$name" >/dev/null 2>&1 </dev/null; done < "$mine"
fi
: > "$mine"
for file in "$src"/*.md; do
  name=$(basename "$file" .md)
  schedule=$(sed -n 's/^  schedule: "\(.*\)"$/\1/p' "$file")
  model=$(sed -n 's/^  model: //p' "$file")
  [ -n "$schedule" ] || continue
  $hermes cron remove "$name" >/dev/null 2>&1
  $hermes cron create "$schedule" "Run the $name routine." --name "$name" --skill "$name" \
    --timezone "$zone" --deliver matrix --provider litellm --model "$model" || failed=1
  echo "$name" >> "$mine"
done

$hermes cron list || failed=1
if [ "$failed" = 1 ]; then echo "ROUTINES SYNC FAILED: see the errors above"; fi
exit 0
