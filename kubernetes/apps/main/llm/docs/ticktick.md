# TickTick setup

Use lists for where tasks belong, and Smart Lists and Filters for what to look
at. A task stays in one list even when several views show it. The calendar
shows when there is room; the project map in Obsidian shows what matters next.

## Personal views

In TickTick, open **Settings > Smart Lists** and set **Filters** to Show.
Use **Add > Filter** in the sidebar. Keep Inbox as the place to capture, not
as the list you work from. Add `quick` and `waiting` as tags only if they do
not already exist.

| View           | Rule                                                          | Use it for                                              |
| -------------- | ------------------------------------------------------------- | ------------------------------------------------------- |
| Now            | Advanced: personal lists AND (High priority OR Date is Today) | The last confirmed focus plus today's dated commitments |
| Quick          | Personal lists AND tag `quick`; exclude `waiting`             | A ten-minute gap or a low-energy start                  |
| Assigned to Me | Built-in, Show if not empty                                   | Work someone handed back to you in a shared list        |
| Waiting        | Optional filter: personal lists AND tag `waiting`             | Weekly review, not a daily list                         |

Select Admin, Health, Growth, Homelab and Life as the personal lists in
these filters; include Inbox in the **Today** clause if you want dated
captures in Now. Do not include Build or Someday. If Advanced mode offers
separate rule groups rather than parentheses, put the list restriction in
both the High and Today groups. Use **Preview** before saving: an undated
High task and a dated task due today should both appear; a Build or Someday
task should not. Keep the built-in Today visible until Now works for you.
If the app cannot express the rule, use Today for dates and a separate
High-priority Focus filter for the personal lists. Hide All and other
built-in views you do not open.

Hermes proposes up to three focus tasks with a short first action. A reply
confirming the selection sets High without adding fake deadlines. The High
marker stays until you complete the task or confirm a new selection. The weekly
review suggests a few stale tasks to park; reply `park <number>` to move one.
Someday is private and undated. Exclude it from the personal filters and the
calendar view. The built-in Today only needs the real dates.

## Build handoffs

Keep the existing **Projects > Build** board (Next, Doing, Done). Keep work
that needs only agents on the board or in its pull request; assign a card to
yourself when it needs your input. Do not copy personal tasks or calendar
data into Build. Leave cards undated and without reminders unless there is a
real handoff deadline.

1. Create a separate Agents account, starting on the free plan. Invite that
   account to **Build only** and accept the invite there.
2. On the main account, edit Build: set **Show in Smart List** and **Reminder**
   to **Tasks Assigned to Me**. Separately turn off routine shared-list
   activity notifications (adds, moves, completions).
3. Before wiring the account to workshop agents, verify using its own login
   or token that it can see Build and cannot see any of the owner's private
   lists, tasks or calendars. Test a handoff with a disposable card; confirm
   a card assigned back shows in **Assigned to Me**, not in the personal
   Now filter. Never repurpose the private Hermes account token for agents.

Assignment is a handoff, not an automatic trigger for agent runs. Keep the
placeholder boards until a scoped connector and the first handoff have been
verified. Free-tier MCP access for the Agents account still needs testing.

## iCloud planner

On your main TickTick account, go to **Settings > Import & Integration >
Calendar > iCloud**. Enter an Apple app-specific password directly in
TickTick. Pick the calendars you want the planner to show. In three-day or
week view, put commitments on the calendar and use explicit start/end blocks
for the time you choose to spend on a project. Leave the rest undated. For
the weekly review, compare planned blocks with what fit, rather than dating
every task or maintaining a Gantt chart.

Private Hermes already queries connected calendars via TickTick. After
linking iCloud, ask it to check for one known test event before relying on
the briefing. A TickTick task block appears in TickTick's planner; it is
not an iCloud event. Keep Apple Calendar as the place to edit iCloud events.

TickTick's supported API and MCP can query tasks, but do not create these
saved Filters. Make the filters and account settings in the app; no personal
password or token needs to be shared with a coding session.

References: [Smart Lists](https://help.ticktick.com/articles/7055782283059396608),
[Filters](https://help.ticktick.com/articles/7055782240994721792),
[collaboration](https://help.ticktick.com/articles/7055781688281923584),
[iCloud](https://help.ticktick.com/articles/7209479055807086592),
[MCP](https://help.ticktick.com/articles/7438129581631995904).
