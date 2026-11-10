# Assistant and agents: design

Target design, agreed 2026-11-09. It describes where the setup is going, not
what is deployed: current state lives in [this directory's README](./README.md)
and [Paseo environments](../agents/README.md). The last section lists what has
to change to get there.

## The invariant

**Cloud models never see private data.**

- **General** scope: code, homelab, operational secrets. Any model may see it,
  including Claude and ChatGPT.
- **Private** scope: mail, calendar, notes, personal tasks, location, health.
  Only Mistral and local models may see it.

Information flows from general to private, never back. A private agent may read
anything; a general agent may read only general things.

Three things enforce it, and nothing else is relied on:

| Layer  | Enforcement                                                          |
| ------ | -------------------------------------------------------------------- |
| Models | Each LiteLLM virtual key lists its models; no private key has cloud  |
| Tools  | One ToolHive gateway per scope; NetworkPolicy admits only that scope |
| Memory | One Memini instance per scope                                        |

The split is about which model provider sees the data, not about limiting tools:
private agents get the full tool catalogue.

## One assistant, one workshop per scope

Hermes is the assistant: it talks to you, remembers, runs routines and decides
who does the work. Paseo is the workshop: it is where agents with a shell work
on repos.

|          | Assistant                          | Private workshop        | General workshop                |
| -------- | ---------------------------------- | ----------------------- | ------------------------------- |
| Product  | Hermes                             | Paseo (`paseo-private`) | Paseo (`paseo`)                 |
| Models   | Mistral, local                     | Mistral, local          | Claude, ChatGPT, Mistral, local |
| Agents   | Hermes                             | OpenCode                | Claude Code, OpenCode           |
| You use  | A messaging app                    | Paseo app               | Paseo app                       |
| Works on | Your life, plus everything general | Private data and repos  | Code and homelab                |

- **No Claude-backed assistant.** It would be an assistant without private
  data, which is what the general workshop already is.
- **The two workshops are one Paseo.** One app with two hosts, one HelmRelease
  with two sets of values. They are separate daemons because Paseo has no
  per-agent sandbox: an agent with a shell can read everything its daemon can,
  so a daemon belongs to one scope.
- **Hermes has no shell and no repo checkouts.** It reads untrusted text (mail,
  clipped web pages) next to private data, so its hands are the workshops,
  reached through Paseo's own tools.

Hermes and Paseo overlap (both can schedule, spawn agents and load skills). Each
overlapping feature has one owner:

| Concern                                          | Owner                                       |
| ------------------------------------------------ | ------------------------------------------- |
| Talking to the assistant                         | Hermes, over the messaging app              |
| Personal routines (briefing, reminders, notices) | Hermes cron, delivered to the messaging app |
| Lookups and sub-tasks done through tools         | Hermes and its sub-agents                   |
| Anything that needs a shell or a repo            | Paseo, in the scope of the data it touches  |
| Repo routines (dependency sweeps, CI watching)   | Paseo schedules                             |
| Models, tools, memory                            | LiteLLM, ToolHive, Memini (shared)          |

## Places

A place is a filesystem, its credentials and its network reach. The boundary is
the place, not the orchestrator or a prompt rule:

- A place has exactly one scope. Cloud models run only in general places.
- A place holds only its own scope's credentials.
- Private places deny egress by default and allow a short list (model gateway,
  tools, memory, the messaging app, GitHub, package indexes).

| Place                | Scope   | Who works there                      |
| -------------------- | ------- | ------------------------------------ |
| `hermes-private` pod | Private | Hermes, no shell                     |
| `paseo-private` pod  | Private | OpenCode                             |
| `paseo` pod          | General | Claude Code, OpenCode                |
| Workstation          | Mixed   | Claude Code, Vibe (see Known limits) |

Adding a place later (another machine, a per-task sandbox) means picking its
scope: it gets that scope's model key, tool gateway and memory, and nothing else
in this design changes.

## Code and data

Repos hold code; services hold data (Dawarich, the vault, databases, private
memory).

- A repo with no private data in it is general. Claude writes it in the general
  workshop; the private workshop clones it and runs it against the real data.
- A repo that does hold private data is private. It is only ever opened in the
  private workshop.
- The private workshop's GitHub credential reads general repos and writes only
  to private ones. General credentials cannot read private repos.
- A bug that only shows on real data is reproduced in the private workshop.
  What part of it goes to Claude is your call, through the hand-off approval.

Personal notes that sit beside code today (routine places, local notes) move to
the vault, so the repo stays general.

## Parts

| Part                         | Role                                                    |
| ---------------------------- | ------------------------------------------------------- |
| `hermes-private`             | The assistant: messaging, cron, memory, skills          |
| `paseo-private`              | Private workshop                                        |
| `paseo`                      | General workshop                                        |
| LiteLLM + key operator       | Only model gateway; key allowlists are the model policy |
| ToolHive                     | One tool catalogue, two gateways (general, private)     |
| Memini ×2                    | Memory per scope                                        |
| `embed`, Obsidian vault sync | Embeddings; the vault as a private tool                 |

Going away: the Paseo → Hermes chat bridge (exec, ACP shim, exec RBAC, projected
token), once the messaging app is in daily use. The link then runs the other
way: Hermes calls Paseo.

## Flows

**Talk.** Messaging app → Hermes. The app is not chosen yet; Hermes supports
Telegram, Signal, Matrix and others. Whatever Hermes writes there is private
data, so prefer an end-to-end encrypted one (Telegram bot chats are not).

**Routine.** Hermes cron runs a versioned job (prompt plus skills), reads
through the private gateway, and delivers to the messaging app. The daily
briefing is the first one.

**Hand-off to a workshop.** "Reconcile yesterday's location", "fix this bug":

1. Hermes picks the workshop from the scope of the data involved and drafts a
   prompt.
2. General workshop only: Hermes shows the exact prompt and waits for approval.
3. Hermes calls that daemon's `create_agent` over Paseo's MCP server; the agent
   appears in the Paseo app, where you can watch and steer it.
4. Hermes checks its status and reports back.

| Work touches | Workshop        | Agent on | Approval               |
| ------------ | --------------- | -------- | ---------------------- |
| Private data | `paseo-private` | Mistral  | None, same scope       |
| Code only    | `paseo`         | Claude   | You approve the prompt |

Step 2 is the only place private data could reach a cloud model, so it is never
automatic. Results coming back need no guard.

**Homelab alerts.** Existing monitoring stays the detector. An alert becomes one
deduplicated task keyed by its fingerprint; Hermes reads those tasks for the
briefing and hands fixes to the general workshop like any other coding request.

## Shared state

| Thing          | Where                         | Read by          | Written by       |
| -------------- | ----------------------------- | ---------------- | ---------------- |
| General memory | General Memini                | Everyone         | General agents   |
| Private memory | Private Memini                | Private agents   | Private agents   |
| Shared skills  | One git directory, `SKILL.md` | Everyone         | You, through git |
| Repo skills    | In the repo                   | Whoever opens it | You, through git |
| Hermes skills  | Hermes's own volume           | Hermes           | Hermes           |

Private agents never write to general memory or the shared skills directory:
either would carry private facts to Claude. Skills Hermes learns stay private
until you promote one into git by hand.

## Where configuration lives

- **dotfiles** defines what an agent is: MCP servers, skills, instructions and
  model picks, written once and parameterised by scope.
- **home-ops** defines where it runs and what it can reach: pods, keys, network
  policies.

A new harness or machine picks a scope; it does not get its own config.

## Known limits

- The workstation is a mixed place: Claude Code there can read every repo and
  note on its disk. Keep private data out of working trees on it.
- Pasted text is not covered: don't paste private data into a general agent.
- Someone with cluster or Bitwarden admin rights in the general scope can reach
  private workloads. The boundary guards normal workflows, not an administrator.

## Considered and left out

- **One Paseo for both scopes.** Paseo runs every agent as the daemon's user
  and keeps all transcripts in the daemon's home; its tool restrictions are not
  a boundary for an agent with a shell.
- **A sandbox per task** (Kubernetes agent-sandbox, gVisor, cloud sandboxes).
  Neither Paseo nor Hermes can launch into one natively today. A place per
  scope gives the same guarantee for two fixed scopes with far fewer parts.
- **Harness sandboxes** (Claude Code's, Codex's). Useful as a second layer
  inside a place; not the boundary, since each harness configures its own.
- **Hermes as its own workbench** (shell and repo checkouts in the Hermes pod).
  Works, but puts a shell next to the agent that reads untrusted mail, and
  gives up Paseo's app and OpenCode for private work.

## Decisions

| Date       | Decision                                                               |
| ---------- | ---------------------------------------------------------------------- |
| 2026-11-05 | LiteLLM is the only model gateway                                      |
| 2026-11-07 | Hardened pods, not OpenShell sandboxes                                 |
| 2026-11-09 | One assistant (private Hermes); general Hermes removed                 |
| 2026-11-09 | One Paseo daemon per scope; both kept                                  |
| 2026-11-09 | The assistant is reached through a messaging app                       |
| 2026-11-09 | Hermes has no shell; it drives the workshops through Paseo's MCP tools |
| 2026-11-09 | Hand-offs to the general workshop need the prompt approved             |
| 2026-11-09 | Repos hold code, services hold data                                    |
| 2026-11-09 | "Scope" is the only term (not tier or segment)                         |

## Open

To decide:

- Which messaging app.
- Task system. Proposal: homelab tasks as GitHub issues in this repo, with the
  alert fingerprint as a label; personal tasks wherever they already live. This
  replaces the three synthetic task boards.
- Hermes memory: keep the patched Memini plugin and its sync job, or connect
  Memini as a plain MCP server and drop both.
- Send OpenCode's Mistral traffic through LiteLLM and drop `MISTRAL_API_KEY`
  from the pods.
- Adopt the community `paseo-agent-orchestration` skill for Hermes, or write a
  smaller one.

To verify:

- Mistral is good enough: Hermes for the briefing and for choosing where work
  goes, OpenCode for unattended work in private repos.
- General GitHub credentials (Paseo's token, the general gateway's GitHub tool,
  the workstation's login) cannot read repos that hold private data.
- The URL of Paseo's MCP server on our pods, and that the daemon password is
  all it needs.
- Marking the general Paseo server `trust: untrusted` in Hermes makes
  `create_agent` ask for approval in the messaging app.
- Cron jobs can be created from versioned definitions at deploy time
  (`hermes cron create`).
- Memini supports read-only keys, so private agents can read general memory.
- Hermes reads the shared skills directory (`skills.external_dirs`).

## Getting there

Done: `hermes-general` removed (2026-11-09).

1. Paseo moves into the `llm` namespace, as `llm/paseo`; `agents` goes away.
2. Hermes: the messaging app (credential, one egress rule), then cron, skills
   and sub-agents switched back on. Still no shell.
3. First routine: the daily briefing. Needs mail and calendar tools, which the
   catalogue does not have yet.
4. `paseo-private` as a real workshop: a GitHub credential (read general repos,
   write private ones), repo bootstrap enabled, an egress allowlist.
5. Hermes → both Paseo daemons over MCP; approval on the general one.
6. Remove the Paseo → Hermes chat bridge.
7. Shared skills directory in dotfiles, mounted read-only into Hermes.
8. Homelab alerts → tasks.
9. Retire the Open WebUI data and legacy hostnames.
