---
name: task-followup
description: Act on what the user says about their tasks, such as an answer to the evening check-in, the briefing's old task or a reminder (done, not done, later, tomorrow, drop it, file the inbox). Use whenever the user reports on, postpones, reschedules, drops or files a TickTick task.
---

# Task follow-up

The user tells you what happened to their tasks. Update TickTick to match,
and keep track of what keeps slipping.

Call tools by their exact names with `tool_call`. The user's timezone is
`America/Toronto`; pass it as `client_timezone`. Every date or time you write
is Toronto time: set `timeZone: "America/Toronto"` on the task.

## Find the task

You need each task's `id` and `projectId`. If you do not have them from this
conversation, call `mcp__tools__ticktick_filter_tasks` with
`filter: {status: [0]}` and match by title. A number in the user's answer
refers to the numbered list in the message they answer, the briefing or the
check-in. If two tasks could match, ask which one.

## Done

`mcp__tools__ticktick_complete_task` with `project_id` and `task_id`.

## Not done, with a new date from the user

1. `mcp__tools__ticktick_get_comment` for the task. Count the comments that
   start with `Postponed`: that is N so far.
2. If N is 2 or more, do not move it yet. Say it has slipped N + 1 times and
   ask: drop it, make it smaller, or block a time for it? Then do what the
   user picks (see below).
3. Otherwise `mcp__tools__ticktick_update_task` with `task_id` and
   `task: {id, projectId, dueDate, timeZone}`. Keep the time of day; keep an
   all-day task all-day. If it has a `startDate`, move it by the same amount.
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

## Today's focus

After the briefing the user confirms its focus ("ok") or names other numbers.
At most three tasks; if more are named, ask which three.

1. `mcp__tools__ticktick_filter_tasks` with
   `filter: {status: [0], priority: [5]}`: tasks still marked high from an
   earlier day.
2. One `mcp__tools__ticktick_batch_update_tasks` call: `priority: 0` on each
   task from step 1 that is not picked today, `priority: 5` on each picked
   task. A picked task with no date also gets `dueDate` today, `isAllDay:
true`, so it shows in Today.

High priority means today's focus and nothing else.

## The briefing's old task

The morning briefing offers one undated task. The answer:

- Today: `mcp__tools__ticktick_update_task` with `dueDate` today,
  `isAllDay: true`.
- A date: that date, all-day unless the user gives a time.
- Drop it: `status: -1`.
- No answer or "not now": change nothing. Tomorrow's briefing offers another.

## The weekly review

Answers to the Sunday review, by number:

- Inbox and overdue items: as in "File the inbox" and "The briefing's old
  task".
- Waiting: "done" completes it. "Follow up" removes the `waiting` tag and sets
  `dueDate` tomorrow, all-day. "Still waiting": nothing.
- A project's next step: `mcp__tools__ticktick_create_task` with the step as
  `title`, the parent's `projectId`, `parentId` the parent's id, and the date
  the user gives (or propose the lightest day, as above). A project with no
  parent task: create the parent first in the list named by the note's
  `area`, title = the note's name, content =
  `obsidian://open?vault=Vault&file=<path without .md, URL-encoded>`; then
  the step; then set the note's `ticktick` with the `vault-notes` skill.
- Back to backlog: the `vault-notes` skill sets the project's `status` to
  `backlog`.
- An idea: "task" creates it in the list named by the idea's `area`, then
  `vault-notes` sets the idea's `status` to `archived` and archives it.
  "project" has `vault-notes` set `categories: ["[[Projects]]"]` and
  `status: ["backlog"]`. "leave": nothing.

When every answer is handled, the `vault-notes` skill writes
`AI/<YYYY-MM-DD> Weekly review.md`: one line per item, what was decided.

## File the inbox

The user accepts the check-in's suggestions ("inbox ok") or gives a list per
number ("4 Life, 5 Admin").

1. `mcp__tools__ticktick_list_projects`: the list ids, matched by name.
2. `mcp__tools__ticktick_move_task` with one `moves` entry per task:
   `{taskId, fromProjectId, toProjectId}`, all in one call.
3. A task marked `drop`: `status: -1`, as above.

## Report

After the writes, one line per task: what changed and its new date or list.
If a call was refused or failed, say which task was not changed.
