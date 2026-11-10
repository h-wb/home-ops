# Assistant and agents: design

Target design, agreed 2026-11-09. It describes where the setup is going, not
what is deployed: current state lives in [this directory's README](./README.md)
and [Paseo environments](./paseo/README.md). The last section lists what has
to change to get there.

The design is written in roles. Product and model names appear as the current
choice for a role, for reference; swapping one does not change the design.

![The map: three places in two scopes, sharing a model gateway, a tool catalogue and a memory store per scope](./docs/img/map.svg)

## The rule

**Private data only reaches models you trust with it.**

Which models are trusted is a list, not part of the design:

|                           | Today                                                       |
| ------------------------- | ----------------------------------------------------------- |
| Trusted with private data | Models served by Mistral's API (Mistral, GLM), local models |
| General data only         | Claude, ChatGPT                                             |

Moving a model from one row to the other is one change, to the model lists on
the keys. Nothing else moves.

Two scopes follow from the rule:

- **General**: code, homelab, operational secrets. Any model may work on it.
- **Private**: mail, calendar, notes, personal tasks, location, health. Trusted
  models only.

Information flows from general to private, never back. A private agent may read
anything; a general agent may read only general things.

Three layers enforce it, and nothing else is relied on:

| Layer  | Enforcement                                                               |
| ------ | ------------------------------------------------------------------------- |
| Models | Each client's key lists its models; a private key lists trusted ones only |
| Tools  | One tool gateway per scope; a network rule admits only that scope         |
| Memory | One memory store per scope                                                |

The split is about which models see the data, not about limiting tools: private
agents get the full tool catalogue.

## Roles

| Role          | What it does                                                   | Today                   |
| ------------- | -------------------------------------------------------------- | ----------------------- |
| Assistant     | Talks to you, remembers, runs routines, decides who does work  | Hermes                  |
| Workshop      | Where agents with a shell work on repos; one per scope         | Paseo                   |
| Model gateway | The only path to any model; each client's key lists its models | LiteLLM                 |
| Tool gateway  | One catalogue of tools, served through one gateway per scope   | ToolHive                |
| Memory        | What agents remember between sessions; one store per scope     | Memini                  |
| Job runner    | Runs a named job with fixed inputs on real data                | Prefect                 |
| Task board    | The one place tasks live, whoever created them                 | Not chosen              |
| Messaging app | How you reach the assistant                                    | Telegram; iMessage next |

## One assistant, one workshop per scope

|          | Assistant                          | Private workshop       | General workshop      |
| -------- | ---------------------------------- | ---------------------- | --------------------- |
| Scope    | Private                            | Private                | General               |
| Models   | Trusted only                       | Trusted only           | Any                   |
| You use  | The messaging app                  | The workshop's app     | The workshop's app    |
| Works on | Your life, plus everything general | Private data and repos | Code and homelab      |
| Today    | `hermes-private`                   | `paseo-private`        | `paseo`               |
| Agents   | Hermes                             | OpenCode               | Claude Code, OpenCode |

- **No general assistant.** It would be an assistant without private data,
  which is what the general workshop already is.
- **The two workshops are one product.** One app with two hosts, one release
  definition with two sets of values. They are separate daemons because the
  workshop has no per-agent sandbox: an agent with a shell can read everything
  its daemon can, so a daemon belongs to one scope.
- **The assistant has no shell and no repo checkouts.** It reads untrusted text
  (mail, clipped web pages) next to private data, so everything it does goes
  through named tools.

The assistant and the workshop overlap (both can schedule, spawn agents and load
skills). Each overlapping feature has one owner:

| Concern                                          | Owner                                         |
| ------------------------------------------------ | --------------------------------------------- |
| Talking to the assistant                         | Assistant, over the messaging app             |
| Personal routines (briefing, reminders, notices) | Assistant's scheduler, delivered to the app   |
| Lookups and sub-tasks done through tools         | Assistant and its sub-agents                  |
| Jobs on private data (reconcile, repair, export) | Named tools in front of the job runner        |
| Anything that needs a shell or a repo            | Workshop, in the scope of the data it touches |
| Repo routines (dependency sweeps, CI watching)   | Workshop schedules                            |
| Models, tools, memory                            | The shared gateways and stores                |

## The assistant acts through tools

Everything the assistant does is a call to a named tool on the private tool
gateway. Tools are the control point: what exists there is what the assistant
can do.

- **Reads are free.** Looking something up never asks.
- **Writes ask.** A tool that changes something runs after you say yes, in the
  messaging app. A yes can cover one call, the rest of the chat, or that tool
  for good.
- **Jobs are tools.** Work on private data that used to be a script in a repo
  becomes a named job with fixed inputs. The assistant can start it; it cannot
  improvise a command.

The private workshop takes no part in this. It is where you work directly, with
a shell, on private repos and on the jobs themselves.

Today: Hermes has its own tool gateway with the real tool names, searches it
itself, asks before any call to a tool its server has not marked read-only, and
lets the read-only ones through. Tools approved
for good are a list in its managed config, so the list is versioned here.

## Places

A place is a filesystem, its credentials and its network reach. The boundary is
the place, not the orchestrator or a prompt rule:

- A place has exactly one scope. Models outside the trusted set run only in
  general places.
- A place holds only its own scope's credentials.
- The assistant's pod denies egress by default and allows a short list (model
  gateway, tools, memory, the messaging app). The workshops have open internet today.

