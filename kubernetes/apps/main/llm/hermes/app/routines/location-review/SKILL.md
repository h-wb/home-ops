---
name: location-review
description: Review yesterday's location history in Dawarich (stays without a visit, unconfirmed visits, movement without a track) and propose fixes; apply them when the user says yes. Use when the location-review routine runs, or when the user answers it or asks to review or fix a day's location data.
metadata:
  schedule: "5 0 * * *"
  model: mistral/mistral-large-4
---

# Location review

Tracks split at midnight, so the day that just ended is a closed unit. Read
it, then write one message. The scheduled run changes nothing: the user
answers, and the last section acts on the answer.

Call tools by their exact names with `tool_call`. If a name is not found,
search for the part after `mcp__tools__`. The day is the user's: yesterday in
`America/Toronto`, written `YYYY-MM-DD`. Pass `tz: "America/Toronto"` unless
the user said they were somewhere else that day; then pass that zone.

## Read

1. `mcp__tools__dawarich_ops_day_ready` with `day`. Keep the last line
   (`READY` or `NOT READY: ...`). Go on either way.
2. `mcp__tools__dawarich_ops_day_summary` with `day`. If it answers
   `status: running`, call `mcp__tools__dawarich_ops_job_result` with its
   `job_id` until it is done.

The summary lists, in time order:

- `DWELL start -> end minutes ... | label`: a stay. The label is
  `HOME <place id> 'name'`, or the known places within 80 m as
  `id 'name' distance tags Nv` (`Nv` is how many visits that place already
  has), or `(no known place)`.
- `move start -> end metres minutes avg p90 ...`: movement between two stays.
- `existing visits`: `id start -> end status 'name' place=id`. Status `sugg`
  is a visit Dawarich suggested and nobody confirmed.
- `existing tracks`: `id start -> end metres mode`.

If a call fails, say which one and stop.

## Compare

A clean day has one confirmed visit with a place for every stay, one track
for every move, and nothing overlapping. Note every difference:

- A stay of ten minutes or more with no visit over it.
- A visit that is `sugg`, has `place=None`, or starts or ends more than five
  minutes away from its stay.
- Two visits over the same stay.
- A move of more than 300 m with no track over it.
- A track that runs across a stay of ten minutes or more.
- A track that lies wholly inside a `HOME` stay.

A stay of three to five minutes on a long move is slow walking, not a stop:
leave it out.

## Propose

Only visits go in the spec. Tracks are reported as questions: how a leg was
travelled cannot be read from the data.

Put a visit change in the spec only when the place is certain: the stay is
`HOME` (use the id after it), or exactly one known place is listed, or one
listed place has far more visits than the others. Otherwise ask which place
it was.

```json
{"day": "YYYY-MM-DD", "tz": "America/Toronto",
 "edits": {"<visit id>": {"place": <place id>, "start": "HH:MM:SS", "end": "HH:MM:SS"}},
 "creates": [{"place": <place id>, "start": "HH:MM:SS", "end": "HH:MM:SS"}],
 "deletes": [<visit id>]}
```

- Times are the stay's own, on `day`. Prefix `+` for a time after midnight
  the next day and `-` for one the evening before.
- An edit confirms the visit; name only the keys that change.
- `deletes` is for the second of two visits over one stay.
- A stay still going at the end of the summary is not ended here.

If the spec has anything in it, call
`mcp__tools__dawarich_ops_day_apply_check` with `spec`. Keep its last line
(`plan: <token>`). With no plan line, read what it objects to (an overlap, a
visit without a place, a day that is not over), fix the spec once and check
again; if it still has no plan, report what it said.

## Write

```
Location, <weekday> <date>. <READY | NOT READY: reason>

<N> stays, <N> moves.
- <start>-<end> <place or HOME>
- ...

I can fix
1. <what and where, in words>
2. ...

I need you for
3. <stay or move, time, the choice to make>
4. ...

Spec: <the JSON on one line>
Plan: <token>

Answer "apply", or with numbers, for example "apply, 3 the gym, 4 by bike".
```

- Number every item in one sequence. Leave out a section that is empty.
- A day with nothing to fix gets two lines: the heading and "Nothing to fix."
- Keep the spec and the plan in the message exactly as checked: the answer
  needs them.

## When the user answers

1. "apply": call `mcp__tools__dawarich_ops_day_ready` for that day. If it
   says `NOT READY`, say why and wait; points still arriving would undo the
   fix. If `READY`, call `mcp__tools__dawarich_ops_day_apply` with the same
   `spec` and `plan`. If it refuses the plan, run the check again and use the
   new one. Report its `day visits:` line.
2. An answer about a place: add the visit to the spec, check again, show the
   new result and ask before applying.
3. An answer about a track or how a leg was travelled: say it is noted and
   that track fixes are done from the workshop, with the `dawarich-fix-day`
   skill. Do not build tracks from here.

Never call `day_apply` in a scheduled run, and never without a yes for that
exact spec.
