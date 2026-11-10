---
name: task-reminders
description: Send reminders for tasks and events that start in the next half hour. Use when the task-reminders routine runs.
---

# Task reminders

This runs every half hour. Most runs find nothing and send nothing.

## Read

Call these tools by their exact names with `tool_call`.

1. Work out the window. Start: the current time rounded down to :00 or :30.
   End: start plus 30 minutes. Write both as ISO 8601 with the UTC offset.
2. `mcp__tools__ticktick_list_undone_tasks_by_date` with `search.startDate`
   and `search.endDate` set to the window and
   `client_timezone: "America/Toronto"`: tasks due in the window.
3. `mcp__tools__ticktick_query_calendar_events` with `query.begin` and
   `query.end` set to the window and `client_timezone: "America/Toronto"`:
   events that start in the window.

Drop all-day tasks and all-day events, and events that began before the
window.

If nothing is left, or a call failed, or you cannot tell the current time to
the minute, reply with only `[SILENT]`.

## Write

One line per item, earliest first, times in `America/Toronto`:

```
Coming up
- 14:15 <task or event>
```

Nothing else.

## Check

Each line comes from a tool result of this run and its time is inside the
window.
