---
name: weekly-review
description: Send the weekly review (wins, inbox, overdue, waiting, each active project's next step, the next seven days, one idea from the vault). Use when the weekly-review routine runs or when asked for the weekly review.
metadata:
  schedule: "0 18 * * 0"
  model: mistral/mistral-large-4
---

# Weekly review

Read, then write one message. Change nothing here: the user answers, and the
`task-followup` and `vault-notes` skills act on the answer.

## Read

Call these tools by their exact names with `tool_call`. If a name is not
found, search for the part after `mcp__tools__`. The timezone is
`America/Toronto`; pass it as `client_timezone`.

1. `mcp__tools__ticktick_list_completed_tasks_by_date` with
   `search: {startDate: seven days ago at 00:00, endDate: now}`: done this
   week.
2. `mcp__tools__ticktick_filter_tasks` with `filter: {status: [0]}`: every
   open task. From it:
   - Inbox: a `projectId` that starts with `inbox`.
   - Overdue: a `dueDate` before today.
   - Waiting: tagged `waiting`.
   - Coming: a `dueDate` from today to seven days from now.
3. `mcp__tools__ticktick_query_calendar_events` with `query.begin` today at
   00:00 and `query.end` seven days later: events ahead.
4. `mcp__tools__vault_ro_query_notes`: notes outside `Archives/` whose
   `categories` contains `Projects` and whose `status` contains `active`, with
   the fields `ticktick` and `url`. For each, the last part of the `ticktick`
   link is its parent task's id; its next step is the open task in step 2
   with that `parentId` and the earliest `dueDate`.
5. `mcp__tools__vault_ro_query_notes`: notes in `Notes/` or `AI/` with no
   `categories` and no `area`: the vault inbox. Count them; take the oldest by
   `created`.
6. `mcp__tools__vault_ro_query_notes`: notes outside `Archives/` whose
   `categories` contains `Ideas` and whose `status` contains `seed`, oldest
   `modified` first. Take the one whose position, counted from 0, is this
   week's number modulo how many there are.

If a call fails, go on with the others and say which source is missing.

## Write

```
Weekly review, week of <date>.

Done this week: <N>
- <task>

Inbox
1. <task> -> <list>
- Vault inbox: <N> unfiled notes, oldest <title> (<date>).

Overdue
2. <task> (due <date>): do, date or drop?

Waiting on someone
3. <task>: still waiting, done, or follow up?

Projects (<N> active)
4. <project>: next step <task> (<date>)
5. <project>: no dated next step. What is it?

Next seven days
- <weekday> <time> <event or task>

One idea
6. <idea> (seed since <date>): task, project, or leave it?

Answer with numbers, for example "1 ok, 2 drop, 5 book flights Friday, 6 leave".
```

- Number only the items that need an answer, in one sequence. Done tasks,
  the vault inbox line and the next seven days get a dash.
- Done this week: the count, then at most five titles, the most recent first.
- For each inbox task, suggest a list as the evening check-in does: Admin,
  Health, Growth, Homelab, Life, or `drop`.
- A project with a `url` and no `ticktick` keeps its steps in a repo: write
  "<project>: steps in the repo", without a number.
- More than three active projects: add "More than three active: which goes
  back to backlog?" as its own numbered item.
- At most ten items per section, then "and N more". Leave empty sections out.
- Nothing else: no advice, no summary.

## Check

Each line comes from a tool result of this run.
