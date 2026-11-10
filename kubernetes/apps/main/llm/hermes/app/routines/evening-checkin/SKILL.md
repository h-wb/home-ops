---
name: evening-checkin
description: Send the evening check-in (ask which of today's tasks got done). Use when the evening-checkin routine runs.
---

# Evening check-in

Read, then ask. Change nothing here: the user answers, and the `task-followup`
skill acts on the answer.

## Read

Call these tools by their exact names with `tool_call`.

1. `mcp__tools__ticktick_list_undone_tasks_by_time_query` with
   `query_command: "today"` and `client_timezone: "America/Toronto"`: tasks
   due today and not done.
2. The same tool with `query_command: "last7day"`: overdue tasks. Drop any
   that step 1 already returned.
3. For each task, at most ten: `mcp__tools__ticktick_get_comment` with its
   `project_id` and `task_id`. A comment that starts with `Postponed` gives
   how many times it was moved. If the call is refused or fails, go on without
   the count.

If both lists are empty, write "Everything due today is done." and stop.

## Write

```
Did you get to these?
1. <task>
2. <task> (postponed 2 times)

Still overdue
3. <task> (due <date>)
```

- One numbering across both sections, so the user can answer "1 and 3 done,
  2 tomorrow".
- At most ten tasks, then "and N more".
- For a task postponed three times or more, add on its own line:
  "<task> has slipped <N> times: drop it, make it smaller, or block a time?"
- Nothing else: no advice, no summary.

## Check

Each line comes from a tool result of this run.
