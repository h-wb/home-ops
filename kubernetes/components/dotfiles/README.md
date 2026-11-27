---
area: "[[Homelab]]"
categories:
  - "[[Resources]]"
reviewed: 2026-11-25
summary: The Component that moves a workstation pod's dotfiles clone to the cluster's DOTFILES_REF and bootstraps it, when it runs, and how it fails safe.
topics:
  - "[[Workshop]]"
created: 2026-11-16T11:13
---

# dotfiles

Bootstraps a pod from the owner's dotfiles. home-ops states two things per pod
and nothing else about what gets installed or configured:

1. **Which ref**: `DOTFILES_REF`, one value for the cluster, substituted into
   every child Kustomization by `kubernetes/clusters/main/ks.yaml`: `master`.
   Every pod takes the newest `master` at its next start; nothing restarts a
   pod when `master` moves. dotfiles `master` takes a pull request and the
   owner's approval (ruleset `default-branch`).
2. **Which environment**: `DOTFILES_ENV` in the app's `ks.yaml`, a set from the
   dotfiles' `miserc.toml` `[env_sets]`, optionally followed by layers for this
   pod only (`code-server`, `neko`, `neko,extra-layer`).

The Component adds a ConfigMap `${APP}-dotfiles` with `dotfiles-bootstrap` and
`dotfiles-bootstrap.desktop`. The hook runs the dotfiles' two steps, the ones
every dotfiles machine runs ([dotfiles' docs/mise.md](https://github.com/h-wb/dotfiles/blob/master/docs/mise.md#one-bootstrap-two-steps)).
The app mounts it at `/opt/dotfiles` and decides when each step runs:

- `sh /opt/dotfiles/dotfiles-bootstrap fetch`: `mise -E $DOTFILES_ENV bootstrap
  --from https://github.com/h-wb/dotfiles.git?ref=$DOTFILES_REF --update
  --save-env --only final-hook` moves the `~/.dotfiles` clone to that ref
  (cloning it on an empty volume), links `~/.config/mise` to it and saves the
  environment. Local branches and ignored files (`*.local.toml`) stay. A local
  change in the way stops the move, and so does a failed fetch: the pod then
  runs the commit already there, and the hook logs `fetch failed`. Develop in
  `~/Repositories/dotfiles`.
- `... run`: `mise run apply --unattended` in that checkout, with a live
  Proton Pass session or without one (the dotfiles' `fresh` and `protect`).
- No argument does both. It always exits 0: the pod's own program starts anyway.

mise is the `ghcr.io/jdx/mise` image, the same as the Paseo pods': mounted at
`/opt/mise` and first on `PATH`, because the shims point at it. neko's `fetch`
runs on that image itself, since the neko image has no git. Its tag (Renovate)
must stay at or above the dotfiles' `min_version`.

Only the hook's own lines reach the pod's log; mise's output goes to
`~/.local/state/dotfiles.log` on the volume. The dotfiles own the status,
`~/.local/state/dotfiles.status`, and the `pod-start` doctor check (`mise
doctor project`), which also fails when `DOTFILES_REF` is a commit and the last
start applied another.

| Pod         | `DOTFILES_ENV` | Trigger                                                                                                                        |
| ----------- | -------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| code-server | `code-server`  | the `bootstrap` init container, no argument                                                                                    |
| neko        | `neko`         | `fetch` in the `dotfiles` init container; `run` from the system XFCE autostart entry (xfconf, apt and `/etc` need the session) |

The Paseo pods run step 1 alone in their `tools` init container, `mise -E
paseo,paseo-overlay bootstrap --from
https://github.com/h-wb/dotfiles.git?ref=${DOTFILES_REF} --save-env` without
`--only`, into an `emptyDir` that is fresh at every start and read-only in the
app container. They hold no secrets, so there is no step 2. `tests/test_dotfiles.py`
renders the hook as Flux does and runs it with real mise and git against a
local remote; `tests/test_paseo.py` checks the Paseo arguments.

## When dotfiles goes bad

A pod never stops starting because of the dotfiles. The signals: the
`DotfilesBootstrapIncomplete` alert (vmalert on the pods' logs; neko's
in-session run only logs to its volume), `mise doctor project` in the pod, and
on neko the n8n workflow "Anki → Nextcloud: Korean Vocabulary" (hourly at :10).

Revert the change in dotfiles: each pod takes it at its next start. To hold
every pod on a known-good commit meanwhile, set `DOTFILES_REF` to that commit;
this rolls every consumer.

Before this hook, the old ones ran a `scripts/pod-bootstrap` without
arguments from a clone on `master`. To go back to them, revert both pull
requests (dotfiles first: Paseo and neko read its `master`), then on neko and
code-server, before the old hooks run:

```sh
git -C ~/.dotfiles switch master && git -C ~/.dotfiles pull --ff-only
```
