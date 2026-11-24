---
area: "[[Homelab]]"
categories:
  - "[[Resources]]"
reviewed: 2026-11-24
summary: The Component that bootstraps a workstation pod from the dotfiles, when it runs, and how it fails safe.
topics:
  - "[[Workshop]]"
created: 2026-11-16T11:13
---

# dotfiles

Bootstraps a workstation pod (dotfiles layer `pod`) from the owner's dotfiles.
home-ops decides **when** it runs; the dotfiles' `scripts/pod-bootstrap`
decides **what** it does. Each exists once.

The Component adds a ConfigMap `${APP}-dotfiles` holding `dotfiles-bootstrap`.
The app mounts it and calls `sh <mount>/dotfiles-bootstrap [options]`, and the
options go to `pod-bootstrap`. The hook:

- clones `~/.dotfiles` when `scripts/pod-bootstrap` is missing, moving a cut-off
  clone aside first (installs git with sudo if the image has none);
- runs that script by path, never through a link the bootstrap manages;
- is time-limited and always exits 0, so the pod's own program starts anyway.

`tests/test_code_server.py` runs it against scratch homes.

| Pod         | Trigger                                                      | Status                                                                                                                      |
| ----------- | ------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------- |
| code-server | the `bootstrap` init container                               | uses it                                                                                                                     |
| neko        | XFCE autostart (xfconf needs the session D-Bus)              | does not use it today (HOMEL-66): its own `neko-provision` ConfigMap and autostart entries                                  |
| Paseo pods  | native `mise bootstrap --from` in the `tools` init container | stays: no workstation layer, so no secrets session; a fresh read-only `emptyDir` checkout every start; mise pinned by image |