| Place                | Scope   | Who works there                     |
| -------------------- | ------- | ----------------------------------- |
| `hermes-private` pod | Private | The assistant, no shell             |
| `paseo-private` pod  | Private | Private workshop agents             |
| `paseo` pod          | General | General workshop agents             |
| Workstation          | Mixed   | Agents of both kinds (Known limits) |

Adding a place later (another machine, a per-task sandbox) means picking its
scope: it gets that scope's model key, tool gateway and memory, and nothing else
in this design changes.

## Code and data

Repos hold code; services hold data (Dawarich, the vault, databases, private
memory).

- A repo with no private data in it is general. Any agent may write it in the
  general workshop; the private workshop clones it and runs it against the real
  data.
- A repo that does hold private data is private. It is only ever opened in the
  private workshop.
- The private workshop's GitHub credential reads general repos and writes only
  to private ones. General credentials cannot read private repos.
- A bug that only shows on real data is reproduced in the private workshop.
  What part of it goes to the general side is your call, through the hand-off
  approval.

Personal notes that sit beside code today (routine places, local notes) move to
the vault, so the repo stays general.

## Flows

Each flow is drawn step by step in [docs/flows.md](./docs/flows.md). How every
agent is connected today, and where that differs from this design, is in
[docs/wiring.md](./docs/wiring.md).

**Talk.** Messaging app → assistant. Telegram first, iMessage next. The
assistant answers only the accounts on its allow list; on Telegram it polls for
messages, so nothing connects in to it. Whatever it writes there is private
data: iMessage is end-to-end encrypted, Telegram bot chats are not, so
Telegram's servers can read them.

**Routine.** The assistant's scheduler runs a versioned job (prompt plus
skills), reads through the private tool gateway, and delivers to the messaging
app. The daily briefing is the first one; it also covers open homelab tasks.

**A job on private data.** "Reconcile yesterday's location":

1. The assistant reads what it needs through the private tool gateway.
2. It tells you what it wants to run and waits for a yes.
3. It starts the named job; the job runner runs it on the real data.
4. It reads the result and reports back.

Today the location repo's jobs are already Prefect deployments. Prefect's own
tool server is read-only, so starting a deployment needs one small tool of ours
that accepts a deployment from an allowed list and its parameters.

**Hand-off to the general workshop.** "Fix this bug":

1. The assistant drafts a prompt.
2. It shows the exact prompt and waits for approval.
3. It starts an agent on the general workshop's daemon; the agent appears in
   the workshop's app, where you can watch and steer it.
4. It checks the agent's status and reports back.

Step 2 is the only place private data could reach a model outside the trusted
set, so it is never automatic. Results coming back need no guard. You can also
skip the assistant and start the agent yourself in the workshop's app.

Today that link is Paseo's MCP server (`/mcp/agents` on the daemon port, the
daemon password as bearer token). The assistant is given its agent tools only
(`create_agent`, `send_agent_prompt`, `get_agent_status`, `list_agents`). The
same server also offers terminal tools, which would be a shell by another name.

**Homelab alerts.** Existing monitoring stays the detector. An alert becomes one
deduplicated task keyed by its fingerprint; the assistant reads those tasks for
the briefing and hands fixes to the general workshop like any other coding
request.

