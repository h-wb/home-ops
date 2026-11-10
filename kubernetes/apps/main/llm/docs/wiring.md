# Wiring

How each agent is connected today: which path its model calls take, where its
tools come from, and where it remembers things. The design it should match is
[DESIGN.md](../DESIGN.md); the flows are in [flows.md](./flows.md).

Read a diagram left to right. A solid arrow is as designed. A dotted arrow
differs from the design, and is explained under
[Differs from the design](#differs-from-the-design).

The published page draws these diagrams with `build.py`; keep to the node and
arrow forms used here so it can read them.

## At a glance

| Agent                       | Runs in          | Scope   | Models                                               | Tools                         | Memory                         |
| --------------------------- | ---------------- | ------- | ---------------------------------------------------- | ----------------------------- | ------------------------------ |
| Assistant (Hermes)          | Its own pod      | Private | Model gateway, own key                               | Private gateway, in-cluster   | Private store, by plugin       |
| Claude Code                 | General workshop | General | Model gateway, which forwards its subscription login | General gateway, in-cluster   | General store                  |
| OpenCode                    | General workshop | General | Model gateway, and Mistral's API directly            | General gateway, in-cluster   | General store, server + plugin |
| OpenCode                    | Private workshop | Private | Model gateway, and Mistral's API directly            | Private gateway, in-cluster   | Private store, server + plugin |
| Claude Code, Claude Desktop | Workstation      | General | Anthropic directly, own login                        | General gateway, from outside | General store, from outside    |
| Codex                       | Workstation      | General | OpenAI directly, own login                           | General gateway, from outside | General store, from outside    |
| Vibe                        | Workstation      | Private | Mistral directly, own key                            | Private gateway, from outside | Private store, from outside    |

In the pods the tool gateways need no key: a network rule admits only that
scope's pods, and the tool servers behind them answer the gateways only. From a workstation they are reached through Envoy with a key per
scope. Memory always needs the client's own key. The agents' tool and memory
servers are defined once, in dotfiles (`conf.d/ai/`), and rendered per scope.

## The assistant

Hermes, in its own pod, private scope. Its network rule allows the three
destinations below and DNS, nothing else. The private workshop reaches it
through an exec bridge, which goes once the messaging app is in use.

```mermaid
flowchart LR
    A["Assistant<br/>Hermes"]:::private
    L["Model gateway<br/>LiteLLM"]:::shared
    MI["Mistral"]:::outside
    T["Private tool gateway<br/>every tool"]:::private
    M["Private memory<br/>Memini"]:::private
    A -->|"own key: Mistral models only"| L
    L --> MI
    A -.->|"no key; tool names hidden"| T
    A -->|"own client key, by plugin"| M
```

- Key: `hermes-private`, three Mistral models.
- The memory plugin is a patched build that records nothing unless told to.

## Claude Code in the general workshop

```mermaid
flowchart LR
    A["Claude Code<br/>general workshop"]:::general
    L["Model gateway<br/>LiteLLM"]:::shared
    AN["Anthropic"]:::outside
    T["General tool gateway<br/>curated tools"]:::general
    M["General memory<br/>Memini"]:::general
    A -->|"subscription login, gateway key"| L
    L -->|"passes it on"| AN
    A -->|"no key, network rule"| T
    A -->|"client key"| M
```

- The gateway holds no Anthropic key: a request without the subscription login
  fails instead of being billed.
- The pod has no Kubernetes credentials; cluster work goes through the tools.

## OpenCode in the general workshop

```mermaid
flowchart LR
    A["OpenCode<br/>general workshop"]:::general
    L["Model gateway<br/>LiteLLM"]:::shared
    CG["ChatGPT"]:::outside
    LO["Local models<br/>the Mac"]:::outside
    MI["Mistral's API<br/>Mistral and GLM models"]:::outside
    T["General tool gateway<br/>curated tools"]:::general
    M["General memory<br/>Memini"]:::general
    A -->|"gateway key"| L
    L -->|"shared login"| CG
    L --> LO
    A -.->|"pod-held API key, direct"| MI
    A -->|"no key, network rule"| T
    A -->|"client key, server and plugin"| M
```

- Roles today: coordinator on ChatGPT through the gateway; build, plan and
  explorer on Mistral models and the reviewer on a GLM model, all direct.

## OpenCode in the private workshop

```mermaid
flowchart LR
    A["OpenCode<br/>private workshop"]:::private
    L["Model gateway<br/>LiteLLM"]:::shared
    LO["Local models<br/>the Mac"]:::outside
    MI["Mistral's API<br/>Mistral and GLM models"]:::outside
    T["Private tool gateway<br/>every tool"]:::private
    M["Private memory<br/>Memini"]:::private
    A -->|"gateway key: local models"| L
    L --> LO
    A -.->|"pod-held API key, direct"| MI
    A -->|"no key, network rule"| T
    A -->|"client key, server and plugin"| M
```

- Its gateway key lists local and Mistral models, but the Mistral calls do not
  go through the gateway.

## Claude Code, Claude Desktop and Codex on a workstation

General scope. Keys come from Proton Pass through fnox when the agent starts.

```mermaid
flowchart LR
    A["Claude Code, Codex<br/>workstation"]:::general
    V["Anthropic, OpenAI"]:::outside
    T["General tool gateway<br/>curated tools"]:::general
    M["General memory<br/>Memini"]:::general
    A -.->|"own login, direct"| V
    A -->|"through Envoy, key per scope"| T
    A -->|"client key"| M
```

## Vibe on a workstation

Private scope.

```mermaid
flowchart LR
    A["Vibe<br/>workstation"]:::private
    MI["Mistral"]:::outside
    T["Private tool gateway<br/>every tool"]:::private
    M["Private memory<br/>Memini"]:::private
    A -.->|"own key, direct"| MI
    A -->|"through Envoy, key per scope"| T
    A -->|"client key"| M
```

## Services that call models

Not agents, but they hold a model gateway key too.

| Service                       | Models on its key                      |
| ----------------------------- | -------------------------------------- |
| Both memory stores            | In-cluster embeddings                  |
| Both tool gateways            | In-cluster embeddings, for tool search |
| Paperless and its OCR helper  | Local models, in-cluster embeddings    |
| Karakeep                      | ChatGPT, in-cluster embeddings         |
| Kritika (pull request review) | ChatGPT, in-cluster embeddings         |
| Lingarr                       | ChatGPT                                |

## Differs from the design

1. **OpenCode calls Mistral's API directly, in both workshops.** The design has
   one path to any model, the gateway, and the gateway key's model list is the
   policy. These calls skip both, so in the private workshop any model on that
   account is reachable. Decided: route them through the gateway and drop the
   API key from the pods. The GLM models served there are trusted.
2. **The assistant cannot see tool names.** The tool gateways put every tool
   behind `find_tool` and `call_tool`. "Writes ask" needs the real names.
   Decided: give the assistant the tools without the search step.
3. **The location repo's clone in the general workshop holds data.** Next to
   the code it has an ignored `data/` directory and a `local-notes.md`. "Repos
   hold code" means those belong on the private side. To do: move them out.
4. **OpenCode records conversations by itself.** Its memory plugin recalls
   before every turn and records after it, in both workshops; the memory
   server next to it adds the on-demand tools. The assistant's plugin is
   patched to record only when told. Each writes to its own scope's store, so
   the rule holds. To decide: whether the workshops keep recording by
   themselves.
5. **Workstation agents call their vendors directly.** The gateway is
   in-cluster only. Accepted: tool use is meant to happen in the workshops.
6. **The general workshop holds a key for OpenCode's hosted models.** A second
   path next to the gateway. Accepted for the general workshop; it never goes
   into the private one.
7. **The private workshop has open internet.** Accepted: an allowlist costs
   too much friction. The assistant stays restricted to its three
   destinations.

Closed on 2026-11-09: tool servers answered any pod in the cluster directly,
and private memory was guarded by its key alone. Both now have a network rule
(`toolhive/config/networkpolicy.yaml`, `memini-private/app/networkpolicy.yaml`).
