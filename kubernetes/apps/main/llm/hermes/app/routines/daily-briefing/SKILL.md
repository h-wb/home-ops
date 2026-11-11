---
name: daily-briefing
description: Write the morning briefing (today's tasks and events, every overdue task, open homelab tasks, one old undated task to settle). Use when the daily-briefing routine runs or when asked for the briefing.
metadata:
  schedule: "0 7 * * *"
  model: mistral/mistral-large-4
---

# Daily briefing

Read, then write one message. Change nothing: no task is created, completed or
edited here.

## Read, in this order

Call these tools by their exact names with `tool_call`. If a name is not
found, search for the part after `mcp__tools__`. The day is the user's:
timezone `America/Toronto`, whatever the clock here says.

1. `mcp__tools__homelab_tasks_ro_list_tasks` with `status: "open"`: the open
   homelab tasks.
2. `mcp__tools__ticktick_list_undone_tasks_by_time_query` with
   `query_command: "today"` and `client_timezone: "America/Toronto"`: tasks
   due today.
3. `mcp__tools__ticktick_filter_tasks` with `filter: {status: [0]}` and
   `client_timezone: "America/Toronto"`: every open task, dated or not. From
   this one result:
   - Overdue: a `dueDate` before today. However old it is, it counts. Drop any
     that step 2 already returned.
   - Old task candidates: no `dueDate`, no `parentId`, a `projectId` that does
     not start with `inbox`, and no `waiting` tag. Sort them by `modifiedTime`,
     oldest first, and number them from 0. Take the one whose number is
     today's day of the month modulo how many there are. One task, a different
     one each day.
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

Old task: <task> (untouched since <date>). Do it today, give it a date, or drop it?

Missing: <source that failed>
```

- Events first, by start time, then tasks.
- Overdue: oldest due date first.
- One line per item, no notes or descriptions, at most ten per section; then
  "and N more".
- The old task line comes last. The user may ignore it: tomorrow brings
  another one.
- If every section is empty, say that nothing is due today.

## Check

Each line comes from a tool result of this run. Do not add items from memory
or from earlier conversations.
