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

| Pod         | Trigger                                                      | Status                                                                                                                                                                                                    |
| ----------- | ------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| code-server | the `bootstrap` init container                               | uses it                                                                                                                                                                                                   |
| neko        | XFCE autostart (xfconf needs the session D-Bus)              | follow-up: replace its `neko-provision` ConfigMap and both autostart entries with this ConfigMap and one entry running `dotfiles-bootstrap --pull --hold ~/.neko-hold --log neko-bootstrap --timeout 900` |
| Paseo pods  | native `mise bootstrap --from` in the `tools` init container | stays: no workstation layer, so no secrets session; a fresh read-only `emptyDir` checkout every start; mise pinned by image                                                                               |
