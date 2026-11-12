# Context usage monitoring

Use the LiteLLM Grafana dashboard's **Context Usage by Consumer/Model** section.
Select a consumer (default `Paseo General`), model and time range to inspect:

- Input/output tokens and average input tokens per model request.
- Provider prompt-cache reads/writes and reasoning tokens.
- Model requests and LiteLLM response-cache hits/misses.

The underlying metrics were verified live on 2026-11-12. No controlled
MCP-versus-CLI benchmark has been run. The dashboard changes must be deployed
before the new section is available.

## Interpretation

Counters measure cumulative request volume, not unique context or context-window
occupancy. The shared Paseo key combines sessions; isolated benchmark traffic is
needed to compare MCP and CLI reliably. Prometheus `increase()` approximates
short trials, so use per-request usage records when exact trial totals matter.

Provider prompt caching and LiteLLM's Redis response cache are different.
The latter has a configured 300-second TTL; check whether it serves a trial
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
