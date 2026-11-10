#!/bin/sh
# Runs before the assistant starts: keeps Hermes's bundled skills out and creates
# the scheduled jobs for the routines in this folder. Never fails the pod: a broken
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

# routine <name> <schedule> <model>: the job loads the skill of the same name.
# Schedules are on your clock, not the pod's.
routine() {
  $hermes cron remove "$1" >/dev/null 2>&1
  $hermes cron create "$2" "Run the $1 routine." --name "$1" --skill "$1" \
    --timezone America/Toronto --deliver telegram --provider litellm --model "$3" || failed=1
}

routine daily-briefing "0 7 * * *" mistral/mistral-large-4
routine midday-nudge "30 12 * * *" mistral/mistral-medium-latest
routine evening-checkin "30 20 * * *" mistral/mistral-large-4
# Every half hour from 08:00 to 21:30; silent unless something is coming up.
routine task-reminders "*/30 8-21 * * *" mistral/mistral-medium-latest

$hermes cron list || failed=1
if [ "$failed" = 1 ]; then echo "ROUTINES SYNC FAILED: see the errors above"; fi
exit 0
