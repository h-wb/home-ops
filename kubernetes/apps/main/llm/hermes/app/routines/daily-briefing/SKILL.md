---
name: daily-briefing
description: Write the morning briefing (today's tasks and events, every overdue task, open homelab tasks, up to three focus tasks each with a first step, one old undated task to settle). Use when the daily-briefing routine runs or when asked for the briefing.
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
3. `mcp__tools__ticktick_list_projects`: resolve the unique ids of Admin,
   Health, Growth, Homelab and Life. Only these personal lists supply focus
   and old task candidates; never guess ids or include Build or Someday.
4. `mcp__tools__ticktick_filter_tasks` with `filter: {status: [0]}` and
   `client_timezone: "America/Toronto"`: every open task, dated or not. From
   this one result:
   - Overdue: a `dueDate` before today. However old it is, it counts. Drop any
     that step 2 already returned.
   - Old task candidates: in a personal list from step 3, no `dueDate`,
     `startDate`, `parentId` or `waiting` tag. After choosing focus in step 6,
     remove those picks, sort by `modifiedTime` oldest first and number from 0. Take today's day of the month modulo the number of candidates. Skip
     if there are none.
5. `mcp__tools__ticktick_query_calendar_events` with
   `client_timezone: "America/Toronto"`, `query.begin` set to today at 00:00
   and `query.end` to tomorrow at 00:00 in that timezone: today's events.
6. Focus: pick at most three open tasks from the personal lists in step 3,
   excluding `waiting`. Prefer commitments due today, then overdue work,
   then fill from actionable undated tasks in step 4 (carry over an open
   focus task before picking a new one). Do not propose the same task as both
   focus and the old task. If list lookup fails, skip both suggestions.
7. A first step for each focus task, so that starting takes no thought:
   - If step 4 returned open, unblocked subtasks, use the one with the lowest
     `sortOrder`. If it takes longer than ten minutes, give its first action
     instead of repeating the whole subtask.
   - Otherwise write one from the title: a single action of ten minutes or
     less, starting with a verb, that can be done without deciding anything
     first ("Open the form and fill in the first page"). If the title is
     already that small, repeat it.

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

Undated focus
3. <task>

Homelab
- <task title>

Focus: 1, 2, 3. Reply ok, or other numbers.
Start with, ten minutes each:
1. <first step>
2. <first step>
3. <first step>

Old task: 4. <task> (untouched since <date>). Add to focus, give it a date, or drop it?

Missing: <source that failed>
```

- Number each displayed TickTick task once across all sections. Events and
  homelab tasks get a dash. Every focus task must be visible even when a
  section is capped; retain those tasks ahead of other tasks at the cutoff.
- The focus line names at most three numbers. Leave it out when there is no
  task.
- "Start with" has one line per focus task, under the same number. Leave it
  out with the focus line.
- Events first, by start time, then tasks.
- Overdue: oldest due date first.
- One line per item, no notes or descriptions, at most ten per section; then
  "and N more".
- The old task line comes last. The user may ignore it: tomorrow brings
  another one.
- If every section is empty, say that nothing is due today.

## Check

Each line comes from a tool result of this run, except a first step you wrote
in step 7. Do not add items from memory or from earlier conversations.
