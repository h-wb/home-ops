---
name: daily-briefing
description: Write the morning briefing (today's tasks and events, every overdue task, your steps that are ready on the build board, one old undated task to settle). Use when the daily-briefing routine runs or when asked for the briefing.
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

1. The board, read-only: three calls.
   - `mcp__tools__orbit_get_me`: `user.id` is the user's id on the board.
   - `mcp__tools__orbit_list_task_statuses` with
     `project_id: "01a20b1d-1555-72d7-8277-76cfb9212e3e"`: the id of the
     status named `Todo`.
   - `mcp__tools__orbit_list_tasks` with that `project_id`,
     `query: "Your step"` and `limit: 100`: the steps written for the user.
     Keep those whose `assignee_ids` holds the user's id and whose
     `status_id` is Todo's. Never list the project without a query: it is
     too long for one answer.
2. `mcp__tools__ticktick_list_undone_tasks_by_time_query` with
   `query_command: "today"` and `client_timezone: "America/Toronto"`: tasks
   due today.
3. `mcp__tools__ticktick_list_projects`: the id of the list named `Someday`,
   where parked tasks wait. Its tasks stay out of this briefing.
4. `mcp__tools__ticktick_filter_tasks` with `filter: {status: [0]}` and
   `client_timezone: "America/Toronto"`: every open task, dated or not. From
   this one result:
   - Overdue: a `dueDate` before today. However old it is, it counts. Drop any
     that step 2 already returned.
   - Old task candidates: no `dueDate`, no `parentId`, a `projectId` that
     does not start with `inbox` and is not Someday's, and no `waiting` tag.
     Sort them by `modifiedTime`, oldest first, and number them from 0. Take
     the one whose number is today's day of the month modulo how many there
     are. One task, a different one each day. If step 3 failed, skip it.
5. `mcp__tools__ticktick_query_calendar_events` with
   `client_timezone: "America/Toronto"`, `query.begin` set to today at 00:00
   and `query.end` to tomorrow at 00:00 in that timezone: today's events.
6. Focus: pick at most three tasks from steps 2 and 4 for today. Tasks due
   today with a time first, then today's other tasks by priority, then the
   oldest overdue, then open tasks with priority 5 and no date: the focus
   confirmed on an earlier day. Never one in Someday or tagged `waiting`,
   and never the old task. Fewer than three when there are fewer.

If a call fails, go on with the others and say which source is missing.

## Write

Plain text for a phone, in this shape. Leave a section out when it is empty.

```
Good morning. <weekday>, <date>.

Today
- <time> <event>
1. <task>

Overdue
2. <task> (due <date>)

Still in focus
3. <task>

Board, your steps
- HOMEL-<n> <title>

Focus: 1, 2, 3. Reply ok, or other numbers.

Old task: 4. <task> (untouched since <date>). Add it to the focus, give it a date, or drop it?

Missing: <source that failed>
```

- Number every TickTick task, Today, Overdue, Still in focus and the old
  task, in one sequence, so the user can answer with numbers. Events and
  board steps get a dash.
- Still in focus: only the undated focus tasks picked in step 6.
- The focus line names at most three numbers. Leave it out when there is no
  task.
- Events first, by start time, then tasks.
- Board steps: the number and the title only, lowest number first, at most
  five, then "and N more on the board". The board is read here, never
  written.
- Overdue: oldest due date first.
- One line per item, no notes or descriptions, at most ten per section; then
  "and N more".
- The old task line comes last. The user may ignore it: tomorrow brings
  another one.
- If every section is empty, say that nothing is due today.

## Check

Each line comes from a tool result of this run. Do not add items from memory
or from earlier conversations.