## Shared state

| Thing              | Where                          | Read by          | Written by       |
| ------------------ | ------------------------------ | ---------------- | ---------------- |
| General memory     | General memory store           | Everyone         | General agents   |
| Private memory     | Private memory store           | Private agents   | Private agents   |
| General skills     | One folder in dotfiles         | Everyone         | You, through git |
| Repo skills        | In the repo                    | Whoever opens it | You, through git |
| Assistant routines | home-ops, beside the assistant | The assistant    | You, through git |
| Learned skills     | The assistant's own volume     | The assistant    | The assistant    |

Private agents never write to general memory or the general skills folder:
either would carry private facts to the general side. They read general memory
with a read-only key; the question they ask is logged by the general store, so
it should not carry private detail. Skills the assistant
learns stay private until you promote one into git by hand.

## Skills

A skill is a folder with a `SKILL.md`: a name, one line saying when to use it,
and the procedure. Every agent here reads that format, and loads a skill only
when its line matches the task.

Guidance lives where its subject lives:

| Kind                | Example                                 | Lives in                                      |
| ------------------- | --------------------------------------- | --------------------------------------------- |
| What a tool is for  | "Restoring replaces the configuration"  | The tool's description, on the gateway        |
| A repo's procedures | Add an app; reconcile a day of location | That repo                                     |
| General habits      | How to use the tool gateway             | dotfiles, one folder, linked into every agent |
| Assistant routines  | The briefing; filing a task             | home-ops, beside the assistant, read-only     |

Review and delegation are not skills to write. The workshop ships them
(a second opinion, a committee of two, a hand-off), and picks who does the work
from agent profiles: a provider, a model and a note saying when to use it.

What makes a smaller model succeed, in order of effect:

1. Fewer tools in view, with short descriptions. Fix the description before
   writing a skill about it.
2. Anything that must happen the same way every time is a named tool or a job,
   not prose.
3. One skill, one job: exact tool names, the order, and how to check it worked.
4. A stronger model plans and reviews; a cheaper one does the work.
5. When an agent stumbles twice on the same thing, change the tool description
   or the skill, not the prompt.

## Where configuration lives

- **dotfiles** defines what an agent is: MCP servers, skills, instructions and
  model picks, written once and parameterised by scope.
- **home-ops** defines where it runs and what it can reach: pods, keys, network
  policies.

A new harness or machine picks a scope; it does not get its own config.

## Known limits

- The workstation is a mixed place: any agent there can read every repo and
  note on its disk. Keep private data out of working trees on it.
- Pasted text is not covered: don't paste private data into a general agent.
- The private workshop has a shell, private data and open internet, so an agent
  tricked there could send data out. Whether that stays is an open decision.
- The approval card for a hand-off shows the first 1200 characters of the
  prompt. A longer prompt is cut off on your screen, not in what is sent.
- The assistant holds both workshop daemons' passwords. Its config registers
  seven of their tools; the daemons themselves would accept the rest.
- Someone with cluster or Bitwarden admin rights in the general scope can reach
  private workloads. The boundary guards normal workflows, not an administrator.

## Considered and left out

- **One workshop for both scopes.** Paseo runs every agent as the daemon's user
  and keeps all transcripts in the daemon's home; its tool restrictions are not
  a boundary for an agent with a shell.
- **A sandbox per task** (Kubernetes agent-sandbox, gVisor, hosted sandboxes).
  Neither Paseo nor Hermes can launch into one natively today. A place per
  scope gives the same guarantee for two fixed scopes with far fewer parts.
- **Harness sandboxes** (the ones coding agents ship with). Useful as a second
  layer inside a place; not the boundary, since each harness configures its own.
- **The assistant as its own workbench** (shell and repo checkouts in its pod).
  Works, but puts a shell next to the agent that reads untrusted mail, and
  gives up the workshop's app for private work.

## Decisions

