---
name: midday-nudge
description: Send the midday nudge (what is still open today). Use when the midday-nudge routine runs.
---

# Midday nudge

Read, then write one short message. Change nothing here.

## Read

Call these tools by their exact names with `tool_call`.

1. `mcp__tools__ticktick_list_undone_tasks_by_time_query` with
   `query_command: "today"` and `client_timezone: "America/Toronto"`: what is
   still open today.
2. The same tool with `query_command: "last7day"`: what is overdue. Drop any
   that step 1 already returned.

If nothing is open today and nothing is overdue, reply with only `[SILENT]`.

## Write

```
Still open today
- <time if it has one> <task>

Overdue: <N>, oldest: <task> (due <date>)
```

- Highest priority first, then by time. At most five tasks, then "and N more".
- Leave the overdue line out when there is none.
- No questions and no advice. The evening check-in asks.

## Check

Each line comes from a tool result of this run.
