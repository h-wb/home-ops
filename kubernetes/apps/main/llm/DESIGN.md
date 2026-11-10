# Assistant and agents: design

Target design, agreed 2026-11-09. It describes where the setup is going, not
what is deployed: current state lives in [this directory's README](./README.md)
and [Paseo environments](./paseo/README.md). The last section lists what has
to change to get there.

The design is written in roles. Product and model names appear as the current
choice for a role, for reference; swapping one does not change the design.

## The rule

**Private data only reaches models you trust with it.**

Which models are trusted is a list, not part of the design:

|                           | Today                 |
| ------------------------- | --------------------- |
| Trusted with private data | Mistral, local models |
| General data only         | Claude, ChatGPT       |

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

| Role          | What it does                                                   | Today      |
| ------------- | -------------------------------------------------------------- | ---------- |
| Assistant     | Talks to you, remembers, runs routines, decides who does work  | Hermes     |
| Workshop      | Where agents with a shell work on repos; one per scope         | Paseo      |
| Model gateway | The only path to any model; each client's key lists its models | LiteLLM    |
| Tool gateway  | One catalogue of tools, served through one gateway per scope   | ToolHive   |
| Memory        | What agents remember between sessions; one store per scope     | Memini     |
| Messaging app | How you reach the assistant                                    | Not chosen |

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
  (mail, clipped web pages) next to private data, so its hands are the
  workshops, reached through the workshop's own tools.

The assistant and the workshop overlap (both can schedule, spawn agents and load
skills). Each overlapping feature has one owner:

| Concern                                          | Owner                                         |
| ------------------------------------------------ | --------------------------------------------- |
| Talking to the assistant                         | Assistant, over the messaging app             |
| Personal routines (briefing, reminders, notices) | Assistant's scheduler, delivered to the app   |
| Lookups and sub-tasks done through tools         | Assistant and its sub-agents                  |
| Anything that needs a shell or a repo            | Workshop, in the scope of the data it touches |
| Repo routines (dependency sweeps, CI watching)   | Workshop schedules                            |
| Models, tools, memory                            | The shared gateways and stores                |

## Places

A place is a filesystem, its credentials and its network reach. The boundary is
the place, not the orchestrator or a prompt rule:

- A place has exactly one scope. Models outside the trusted set run only in
  general places.
- A place holds only its own scope's credentials.
- Private places deny egress by default and allow a short list (model gateway,
  tools, memory, the messaging app, GitHub, package indexes).

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

**Talk.** Messaging app → assistant. The app is not chosen yet; Hermes supports
Telegram, Signal, Matrix and others. Whatever the assistant writes there is
private data, so prefer an end-to-end encrypted one (Telegram bot chats are
not).

**Routine.** The assistant's scheduler runs a versioned job (prompt plus
skills), reads through the private tool gateway, and delivers to the messaging
app. The daily briefing is the first one; it also covers open homelab tasks.

**Hand-off to a workshop.** "Reconcile yesterday's location", "fix this bug":

1. The assistant picks the workshop from the scope of the data involved and
   drafts a prompt.
2. General workshop only: the assistant shows the exact prompt and waits for
   approval.
3. The assistant starts an agent on that workshop's daemon; the agent appears
   in the workshop's app, where you can watch and steer it.
4. The assistant checks its status and reports back.

| Work touches | Workshop | Models  | Approval               |
| ------------ | -------- | ------- | ---------------------- |
| Private data | Private  | Trusted | None, same scope       |
| Code only    | General  | Any     | You approve the prompt |

Step 2 is the only place private data could reach a model outside the trusted
set, so it is never automatic. Results coming back need no guard.

Today that link is Paseo's MCP server (`/mcp/agents` on the daemon port, the
daemon password as bearer token). The assistant is given its agent tools only
(`create_agent`, `send_agent_prompt`, `get_agent_status`, `list_agents`). The
same server also offers terminal tools, which would be a shell by another name.

