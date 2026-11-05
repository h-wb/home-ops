#!/bin/sh
# Applies the prototype's OpenShell state from git, so nothing in the gateway is hand-made:
# Hermes managed config and the Memini plugin (config PVC), provider profiles, providers,
# templates and sandboxes. Idempotent; the Job reruns whenever this ConfigMap changes.
# Flux substitutes dollar-brace references in this file, so it uses only plain $VAR forms.
set -eu
log() { echo "[apply] $*"; }

# --- Hermes managed config and the Memini plugin, per scope ---------------------------------
base="https://raw.githubusercontent.com/eleboucher/memini-hermes/$MEMINI_PLUGIN_REF"
curl -fsSLo /tmp/plugin.py "$base/__init__.py"
curl -fsSLo /tmp/plugin.yaml "$base/plugin.yaml"
echo "$MEMINI_PLUGIN_SHA256  /tmp/plugin.py" | sha256sum -c -
echo "$MEMINI_PLUGIN_YAML_SHA256  /tmp/plugin.yaml" | sha256sum -c -
# Upstream turns capture on when the handshake fails; keep it off (obsidian-workspace
# docs/assistant/assistant-integration). The hash check fails closed if the line moves.
sed -i 's/settings\["capture"\] if isinstance(settings.get("capture"), bool) else True/settings["capture"] if isinstance(settings.get("capture"), bool) else False/' /tmp/plugin.py
echo "$MEMINI_PLUGIN_PATCHED_SHA256  /tmp/plugin.py" | sha256sum -c -
for scope in general private; do
  dir="/hermes-config/$scope"
  mkdir -p "$dir/memini-plugin"
  cp "/config/hermes-$scope.yaml" "$dir/config.yaml"
  cp /tmp/plugin.py "$dir/memini-plugin/__init__.py"
  cp /tmp/plugin.yaml "$dir/memini-plugin/plugin.yaml"
  chmod -R a+rX "$dir"
  log "config $scope written"
done

# --- Gateway access with the chart's client bundle ------------------------------------------
mtls="$HOME/.config/openshell/gateways/proto/mtls"
mkdir -p "$mtls"
cp /etc/openshell-client-tls/ca.crt /etc/openshell-client-tls/tls.crt /etc/openshell-client-tls/tls.key "$mtls/"
chmod 600 "$mtls"/*
openshell gateway add https://openshell.proto.svc:8080 --local --name proto >/dev/null
openshell status | grep -q 'Status: Connected'

# --- Provider profiles: import, or update in place with the gateway's resource_version ------
for f in /config/profile-*.yaml; do
  id=$(yq '.id' "$f")
  if openshell profile import -f "$f" >/dev/null 2>&1; then
    log "profile $id imported"
  else
    rv=$(openshell profile export "$id" -o yaml | yq '.resource_version')
    yq ".resource_version = $rv" "$f" >/tmp/profile.yaml
    openshell profile update "$id" -f /tmp/profile.yaml >/dev/null
    log "profile $id updated"
  fi
done

# --- Providers: credential values pass from this pod's env to the gateway, nowhere else -----
# Usage: VAR=value upsert_provider <name> <profile> <VAR>, with VAR exported.
upsert_provider() {
  if openshell provider get "$1" >/dev/null 2>&1; then
    openshell provider update "$1" --credential "$3" >/dev/null
    log "provider $1 updated"
  else
    openshell provider create --name "$1" --type "$2" --credential "$3" >/dev/null
    log "provider $1 created"
  fi
}
(LITELLM_API_KEY=$LITELLM_GENERAL_KEY && export LITELLM_API_KEY && upsert_provider litellm-general proto-litellm LITELLM_API_KEY)
(LITELLM_API_KEY=$LITELLM_PRIVATE_KEY && export LITELLM_API_KEY && upsert_provider litellm-private proto-litellm LITELLM_API_KEY)
(MEMINI_API_KEY=$MEMINI_GENERAL_KEY && export MEMINI_API_KEY && upsert_provider memini-general proto-memini-general MEMINI_API_KEY)
(MEMINI_API_KEY=$MEMINI_PRIVATE_KEY && export MEMINI_API_KEY && upsert_provider memini-private proto-memini-private MEMINI_API_KEY)

# --- Templates and sandboxes, one per scope -------------------------------------------------
# The plugin cannot live outside the agent-writable HERMES_HOME (Memini is not a bundled
# provider), so every start restores it from the read-only mount and checks its hash.
# shellcheck disable=SC2016 # expands inside the sandbox, not here
start='set -eu
mkdir -p "$HERMES_HOME/plugins/memini"
cp /etc/hermes/memini-plugin/__init__.py /etc/hermes/memini-plugin/plugin.yaml "$HERMES_HOME/plugins/memini/"
echo "$MEMINI_PLUGIN_SHA256  $HERMES_HOME/plugins/memini/__init__.py" | sha256sum -c - >/dev/null
exec hermes gateway run'

for scope in general private; do
  name="hermes-$scope"
  # Pinned to tal1s, the only node with Yama ptrace_scope 1 (talos/main/nodes/192.168.1.191.yaml.j2).
  driver=$(jq -nc --arg scope "$scope" '{kubernetes: {
    pod: {node_selector: {"kubernetes.io/hostname": "tal1s"}},
    volumes: [{name: "hermes-config", persistent_volume_claim: {claim_name: "hermes-config", read_only: true}}],
    containers: {agent: {volume_mounts: [{name: "hermes-config", mount_path: "/etc/hermes", sub_path: $scope, read_only: true}]}}}}')
  template_hash=$(printf '%s|%s|%s|%s' "$HERMES_IMAGE" "$driver" "$MEMINI_PLUGIN_PATCHED_SHA256" "$start" | sha256sum | cut -c1-16)
  current=$(openshell sandbox get "$name" -o json 2>/dev/null || echo '{}')

  if [ "$(echo "$current" | jq -r '.labels["proto.template"] // ""')" = "$template_hash" ]; then
    # Same workload: refresh the policy and restart, so config and filesystem rules apply.
    openshell policy set "$name" --policy "/config/policy-$scope.yaml" --yes --wait >/dev/null
    openshell sandbox stop "$name" >/dev/null
    openshell sandbox start "$name" >/dev/null
    log "sandbox $name restarted"
    continue
  fi

  if [ "$current" != '{}' ]; then
    openshell sandbox delete "$name" >/dev/null
    while openshell sandbox get "$name" >/dev/null 2>&1; do sleep 2; done
  fi
  openshell sandbox template delete "$name" >/dev/null 2>&1 || true
  openshell sandbox template create "$name" \
    --image "$HERMES_IMAGE" \
    --driver-config-json "$driver" \
    --label "assistant.scope=$scope" \
    --env HERMES_HOME=/sandbox/hermes \
    --env "MEMINI_BASE_URL=http://memini-proto-$scope.proto.svc.cluster.local:8080" \
    --env "MEMINI_NAMESPACE=proto-$scope" \
    --env "MEMINI_PLUGIN_SHA256=$MEMINI_PLUGIN_PATCHED_SHA256" >/dev/null
  openshell sandbox create --name "$name" --template "$name" \
    --provider "litellm-$scope" --provider "memini-$scope" --no-auto-providers \
    --policy "/config/policy-$scope.yaml" \
    --label "proto.template=$template_hash" \
    --restart-policy always --detach --no-tty \
    -- sh -c "$start" >/dev/null
  log "sandbox $name created"
done

openshell sandbox list
