---
name: alert-triage
description: Investigate firing Grafana/Alertmanager alerts and report each new one in the Matrix Inbox. Use when the alert-triage routine runs.
# Disabled for now: with no schedule below, routines/sync.sh creates no cron
# job for this routine (and removes the old one on the next pod start). To
# re-enable, uncomment:
# metadata:
#   schedule: "*/15 * * * *"
#   model: mistral/mistral-large-4
---

# Alert triage

Runs every fifteen minutes when scheduled (disabled for now — no schedule in
the front matter). Read-only: list what is firing, investigate it, and
tell the user about each new alert in the Matrix Inbox. A scheduled run has nobody to
approve a write (`cron_mode: deny`), so never call a write-capable tool — not
on the cluster, not on Grafana, not a workshop: spawning a Paseo investigator
is the user's call, they reply "agent" to the message.

Call these tools by their exact names with `tool_call`. If a name is not
found, search for the part after `mcp__tools__`.

## Read the firing alerts

1. `mcp__tools__grafana_alerting_rules_read` with `operation: "list"`,
   `states: ["firing"]`, `limit_alerts: 200`: the Grafana-managed rules.
2. If that returns no rules, repeat the call with `datasource_uid` set to the
   alertmanager datasource's uid (find it with
   `mcp__tools__grafana_list_datasources`, the datasource named
   `alertmanager`). If that uid is refused — only Prometheus/Loki datasources
   back datasource-managed rules — use the `prometheus` datasource's uid
   instead. On the datasource path the `states` filter is not applied, so keep
   only the rules whose own `state` is `"firing"`.

Give every firing alert a fingerprint that comes out identical on every run
for the same alert: the rule's uid, or for datasource-managed rules
`<rule_group>/<title>`, plus the alert instance's labels, for example
`<rule>|<namespace>|<sorted label=value pairs>`. The namespace comes from the
instance labels (`namespace` or `exported_namespace`); if the alert carries
none, say so, do not guess one.

## State

Read `$HERMES_HOME/alert-triage-state.json`; a missing or unreadable file
means an empty state. Shape:

```json
{
  "alerts": {
    "<fingerprint>": {
      "name": "KubeHpaMaxedOut",
      "severity": "warning",
      "namespace": "media",
      "firstSeen": "2026-11-11T10:05:00-05:00",
      "notified": true,
      "resolvedAt": null
    }
  }
}
```

Times are ISO 8601 with the `America/Toronto` offset. After processing, write
the updated state back to that file once, at the end of the run.

## New firing alerts

A firing alert is new when its fingerprint is not in the state, or is there
without `notified`. For each new one:

1. Rule details: `mcp__tools__grafana_alerting_rules_read` with
   `operation: "get"` and the rule's `rule_uid`. Datasource-managed rules have
   no uid; their list entry already carries the details (`query`,
   `annotations`, `labels`, `rule_group`), so use that.
2. `mcp__tools__kubectl_kubectl_get` with `resource_type: "pods"`, the
   alert's `namespace`, `output: "wide"`: the pod states there.
3. `mcp__tools__kubectl_kubectl_get` with `resource_type: "events"`, the
   alert's `namespace`, `sort_by: ".lastTimestamp"`, and `type: "Warning"` if
   the call supports it: what is going wrong there. If the alert labels name a
   resource (`pod`, `deployment`, `horizontalpodautoscaler`, ...), add its
   `name` or a `field_selector` on it.
4. The failing resource itself: `mcp__tools__kubectl_kubectl_get` with the
   `resource_type` and `name` from the alert labels, the `namespace`,
   `output: "yaml"` — or `mcp__tools__kubectl_kubectl_describe` with the same
   `resource_type`, `name` and `namespace`.

Then record it in the state: `name`, `severity` (the rule's `severity`
label), `namespace`, `firstSeen` (now), `notified: true`, `resolvedAt: null`.

## Resolved alerts

A fingerprint in the state with `notified: true` and `resolvedAt: null` that
is not firing anymore: set `resolvedAt` to now. Keep the entry — it is the
record that this alert was reported.

## Write

The run's delivery goes to the Matrix Inbox room (`--deliver matrix` in
routines/sync.sh). One message per new alert, in this
shape, nothing else around it:

```
🚨 <alert name> (<severity>)
ns <namespace> · first seen <time, America/Toronto>
- <finding>
- <finding>
- <finding>
Reply "agent" to spawn a Paseo investigator.
```

- Two or three findings, each one line, each from a tool result of this run
  (pod CrashLoopBackOff, event reason, HPA at max, ...). Factual, no advice,
  no speculation.
- One short notice per resolved alert:
  `✅ <alert name> resolved (first seen <time>, resolved <time>, ns <namespace>)`.
- Nothing new and nothing resolved: reply with only `[SILENT]`.

## Check

- Every finding comes from a tool result of this run.
- No write-capable tool was called; nothing on the cluster or in Grafana was
  changed, and no agent was spawned.
- The state file was written back exactly once, after all messages.
