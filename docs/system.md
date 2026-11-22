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

| Part          | What it does                                                   | State                                        | Its page                                                                 |
| ------------- | -------------------------------------------------------------- | -------------------------------------------- | ------------------------------------------------------------------------ |
| Model gateway | The only path to any model; each client's key lists its models | Works                                        | [llm](../kubernetes/apps/main/llm/README.md)                             |
| Tool gateways | One catalogue of tools, served per scope                       | Works                                        | [llm](../kubernetes/apps/main/llm/README.md)                             |
| Memory        | What agents remember between sessions, one store per scope     | Works                                        | [llm](../kubernetes/apps/main/llm/README.md)                             |
| Workshops     | Where agents with a shell work on repos, one per scope         | Works                                        | [paseo](../kubernetes/apps/main/llm/paseo/README.md)                     |
| Assistant     | Talks to you, runs routines, acts through named tools          | Works, on a clock                            | [hermes](../kubernetes/apps/main/llm/hermes/README.md)                   |
| Awareness     | How the assistant knows what is going on and when to speak     | Designed, not built                          | [awareness](../kubernetes/apps/main/llm/docs/awareness.md)               |
| Warehouse     | Every source mirrored into one database, for good              | Works                                        | [miroir](../kubernetes/apps/main/automation/miroir/README.md)            |
| Collectors    | On a device: read local sources, mask, deliver                 | Works on the MacBook; edge Mac being set up  | [edge-mac](../hosts/edge-mac/README.md), dotfiles                        |
| Dashboards    | One collection per source                                      | Works                                        | [miroir](../kubernetes/apps/main/automation/miroir/README.md)            |
| Timeline      | Look back at a day: screen, browser, later conversations       | Data and API work; pages being built         | [miroir](../kubernetes/apps/main/automation/miroir/README.md)            |
| Tasks         | The one list of what is to do, for you and for the build       | Yours works; no shared one for the build yet | [Open](#open)                                                            |
| Calendar      | The plan: what happens when, and what time is free             | Events are read; the plan is not in it yet   | [awareness](../kubernetes/apps/main/llm/docs/awareness.md#getting-there) |
| Notes         | Your own notes, private                                        | Works                                        | [llm](../kubernetes/apps/main/llm/README.md#where-things-live)           |
| Location      | Where you were                                                 | Works, in its own service                    | –                                                                        |
| Home hub      | Home automation; later the live signals                        | Works; no live signals                       | [awareness](../kubernetes/apps/main/llm/docs/awareness.md)               |

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

At most three.

1. Messages from the edge Mac (milestone 1).
2. The timeline's pages (milestone 2).
3. This page, and the two decisions under [Open](#open) (milestone 3).

### Next

- Your recurring things and the blocks for each project, in the calendar.
- The shared task list, and the backlog moved into it.
- The Now room and a room per routine.

### Later, and deliberately not now

Mail and calendar tools, the live path, summaries of each day, the log by
voice, the missed-task loop, conversations in the timeline, other chat
networks, a contacts source, the screen recorder trial, a decision model. Each
is described in [awareness](../kubernetes/apps/main/llm/docs/awareness.md).

## Open

**The shared task list.** Today your tasks are in your task app, which only the
assistant can reach, and the build's tasks are in three places: a placeholder
board, pull requests, and agents' own notes. Proposal: your task app stays the
one list for everything you do, the build included, in its own list; a narrow
tool lets general agents read and write that one list and nothing else; the
placeholder boards go. The rule that decides what may be in that list is the
[scope rule](../kubernetes/apps/main/llm/DESIGN.md#the-rule): general agents
read it, so nothing private goes there.

**One place to read.** The pages are spread over three repos, and your notes
are in the vault. The idea: the vault becomes the one place to read
everything. The constraint: the vault is private, and general agents cannot
read it. Proposal: git stays where system pages are written, and they are
copied into the vault, read-only, where you read them beside your notes. That
direction (general to private) is the free one. Notes you write about the
system stay in the vault; a page that general agents must follow has to live
in git.

**The budget for building.** How many blocks a week, and when.

## Where each kind of thing lives

| Kind                             | Where                                                                 |
| -------------------------------- | --------------------------------------------------------------------- |
| What the system is, and the plan | This page                                                             |
| How a part works                 | That part's page (the table above)                                    |
| Why it is built this way         | `DESIGN.md`, and the decisions in pipelines                           |
| What is to do                    | The shared task list, once chosen; until then, "Now" and "Next" above |
| What happened                    | Pull requests                                                         |
| Your own notes                   | The vault                                                             |
| What agents learned as they work | Their memory store; never the only copy of a plan                     |
