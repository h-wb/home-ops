---
name: location-review
description: Review yesterday's location history in Dawarich each morning, fix what needs no one, ask the user the rest, and apply their answers or corrections. Use when the location-review routine runs, or when the user answers it or asks to review, fix, change or correct a day's location data.
metadata:
  schedule: "30 8 * * *"
  model: mistral/mistral-large-4
---

# Location review

The tools do the thinking. They read the day, write the message for the user
and take the user's reply as typed. Your job is to pass text along unchanged
and to pick the right tool.

Call tools by their exact names with `tool_call`. If a name is not found,
search for the part after `mcp__tools__`. A day is written `YYYY-MM-DD`. Do
not pass `tz` unless the user said they were in another time zone that day.
If a tool answers `status: running`, call
`mcp__tools__dawarich_ops_job_result` with its `job_id` until it is done. If
a call fails, say which one and what its `error:` line says, and stop.

Every tool prints a block between the lines `MESSAGE` and `END MESSAGE`.
That block is for the user. Send it exactly as printed: same lines, same
numbers, nothing added inside it, nothing left out.

## The scheduled run

One call: `mcp__tools__dawarich_ops_day_auto` with no arguments. It looks at
yesterday and the week before, fixes by itself the days where there is
nothing to ask, and changes nothing else.

Its first line starts with `AUTO`. Send:

```
Location: <the first line, without the word AUTO>

<the MESSAGE block>
```

Then, if it printed them, the `ALSO FIXED:` line and the `STILL OPEN` lines,
as printed. Do not call any other tool in the scheduled run.

## When the user replies with answers

The message numbers its questions. The user answers with those numbers
("1 bike, 2 passing, 3 the cafe"), or says "ok" to take the defaults.

1. `mcp__tools__dawarich_ops_day_fix_check` with `day` (the date of the
   message they are answering) and `reply`, the user's text exactly as they
   typed it. Do not translate it and do not turn it into ids.
2. If the result has a `plan:` line, call `mcp__tools__dawarich_ops_day_fix`
   with the same `day`, the same `reply`, and `plan`, the token on that
   line. Then send the MESSAGE block it prints: that is the day as it now
   stands.
3. If the result has no `plan:` line, send its MESSAGE block and the line
   under it that starts with `not applied` or `nothing to fix`. A question
   still open means the user has to answer it: ask only that.

If the tool says `error: cannot read`, the reply was not a list of numbered
answers. It is probably a correction: see the next section.

## When the user says something was wrong

"The 14:12 stop was the bakery", "I took the bus", "that wasn't a stop".
This works on any day, fixed or not. Pick one row, fill it in with the times
from the message's timeline, and call
`mcp__tools__dawarich_ops_day_change_check` with `day` and `change`:

| The user says                         | `change`                                                              |
| ------------------------------------- | --------------------------------------------------------------------- |
| a visit was at another place          | `{"op": "place", "at": "14:12", "place": "the name they gave"}`       |
| a leg was travelled another way       | `{"op": "mode", "at": "13:58", "mode": "bus"}`                        |
| one visit was really two places       | `{"op": "split", "at": "19:00", "first": "name", "second": "name"}`   |
| several legs were one ride            | `{"op": "merge", "from": "13:40", "to": "14:10"}`                     |
| a visit was no stop: traffic, waiting | `{"op": "not_a_stop", "at": "13:43"}`                                 |
| there was a stop that is missing      | `{"op": "stop", "from": "14:28", "to": "14:40", "place": "the name"}` |

`at` is the start time of the visit or leg on the timeline. A place is the
name the user said; the tool finds it. For `split`, add `"cut": "20:30"`
only when the user says when they changed place, or when the tool asks for
it.

Then tell the user the `change:` line in your own words. With a `plan:`
line, call `mcp__tools__dawarich_ops_day_change` with the same `day`, the
same `change` and that `plan`, and send the MESSAGE block it prints. Without
one, say what its `error:` or `problem:` line says. One correction per
call; for two corrections, do the first to the end, then the second.

## When the user asks about a day

`mcp__tools__dawarich_ops_day_plan` with `day`, then send its MESSAGE block.
Use it for a date on the `STILL OPEN` list, or when the user asks what a day
looks like.

## Rules

- Never call `day_fix` or `day_change` without the `plan:` token from its
  `_check` call for the same arguments, made in this conversation.
- Never write a spec, and never call `day_apply`.
- A day that says `not settled` is still receiving points. Tell the user and
  leave it: the next morning's run looks at it again.
- A day with no points at all, or a ride that changed mode halfway, is not
  for this routine. Say it is noted and that it needs the workshop
  (`dawarich-fix-day`, or `dawarich-reconstruct-day` for missing data).
