---
name: midday-nudge
description: Send the midday nudge (what is still open today). Use when the midday-nudge routine runs.
metadata:
  schedule: "30 12 * * *"
  model: mistral/mistral-medium-latest
---

# Midday nudge

Read, then write one short message. Change nothing here.

## Read

Call these tools by their exact names with `tool_call`.

1. `mcp__tools__ticktick_list_undone_tasks_by_time_query` with
   `query_command: "today"` and `client_timezone: "America/Toronto"`: what is
   still open today.
2. `mcp__tools__ticktick_filter_tasks` with `filter: {status: [0]}` and
   `client_timezone: "America/Toronto"`: every open task. Keep those with a
   `dueDate` before today for the overdue count. Also keep undated priority-5
   tasks (no `dueDate`, no `startDate`, not tagged `waiting`) from Admin,
   Health, Growth or Life for the main list. Resolve these ids
   with `mcp__tools__ticktick_list_projects`; skip undated focus if lookup
   fails. Drop duplicates from step 1.

If nothing is open today, in undated focus or overdue, reply with only
`[SILENT]`.

## Write

```
Still open: today and focus
- <time if it has one> <task>

Overdue: <N>, oldest: <task> (due <date>)
```

- Highest priority first, then by time. At most five tasks, then "and N more".
- Leave the overdue line out when there is none.
- No questions and no advice. The evening check-in asks.

## Check

Each line comes from a tool result of this run.