| Date       | Decision                                                                                     |
| ---------- | -------------------------------------------------------------------------------------------- |
| 2026-11-05 | One model gateway, LiteLLM                                                                   |
| 2026-11-07 | Hardened pods, not OpenShell sandboxes                                                       |
| 2026-11-09 | The rule is about trusted models, not about cloud against local                              |
| 2026-11-09 | One assistant, private only; the general Hermes was removed                                  |
| 2026-11-09 | One workshop daemon per scope; both kept, both in the `llm` namespace                        |
| 2026-11-09 | The assistant is reached through a messaging app                                             |
| 2026-11-09 | The assistant has no shell; everything it does is a named tool                               |
| 2026-11-09 | Reads are free, writes ask                                                                   |
| 2026-11-09 | Agents record conversations by themselves, each into its own scope's memory                  |
| 2026-11-09 | Home Assistant is private                                                                    |
| 2026-11-09 | GLM models served by Mistral's API are trusted                                               |
| 2026-11-09 | Every model call goes through the model gateway, OpenCode's included                         |
| 2026-11-09 | Exceptions to that: workstation agents, and OpenCode's hosted models in the general workshop |
| 2026-11-09 | Tool servers answer ToolHive's own pods only                                                 |
| 2026-11-09 | Jobs on private data are named tools, not free-form agents                                   |
| 2026-11-09 | Hand-offs to the general workshop need the prompt approved                                   |
| 2026-11-09 | Repos hold code, services hold data                                                          |
| 2026-11-09 | The briefing covers open homelab tasks                                                       |
| 2026-11-09 | "Scope" is the only term (not tier or segment)                                               |
| 2026-11-10 | The messaging apps are Telegram and iMessage                                                 |
| 2026-11-10 | The assistant starts agents in either workshop; every start asks, one call at a time         |

## Open

To decide:

- Whether the private workshop keeps open internet or gets an allowlist.
- Task board. Proposal: the assistant's built-in board (Hermes Kanban). It is
  already part of the assistant, has a web view, takes cards from chat, and
  dedupes cards created by automation, which is what alerts need. It replaces
  the three synthetic task boards. Homelab tasks then live on the private side,
  which the direction rule allows.
- Assistant memory: keep the Memini plugin and the job that installs it, or
  connect Memini as a plain MCP server and drop both.
- Adopt the community `paseo-agent-orchestration` skill for the assistant, or
  write a smaller one.
- iMessage for the assistant, after Telegram. Its adapter talks to a BlueBubbles
  server on a Mac: it needs that server's address and password, a way in for
  the server's webhook and one egress rule out. To settle first: whether the
  edge MacBook runs BlueBubbles or OpenBubbles (which does not fit a pod), and
  which Apple ID it is signed into. With your own, you would be texting
  yourself.

To verify:

- The trusted models are good enough: for the briefing, for choosing where work
  goes, and for unattended work in private repos.
- General GitHub credentials (the general workshop's token, the general tool
  gateway's GitHub tool, the workstation's login) cannot read repos that hold
  private data.
- The approval prompt for a write reaches you in the messaging app. On Telegram
  it is a message with buttons: once, this chat, always, deny.
- Hermes Kanban fits as a task board: cards nobody is assigned to stay put, and
  its automatic splitting of new cards can be turned off.
- Scheduled jobs can be created from versioned definitions at deploy time
  (`hermes cron create`).
- Hermes reads a routines folder mounted read-only (`skills.external_dirs`),
  and its bundled skills can be kept out (`.no-bundled-skills`).

## Getting there

Done (2026-11-09): the general Hermes removed; both workshops moved into the
`llm` namespace as `llm/paseo`; the old `agents` namespace deleted.

1. The assistant: Telegram is wired (a bot credential, and one egress rule to
   Telegram's API only). Next iMessage, then its scheduler, skills and
   sub-agents switched back on. Still no shell.
2. First routine: the daily briefing. Needs mail and calendar tools, which the
   catalogue does not have yet.
3. The private workshop as a real workshop: a GitHub credential (read general
   repos, write private ones), repo bootstrap enabled.
4. Job tools: Prefect's read-only tool server plus one small tool that starts
   an allowed deployment. First jobs: the location repo's.
5. Done: the assistant starts agents in either workshop. Every start asks,
   with the prompt on the approval card.
6. Remove the workshop → assistant chat bridge (exec, ACP shim, exec RBAC,
   projected token) once the messaging app is in daily use.
7. Skills: the general folder in dotfiles and agent profiles in the workshops;
   then the assistant's routines folder, with its first routine, when its
   skills are switched on (its bundled skills kept out).
8. Task board, then homelab alerts → cards.
9. Retire the Open WebUI data and legacy hostnames.
