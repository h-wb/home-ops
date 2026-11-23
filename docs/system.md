# The system: map and plan

Start here. One page for everyone who works on this: you, the assistant, and
every agent in a workshop. It says what the system is for, what its parts are,
what is being worked on, and where each part is documented. It links to the
other pages and copies nothing from them.

If you change a part, change its row here in the same pull request.

## What it is for

A second brain: something that knows what is going on, so you can spend your
time well and be present, instead of holding everything in your head.

It is a tool, not the project of your life. Building it is one project among
the others, with its own blocks in the calendar.

## Rules that keep it small

1. **Three things at most are "now".** A new idea goes to the backlog, not
   into "now". Nothing is lost by waiting there.
2. **Every milestone has a "done when".** When it is met, stop and use the
   thing for two weeks before starting the next.
3. **Building has a budget.** It happens in blocks that are in the calendar,
   like any other project. An agent that is asked for more outside a block may
   say so.
4. **One place per kind of thing** (the table at the end). If something exists
   twice, one of the two is wrong.
5. **An agent finishes by updating the record**: the part's own page, its row
   here, and the backlog. What an agent keeps only in its own memory does not
   count as written down.

## The parts

| Part          | What it does                                                   | State                                                                            | Its page                                                                 |
| ------------- | -------------------------------------------------------------- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| Model gateway | The only path to any model; each client's key lists its models | Works                                                                            | [llm](../kubernetes/apps/main/llm/README.md)                             |
| Tool gateways | One catalogue of tools, served per scope                       | Works                                                                            | [llm](../kubernetes/apps/main/llm/README.md)                             |
| Memory        | What agents remember between sessions, one store per scope     | Works                                                                            | [llm](../kubernetes/apps/main/llm/README.md)                             |
| Workshops     | Where agents with a shell work on repos, one per scope         | Works                                                                            | [paseo](../kubernetes/apps/main/llm/paseo/README.md)                     |
| Assistant     | Talks to you, runs routines, acts through named tools          | Works, on a clock                                                                | [hermes](../kubernetes/apps/main/llm/hermes/README.md)                   |
| Awareness     | How the assistant knows what is going on and when to speak     | Designed, not built                                                              | [awareness](../kubernetes/apps/main/llm/docs/awareness.md)               |
| Warehouse     | Every source mirrored into one database, for good              | Works                                                                            | [miroir](../kubernetes/apps/main/automation/miroir/README.md)            |
| Collectors    | On a device: read local sources, mask, deliver                 | Works on the MacBook; edge Mac being set up                                      | [edge-mac](../hosts/edge-mac/README.md), dotfiles                        |
| Dashboards    | One collection per source                                      | Works                                                                            | [miroir](../kubernetes/apps/main/automation/miroir/README.md)            |
| Timeline      | Look back at a day: screen, browser, later conversations       | Data and API work; pages being built                                             | [miroir](../kubernetes/apps/main/automation/miroir/README.md)            |
| Tasks         | The one list of what is to do, for you and for the build       | Works: your lists, and the Homelab board for the build; agents not connected yet | [Open](#open)                                                            |
| Calendar      | The plan: what happens when, and what time is free             | Events are read; the plan is not in it yet                                       | [awareness](../kubernetes/apps/main/llm/docs/awareness.md#getting-there) |
| Notes         | Your own notes, private                                        | Works                                                                            | [llm](../kubernetes/apps/main/llm/README.md#where-things-live)           |
| Location      | Where you were                                                 | Works, in its own service                                                        | –                                                                        |
| Home hub      | Home automation; later the live signals                        | Works; no live signals                                                           | [awareness](../kubernetes/apps/main/llm/docs/awareness.md)               |

Design and rules behind all of it:
[DESIGN.md](../kubernetes/apps/main/llm/DESIGN.md). Who may see what is its
first section, and it applies to everything here.

## The road

Proposed on 2026-11-22; yours to change. Each step is worth having on its own,
so stopping after any of them is fine.

| Milestone           | Done when                                                                                                 | State                        |
| ------------------- | --------------------------------------------------------------------------------------------------------- | ---------------------------- |
| 0. Foundation       | Scopes, gateways, workshops and an assistant you can talk to                                              | Done                         |
| 1. The record       | Every source loads by itself for two weeks without anyone touching it                                     | Nearly: the edge Mac is left |
| 2. Look back        | You can scrub through a day and search what was on screen, on the phone and the desktop                   | In progress                  |
| 3. The plan         | Your recurring things and project blocks are in the calendar, and one task list is reachable by everyone  | Not started                  |
| 4. The right moment | Two weeks of prompts in the Now room, within the daily budget, with a log of which you acted on           | Not started                  |
| 5. It learns        | A slipped task is noticed and repaired without you saying so, and the weekly review proposes rule changes | Not started                  |

Milestone 3 comes before 4 on purpose: without a plan in the calendar there is
no "free" moment to find, and without one task list there is nothing to
propose.

### Now

At most three. They are the "Doing" column of the Homelab board in the task app,
each with its steps and who does them.

1. Conversations in the timeline (milestone 2, extended).
2. Messages from the edge Mac (milestone 1).
3. The fix for the timeline's upgrade on PostgreSQL 18.

### Next, and later

On the Homelab board, in its "Next" and "Later" columns, and nowhere else. A new
idea becomes a card in "Later". What "Later" holds is described in
[awareness](../kubernetes/apps/main/llm/docs/awareness.md).

## Open

**The shared task list.** Decided on 2026-11-23: your task app is the one list
for everything you do, split by list and not by tool.

- The lists are the vault's areas, in one folder, "Areas": Admin, Health,
  Growth, Life and Homelab. Homelab is a board (Doing, Next, Later, Done) and
  holds the build: the homelab, the assistant and the warehouse. A card is an
  outcome with its "done when"; its steps are subtasks, each saying who does
  it. A project is not a list: it is a note in the vault and a parent task in
  its area's list. "Someday" holds what you parked.
- Homelab holds nothing private
  ([the scope rule](../kubernetes/apps/main/llm/DESIGN.md#the-rule)), because
  it is the one list agents will read.
- Nothing on Homelab has a date or a reminder unless you give it one, so it
  never fills your day. It comes up in the weekly review.
- Still to do: an account of their own for the agents, with only Homelab shared
  with it, so that a card is assigned to you or to them and the app's own
  sharing decides what they see; then the placeholder boards go.

The calendar stays where it is (iCloud), shown inside the task app, where the
assistant can read it. Fixed things and the blocks for each project are
events; a block holds a project, not a task. The blocks are the budget.

**One place to read and write.** The pages are spread over three repos, and
your notes are in the vault. Your idea (2026-11-22): Obsidian is where the
system's pages are written, and GitHub shows the same pages. Proposal:

- A vault of its own for them, not a folder of your vault. Your vault is
  private and served to private agents; a public folder inside it is one drag,
  one embed or one link away from publishing a note. The cost: no links
  between the two vaults, and each has its own search.
- That vault is a git repo. Obsidian edits plain Markdown files and GitHub
  shows them, diagrams included, so there is one copy and no export. You write
  in Obsidian; agents write through pull requests.
- What moves there: this page, the designs, the flows, the overview of each
  part: what you read to understand or run the system. What stays beside the
  code: what only matters when changing that code, with a link to the vault.
  The cost: a change to code and to its page becomes two pull requests.
- Tasks do not go there. A task needs capture from anywhere, a date, a
  reminder, and to be ticked by an agent without rewriting a page you have
  open. The plan stays a page; the items live in the task list.

To settle: public or only general (a private repo general agents can read),
and how the phone edits it (the git plugin, or a sync like your vault's).

**The budget for building.** How many blocks a week, and when.

## Where each kind of thing lives

| Kind                             | Where                                                          |
| -------------------------------- | -------------------------------------------------------------- |
| What the system is, and the plan | This page                                                      |
| How a part works                 | That part's page (the table above)                             |
| Why it is built this way         | `DESIGN.md`, and the decisions in pipelines                    |
| What is to do                    | The task app: your lists, with the Homelab board for the build |
| What happened                    | Pull requests                                                  |
| Your own notes                   | The vault                                                      |
| What agents learned as they work | Their memory store; never the only copy of a plan              |
