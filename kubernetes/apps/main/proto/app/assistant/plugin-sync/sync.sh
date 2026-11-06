#!/bin/sh
# Writes the Memini Hermes plugin, pinned and with the capture fallback patched, to the shared
# volume that each Hermes pod mounts read-only at $HERMES_HOME/plugins/memini. The agent pods
# never fetch it themselves: their egress is limited to DNS, LiteLLM and Memini.
# Flux substitutes dollar-brace references in this file, so it uses only plain $VAR forms.
set -eu
base="https://raw.githubusercontent.com/eleboucher/memini-hermes/$MEMINI_PLUGIN_REF"
curl -fsSLo /tmp/plugin.py "$base/__init__.py"
curl -fsSLo /tmp/plugin.yaml "$base/plugin.yaml"
echo "$MEMINI_PLUGIN_SHA256  /tmp/plugin.py" | sha256sum -c -
echo "$MEMINI_PLUGIN_YAML_SHA256  /tmp/plugin.yaml" | sha256sum -c -
# Upstream turns capture on when the handshake fails; keep it off (obsidian-workspace
# docs/assistant/assistant-integration). The hash check fails closed if the line moves.
sed -i 's/settings\["capture"\] if isinstance(settings.get("capture"), bool) else True/settings["capture"] if isinstance(settings.get("capture"), bool) else False/' /tmp/plugin.py
echo "$MEMINI_PLUGIN_PATCHED_SHA256  /tmp/plugin.py" | sha256sum -c -
mkdir -p /plugins/memini
cp /tmp/plugin.py /plugins/memini/__init__.py
cp /tmp/plugin.yaml /plugins/memini/plugin.yaml
chmod -R a+rX,go-w /plugins/memini
echo "memini plugin $MEMINI_PLUGIN_REF written"