**Homelab alerts.** Existing monitoring stays the detector. An alert becomes one
deduplicated task keyed by its fingerprint; the assistant reads those tasks for
the briefing and hands fixes to the general workshop like any other coding
request.

## Shared state

| Thing            | Where                         | Read by          | Written by       |
| ---------------- | ----------------------------- | ---------------- | ---------------- |
| General memory   | General memory store          | Everyone         | General agents   |
| Private memory   | Private memory store          | Private agents   | Private agents   |
| Shared skills    | One git directory, `SKILL.md` | Everyone         | You, through git |
| Repo skills      | In the repo                   | Whoever opens it | You, through git |
| Assistant skills | The assistant's own volume    | The assistant    | The assistant    |

Private agents never write to general memory or the shared skills directory:
either would carry private facts to the general side. Skills the assistant
learns stay private until you promote one into git by hand.

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

| Date       | Decision                                                                |
| ---------- | ----------------------------------------------------------------------- |
| 2026-11-05 | One model gateway, LiteLLM                                              |
| 2026-11-07 | Hardened pods, not OpenShell sandboxes                                  |
| 2026-11-09 | The rule is about trusted models, not about cloud against local         |
| 2026-11-09 | One assistant, private only; the general Hermes was removed             |
| 2026-11-09 | One workshop daemon per scope; both kept, both in the `llm` namespace   |
| 2026-11-09 | The assistant is reached through a messaging app                        |
| 2026-11-09 | The assistant has no shell; it drives the workshops through their tools |
| 2026-11-09 | Hand-offs to the general workshop need the prompt approved              |
| 2026-11-09 | Repos hold code, services hold data                                     |
| 2026-11-09 | The briefing covers open homelab tasks                                  |
| 2026-11-09 | "Scope" is the only term (not tier or segment)                          |

## Open

To decide:

- Which messaging app.
- Whether the assistant may start private jobs without asking, or waits for a
  yes there too.
- Task system. Proposal: homelab tasks as GitHub issues in this repo, with the
  alert fingerprint as a label; personal tasks wherever they already live. This
  replaces the three synthetic task boards.
- Assistant memory: keep the patched Memini plugin and its sync job, or connect
  Memini as a plain MCP server and drop both.
- Send every model call through the model gateway and drop the direct
  `MISTRAL_API_KEY` from the workshop pods.
- Adopt the community `paseo-agent-orchestration` skill for the assistant, or
  write a smaller one.

To verify:

- The trusted models are good enough: for the briefing, for choosing where work
  goes, and for unattended work in private repos.
- General GitHub credentials (the general workshop's token, the general tool
  gateway's GitHub tool, the workstation's login) cannot read repos that hold
  private data.
- Marking the general workshop's server `trust: untrusted` in Hermes makes
  `create_agent` ask for approval in the messaging app.
- Scheduled jobs can be created from versioned definitions at deploy time
  (`hermes cron create`).
- Memini supports read-only keys, so private agents can read general memory.
- Hermes reads the shared skills directory (`skills.external_dirs`).

## Getting there

Done (2026-11-09): the general Hermes removed; both workshops moved into the
`llm` namespace as `llm/paseo`; the old `agents` namespace deleted.

1. The assistant: the messaging app (credential, one egress rule), then its
   scheduler, skills and sub-agents switched back on. Still no shell.
2. First routine: the daily briefing. Needs mail and calendar tools, which the
   catalogue does not have yet.
3. The private workshop as a real workshop: a GitHub credential (read general
   repos, write private ones), repo bootstrap enabled, an egress allowlist.
4. Assistant → both workshop daemons; approval on the general one.
5. Remove the workshop → assistant chat bridge (exec, ACP shim, exec RBAC,
   projected token) once the messaging app is in daily use.
6. Shared skills directory in dotfiles, mounted read-only into the assistant.
7. Homelab alerts → tasks.
8. Retire the Open WebUI data and legacy hostnames.
