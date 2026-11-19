---
name: location-review
description: Reconcile yesterday's location history in Dawarich (visits, places, how each leg was travelled, noise tracks) and apply the fix when the user says yes. Use when the location-review routine runs, or when the user answers it or asks to review, fix or reconcile a day's location data.
metadata:
  schedule: "5 0 * * *"
  model: mistral/mistral-large-4
---

# Location review

One day at a time. A tool reads the day and proposes the whole fix; you ask
the user what it could not know, hand the answers back to it, and apply the
result when the user says yes. The scheduled run changes nothing.

Call tools by their exact names with `tool_call`. If a name is not found,
search for the part after `mcp__tools__`. The day is the user's: yesterday in
`America/Toronto`, written `YYYY-MM-DD`. Pass `tz: "America/Toronto"` unless
the user said they were somewhere else that day; then pass that zone. If a
tool answers `status: running`, call `mcp__tools__dawarich_ops_job_result`
with its `job_id` until it is done. If a call fails, say which one and what
its `error:` line says, and stop.

## Read

1. `mcp__tools__dawarich_ops_day_ready` with `day`. Keep the last line
   (`READY` or `NOT READY: ...`). Go on either way.
2. `mcp__tools__dawarich_ops_day_plan` with `day`.
3. `mcp__tools__dawarich_ops_days_scan` with `from` seven days before `day`
   and `to` the day before `day`. Keep only the dates it lists.

If the plan prints a line starting ` warn the clocks change`, call steps 1
and 2 again with the `tz` that line names, and use that `tz` for every later
call about this day.

The plan lists:

- `stays`: `start -> end  minutes  place  what changes` (`visit N ok`, `visit
  N: confirm, place, start, end`, `new visit`, or `place?` when it must ask).
- `legs`: `start -> end  metres  minutes  speeds  mode  new|kept`. A mode
  with `?` is a guess.
- `tracks`: tracks inside a stay it removes as jitter, and tracks the legs
  replace.
- `questions`: one per line, each starting with its key in brackets:
  `[stop 18:27]`, `[leg 13:37]`, `[track 45946]`.
- `note:` lines, and the last two lines: `nothing to fix` or `next: ...`,
  then `SPEC {...}`.

## Write

A day with `nothing to fix`:

```
Location, <weekday> <date>. <READY | NOT READY: reason>
Nothing to fix.
```

Otherwise:

```
Location, <weekday> <date>. <READY | NOT READY: reason>

<N> stays, <N> legs.
- <start>-<end> <place>
- ...

I will fix
- <each change, in words: "confirm the gym visit 17:31-18:22", "rebuild the walk home", "remove 2 noise tracks at home">

I need you for
1. [stop 18:27] <the question in your words, with the places it offers>
2. [leg 13:37] <...>

Answer with the numbers, for example "1 the vape shop, 2 streetcar", then "apply".
```

- Number the questions in order and keep each key in brackets exactly as
  printed: the answer needs it.
- With no question, leave that section out and end with: `Answer "apply".`
- Put a `note:` line in your own words under the stays when it says a visit
  was left alone or a leg has a long gap without points.
- If the scan listed other days, add one last line:
  `Also still open: <dates>.`
- Do not print the spec. Do not call `day_apply_check` in the scheduled run.

## When the user answers

Turn each answer into the value for its key, and call
`mcp__tools__dawarich_ops_day_plan` again with `day`, `tz` and `answers`, an
object from key to value:

| The user says                                                                    | Value                                                         |
| -------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| a place the question offered                                                     | its id, a number: `2187`                                      |
| a place it did not offer                                                         | `{"new": "Name", "tags": ["Bar"]}`                            |
| just passing, waiting, not a stop                                                | `"skip"`                                                      |
| walked / by bike / streetcar or bus / metro, subway or train / car, Uber or taxi | `"walking"` / `"cycling"` / `"bus"` / `"train"` / `"driving"` |
| GPS noise / a real outing                                                        | `"noise"` / `"keep"`                                          |

For a place it did not offer, first call
`mcp__tools__dawarich_ops_place_lookup` with `q` the name and `latlon` the
`lat,lon` printed in the question. If a hit says `already place #N`, answer
`N`. If a hit matches the name, add its coordinates:
`{"new": "Name", "tags": ["Bar"], "lat": 43.647611, "lon": -79.395621}`.
With no hit, leave `lat` and `lon` out: the place goes where the stay was.
Tags say what the place is: `Restaurant`, `Bar`, `Cafe`, `Fast Food`, `Shop`,
`Gym`, `Park`, `Hotel`, `Venue`, `Transit`, `Work`, `Friends and Family`. If
you are not sure, ask.

Then:

1. The new plan still has questions: ask them, numbered again.
2. It has none: call `mcp__tools__dawarich_ops_day_apply_check` with `spec`,
   the JSON after `SPEC ` on the plan's last line, unchanged. If the result
   has no `plan:` line, read its `problem:` or `error:` lines and tell the
   user what they say; do not try another spec.
3. With a `plan:` line, report its `day visits:` line in words. If the user
   has already said "apply", go on; otherwise ask `Apply?` and wait.
4. To apply: `mcp__tools__dawarich_ops_day_ready` first. If it says `NOT
   READY`, say why and wait: points still arriving would undo the fix. If
   `READY`, call `mcp__tools__dawarich_ops_day_apply` with the same `spec`
   and the `plan` token. If it refuses the plan, run the check again and use
   the new one. Report `done (committed)` and the `day visits:` line.

What this routine does not do: a stay that was really two places, a ride
that changed mode halfway, a day with no points at all. Say it is noted and
that it needs the workshop (`dawarich-fix-day`, or `dawarich-reconstruct-day`
for missing data). Do not write or edit a spec by hand.

Never call `day_apply` in a scheduled run, and never without a yes for that
day.
