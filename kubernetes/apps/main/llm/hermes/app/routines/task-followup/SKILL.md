---
name: task-followup
description: Act on what the user says about their tasks, such as an answer to the evening check-in or to a reminder (done, not done, later, tomorrow, drop it). Use whenever the user reports on, postpones or reschedules a TickTick task.
---

# Task follow-up

The user tells you what happened to their tasks. Update TickTick to match,
and keep track of what keeps slipping.

Call tools by their exact names with `tool_call`. The user's timezone is
`America/Toronto`; pass it as `client_timezone`.

## Find the task

You need each task's `id` and `projectId`. If you do not have them from this
conversation, call `mcp__tools__ticktick_list_undone_tasks_by_time_query` with
`query_command: "today"`, then with `"last7day"`, and match by title. A number
in the user's answer refers to the numbered list in the last check-in. If two
tasks could match, ask which one.

## Done

`mcp__tools__ticktick_complete_task` with `project_id` and `task_id`.

## Not done, with a new date from the user

1. `mcp__tools__ticktick_get_comment` for the task. Count the comments that
   start with `Postponed`: that is N so far.
2. If N is 2 or more, do not move it yet. Say it has slipped N + 1 times and
   ask: drop it, make it smaller, or block a time for it? Then do what the
   user picks (see below).
3. Otherwise `mcp__tools__ticktick_update_task` with `task_id` and
   `task: {id, projectId, dueDate}`. Keep the time of day; keep an all-day
   task all-day. If it has a `startDate`, move it by the same amount.
4. `mcp__tools__ticktick_add_comment` with
   `title: "Postponed <N + 1> times. <old date> -> <new date>"`.

## Not done, no date given

Propose one date, do not pick silently.

1. `mcp__tools__ticktick_list_undone_tasks_by_date` for the next seven days.
2. Pick the day with the fewest tasks among the next three, later if all
   three are full. A task that is small and was due today goes to tomorrow.
3. Ask in one line: "Move <task> to <weekday>? It is your lightest day."
4. On yes, follow "Not done, with a new date".

## A task that keeps slipping

- Drop it: `mcp__tools__ticktick_update_task` with `task: {id, projectId,
  status: -1}`.
- Make it smaller: ask for the first step, rename the task to that step with
  `title`, and move it to tomorrow.
- Block a time: ask when, set `dueDate` to that time with `isAllDay: false`
  and `reminders: ["TRIGGER:-PT15M"]`.

Add the `Postponed` comment in the last two cases as well.

## Report

After the writes, one line per task: what changed and its new date. If a call
was refused or failed, say which task was not changed.
