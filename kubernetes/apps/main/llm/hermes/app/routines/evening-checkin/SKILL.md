---
name: evening-checkin
description: Send the evening check-in (ask which of today's tasks got done, list what is overdue, suggest a list for each inbox task). Use when the evening-checkin routine runs.
metadata:
  schedule: "30 20 * * *"
  model: mistral/mistral-large-4
---

# Evening check-in

Read, then ask. Change nothing here: the user answers, and the `task-followup`
skill acts on the answer.

## Read

Call these tools by their exact names with `tool_call`.

1. `mcp__tools__ticktick_list_undone_tasks_by_time_query` with
   `query_command: "today"` and `client_timezone: "America/Toronto"`: tasks
   due today and not done.
2. `mcp__tools__ticktick_filter_tasks` with `filter: {status: [0]}` and
   `client_timezone: "America/Toronto"`: every open task. From it:
   - Overdue: a `dueDate` before today, however old. Drop any that step 1
     already returned.
   - Inbox: a `projectId` that starts with `inbox`.
3. For each task of steps 1 and 2 that has a due date, at most ten:
   `mcp__tools__ticktick_get_comment` with its `project_id` and `task_id`. A
   comment that starts with `Postponed` gives how many times it was moved. If
   the call is refused or fails, go on without the count.

If all three lists are empty, write "Everything due today is done." and stop.

## Write

```
Did you get to these?
1. <task>
2. <task> (postponed 2 times)

Still overdue
3. <task> (due <date>)

Inbox, where do these go?
4. <task> -> <list>
5. <task> -> drop
```

- One numbering across all sections, so the user can answer "1 and 3 done,
  2 tomorrow, inbox ok".
- At most ten tasks in the first two sections, then "and N more". At most five
  inbox tasks.
- For each inbox task, suggest one list from its title: Admin (money, papers,
  accounts), Health, Growth (learning, work), Homelab (servers, software),
  Life (home, people, errands, trips). Suggest `drop` for a bare link or
  something already past.
- For a task postponed three times or more, add on its own line:
  "<task> has slipped <N> times: drop it, make it smaller, or block a time?"
- Leave a section out when it is empty. Nothing else: no advice, no summary.

## Check

Each line comes from a tool result of this run.
