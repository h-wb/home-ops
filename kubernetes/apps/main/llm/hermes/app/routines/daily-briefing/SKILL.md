---
name: daily-briefing
description: Write the morning briefing (today's tasks and events, overdue tasks, open homelab tasks). Use when the daily-briefing routine runs or when asked for the briefing.
---

# Daily briefing

Read, then write one message. Change nothing: no task is created, completed or
edited here.

## Read, in this order

Call these tools by their exact names with `tool_call`. If a name is not
found, search for the part after `mcp__tools__`. The day is the user's:
timezone `America/Toronto`, whatever the clock here says.

1. `mcp__tools__homelab-tasks-ro_list_tasks` with `status: "open"`: the open
   homelab tasks.
2. `mcp__tools__ticktick_list_undone_tasks_by_time_query` with
   `query_command: "today"` and `client_timezone: "America/Toronto"`: tasks
   due today.
3. The same tool with `query_command: "last7day"`: tasks that are overdue.
   Drop any that step 2 already returned.
4. `mcp__tools__ticktick_query_calendar_events` with
   `client_timezone: "America/Toronto"`, `query.begin` set to today at 00:00
   and `query.end` to tomorrow at 00:00 in that timezone: today's events.

If a call fails, go on with the others and say which source is missing.

## Write

Plain text for a phone, in this shape. Leave a section out when it is empty.

```
Good morning. <weekday>, <date>.

Today
- <time> <event>
- <task>

Overdue
- <task> (due <date>)

Homelab
- <task title>

Missing: <source that failed>
```

- Events first, by start time, then tasks.
- One line per item, no notes or descriptions, at most ten per section; then
  "and N more".
- If every section is empty, say that nothing is due today.

## Check

Each line comes from a tool result of this run. Do not add items from memory
or from earlier conversations.
