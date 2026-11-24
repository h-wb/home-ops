---
area: "[[Homelab]]"
categories:
  - "[[Resources]]"
reviewed: 2026-11-24
summary: How to read the context usage section of the LiteLLM Grafana dashboard, and how a fair MCP-versus-CLI comparison would be run on it.
topics:
  - "[[Model gateway]]"
  - "[[Tool gateway]]"
created: 2026-11-12T16:48
---

# LiteLLM dashboard: context usage

`litellm.json` here is the LiteLLM Grafana dashboard. Its Context Usage by Consumer/Model section
shows, for a consumer (default `Paseo General`), model and time range:

- Input/output tokens and average input tokens per model request.
- Provider prompt-cache reads/writes and reasoning tokens.
- Model requests and LiteLLM response-cache hits/misses.

No controlled MCP-versus-CLI comparison has been run yet.

## Interpretation

Counters measure cumulative request volume, not unique context or context-window
occupancy. The shared Paseo key combines sessions; isolated benchmark traffic is
needed to compare MCP and CLI reliably. Prometheus `increase()` approximates
short trials, so use per-request usage records when exact trial totals matter.

Provider prompt caching and LiteLLM's Redis response cache are different.
The latter has a 300-second TTL (`../litellmproxy.yaml`); check whether it serves a trial
before interpreting its usage. Do not disable shared caching globally.
Missing detail series mean unreported or unobserved data, not necessarily zero.
Do not add reasoning to output or cached tokens to input without verifying
provider normalization, or double-count legacy provider-cache metric aliases.

## Future comparisons

Compare equivalent read-only tasks with the same model, instructions and bounded
results. Alternate CLI, MCP cold discovery (`find_tool` then `call_tool`), and
MCP warm discovery (schema already known), with at least three trials each.
Record task success, requests, tokens, cache behavior and elapsed time. Account
for warm-up history separately; discovery warmth is not provider cache warmth.
Do not introduce session/run IDs as Prometheus labels or log prompts centrally.
