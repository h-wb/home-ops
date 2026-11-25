---
area: "[[Homelab]]"
categories:
  - "[[Resources]]"
reviewed: 2026-11-25
summary: The Component that moves a workstation pod's dotfiles clone to the cluster's pinned commit and bootstraps it, when it runs, and how it fails safe.
topics:
  - "[[Workshop]]"
created: 2026-11-16T11:13
---

# dotfiles

Bootstraps a pod from the owner's dotfiles. home-ops states two things per pod
and nothing else about what gets installed or configured:

1. **Which commit**: `DOTFILES_REF`, one value for the cluster, substituted into
   every child Kustomization by `kubernetes/clusters/main/ks.yaml`. Renovate
   proposes the head of dotfiles `master` in a scheduled PR. Review the exact
   SHA and its CI before merging. Do not enable auto-merge without owner review
   and required checks enforced on dotfiles `master`. Keep the pin reachable
   from a branch so the Paseo pods can clone it.
2. **Which environment**: `DOTFILES_ENV` in the app's `ks.yaml`, a set from the
   dotfiles' `miserc.toml` `[env_sets]`, optionally followed by layers for this
   pod only (`code-server`, `neko`, `neko,extra-layer`).

The Component adds a ConfigMap `${APP}-dotfiles` with `dotfiles-bootstrap` and
`dotfiles-bootstrap.desktop`. The app mounts it at `/opt/dotfiles` and decides
when it runs:

- `sh /opt/dotfiles/dotfiles-bootstrap fetch` moves the `~/.dotfiles` git
  clone to that commit (detached), cloning it on an empty volume. Local changes
  go to a stash, never away: develop in `~/Repositories/dotfiles`. Ignored files
  (`miserc.local.toml`, `config.local.toml`) and local branches stay. A failed
  fetch keeps the commit already checked out.
- `... run` runs that checkout's `scripts/pod-bootstrap $DOTFILES_ENV` by path.
- No argument does both. It always exits 0: the pod's own program starts anyway.

The dotfiles own everything after that: the log and status in
`~/.local/state/pod-bootstrap.{log,status}` and the `pod-bootstrap` doctor
check (`mise doctor project`), which also fails when the last start applied a
commit other than the pin (`stale`: the fetch failed).

| Pod         | `DOTFILES_ENV` | Trigger                                                                                                                                                                      |
| ----------- | -------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| code-server | `code-server`  | the `bootstrap` init container, no argument                                                                                                                                  |
| neko        | `neko`         | `fetch` in the `dotfiles` init container (a pinned git image: the neko image has none); `run` from the system XFCE autostart entry (xfconf, apt and `/etc` need the session) |

The Paseo pods use the same two inputs without this hook: their `tools` init
container runs `mise -E paseo,paseo-overlay bootstrap --from
https://github.com/h-wb/dotfiles.git?ref=${DOTFILES_REF} --save-env` into an
`emptyDir`, fresh at every start and read-only in the app container (mise from
an image volume; no secrets session to protect). `tests/test_dotfiles.py`
renders the hook as Flux does and runs it against scratch homes with a local
remote; `tests/test_paseo.py` checks the Paseo arguments.

## When a pin goes bad

A pod never stops starting because of the dotfiles. The signals: the
`DotfilesBootstrapIncomplete` alert (vmalert on the pods' logs; neko's
in-session run only logs to its volume), `mise doctor project` in the pod, and
on neko the n8n workflow "Anki → Nextcloud: Korean Vocabulary" (hourly at :10).

Revert the `DOTFILES_REF` update to a known-good commit. This rolls every
consumer.

Before this hook took an environment, the old ones ran a `scripts/pod-bootstrap`
without arguments from a clone on `master`. To go back to them, revert both
pull requests (dotfiles first: Paseo and neko read its `master`), then on neko
and code-server, before the old hooks run:

```sh
git -C ~/.dotfiles switch master && git -C ~/.dotfiles pull --ff-only
```
