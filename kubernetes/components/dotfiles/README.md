# dotfiles

Bootstraps a pod from the owner's dotfiles. home-ops states two things per pod
and nothing else about what gets installed or configured:

1. **Which commit**: `DOTFILES_REF`, one value for the cluster, substituted into
   every child Kustomization by `kubernetes/clusters/main/ks.yaml`. Renovate
   bumps it to the head of the dotfiles' `master` (one PR, merged between 03:00
   and 06:00 New York time; `.renovaterc.json5`).
2. **Which environment**: `DOTFILES_ENV` in the app's `ks.yaml`, a set from the
   dotfiles' `miserc.toml` `[env_sets]`, optionally followed by layers for this
   pod only (`code-server`, `neko`, `neko,extra-layer`).

The Component adds a ConfigMap `${APP}-dotfiles` with `dotfiles-bootstrap` and
`dotfiles-bootstrap.desktop`. The app mounts it at `/opt/dotfiles` and decides
when it runs:

- `sh /opt/dotfiles/dotfiles-bootstrap fetch` downloads that commit's tarball
  and swaps it in at `~/.dotfiles`, fresh at every start. Whatever was there
  goes, local edits included: develop in `~/Repositories/dotfiles`. A failed
  download keeps the previous checkout.
- `... run` runs that checkout's `scripts/pod-bootstrap $DOTFILES_ENV` by path.
- No argument does both. It always exits 0: the pod's own program starts anyway.

The dotfiles own everything after that: the log and status in
`~/.local/state/pod-bootstrap.{log,status}` and the `pod-bootstrap` doctor
check (`mise doctor project`), which also fails when the last start applied a
commit other than the pin (`stale`: the download failed).

| Pod         | `DOTFILES_ENV` | Trigger                                                                                                                        |
| ----------- | -------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| code-server | `code-server`  | the `bootstrap` init container, no argument                                                                                    |
| neko        | `neko`         | `fetch` in the `dotfiles` init container; `run` from the system XFCE autostart entry (xfconf, apt and `/etc` need the session) |

The Paseo pods use the same two inputs without this hook: their `tools` init
container runs `mise -E paseo,paseo-overlay bootstrap --from
https://github.com/h-wb/dotfiles.git?ref=${DOTFILES_REF} --save-env` into an
`emptyDir`, fresh at every start and read-only in the app container (mise from
an image volume; no secrets session to protect). Hermes' skills Job downloads
the same commit. `tests/test_dotfiles.py` renders the hook as Flux does and runs
it against scratch homes; `tests/test_paseo.py` checks the Paseo arguments.

## When a pin goes bad

A pod never stops starting because of the dotfiles. The signals: the
`DotfilesBootstrapIncomplete` alert (vmalert on the pods' logs; neko's
in-session run only logs to its volume), `mise doctor project` in the pod, and
on neko the n8n workflow "Anki → Nextcloud: Korean Vocabulary" (hourly at :10).
Roll back by reverting the Renovate merge that bumped `DOTFILES_REF`: every pod
rolls to the previous commit (Reloader for neko and code-server, the changed
spec for Paseo and Hermes).
