"""Render the mounted data-scope policy into this pod's agent homes.

Ships with home-ops' paseo base (next to the policy ConfigMap it consumes), and
runs from provision.sh after dotfiles' bootstrap; dotfiles provides only the
python runtime via mise. Never infer a private host's provider grants.
"""
import json
import os
import re
from pathlib import Path


def apply_policy(policy, scope, config):
    settings = policy["scopes"][scope]  # unknown scopes fail closed
    allowed = settings["providers"]
    for name in allowed:
        if scope not in policy["providers"][name]["allowed_data_scopes"]:
            raise ValueError(f"{name} is not eligible for {scope}")
    agents = config.setdefault("agents", {})
    providers = agents.setdefault("providers", {})
    for name in providers.keys() | policy["providers"].keys():
        providers.setdefault(name, {})["enabled"] = name in allowed
    servers = [{"name": "toolhive-" + scope, "transport": "streamable-http",
                "url": settings["mcp_url"], "auth": {"type": "static",
                "api_key_env": "MCP_API_KEY", "api_key_header": "x-api-key",
                "api_key_format": "{token}"}, "startup_timeout_sec": 60,
                "tool_timeout_sec": 120}]
    if scope == "general":
        servers.append({"name": "memini-general", "transport": "streamable-http",
                        "url": settings["memory_url"], "auth": {"type": "static",
                        "api_key_env": "MEMINI_API_KEY", "api_key_header": "Authorization",
                        "api_key_format": "Bearer {token}"}})
    for name in allowed:
        providers[name]["paseoTools"] = {"disabledTools": settings.get("disabled_paseo_tools", [])}
    vibe = providers["mistral-vibe"]
    vibe.setdefault("env", {})["VIBE_MCP_SERVERS"] = json.dumps(servers)
    # Overwrite a stale general-host fallback list on a private home.
    if scope == "private":
        agents["metadataGeneration"] = {"providers": [{"provider": settings["metadata_provider"]}]}
    return config


def main():
    scope = os.environ.get("PASEO_DATA_SCOPE", "general")
    policy_path = Path(os.environ.get("PASEO_DATA_POLICY", "/etc/paseo/policy.json"))
    if not policy_path.exists():
        raise SystemExit("Paseo data policy missing; refusing to configure providers")
    policy = json.loads(policy_path.read_text())
    root = Path(os.environ.get("PASEO_HOME", str(Path.home() / ".paseo")))
    root.mkdir(parents=True, exist_ok=True)
    target = root / "config.json"
    config = json.loads(target.read_text()) if target.exists() else {"version": 1}
    config = apply_policy(policy, scope, config)
    temp = root / "config.json.scope-tmp"
    temp.write_text(json.dumps(config, indent=2) + "\n")
    temp.chmod(0o600)
    temp.replace(target)
    if scope == "general":
        configure_native_mcp(policy["scopes"][scope])
    print(f"Paseo scope: {scope}; enabled providers: {', '.join(policy['scopes'][scope]['providers'])}")


def configure_native_mcp(settings):
    """Write env references, never credentials. Preserve unrelated client config."""
    target = Path.home() / ".claude.json"
    config = json.loads(target.read_text()) if target.exists() else {}
    servers = config.setdefault("mcpServers", {})
    for name in ("toolhive-ops", "home-mcp", "memini-code"):
        servers.pop(name, None)
    servers["toolhive-general"] = {"type": "http", "url": settings["mcp_url"],
        "headers": {"x-api-key": "${MCP_API_KEY}"}}
    servers["memini-general"] = {"type": "http", "url": settings["memory_url"],
        "headers": {"Authorization": "Bearer ${MEMINI_API_KEY}"}}
    atomic_json(target, config)
    root = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    root.mkdir(parents=True, exist_ok=True)
    target = root / "config.toml"
    text = target.read_text() if target.exists() else ""
    names = "toolhive-ops|toolhive-general|home-mcp|memini-code|memini-general"
    # Only remove managed tables and their subtables. Keep every other setting.
    text = re.sub(r'(?ms)^\[mcp_servers\.(?:' + names + r')(?:\.[^\]]+)?\]\s*\n.*?(?=^\[|\Z)', "", text)
    text = text.rstrip() + "\n"
    text += '\n[mcp_servers.toolhive-general]\nurl = ' + json.dumps(settings["mcp_url"]) + '\nenv_http_headers = { "x-api-key" = "MCP_API_KEY" }\n'
    text += '\n[mcp_servers.memini-general]\nurl = ' + json.dumps(settings["memory_url"]) + '\nbearer_token_env_var = "MEMINI_API_KEY"\n'
    temp = root / "config.toml.scope-tmp"
    temp.write_text(text)
    temp.chmod(0o600)
    temp.replace(target)


def atomic_json(target, value):
    temp = target.with_name(target.name + ".scope-tmp")
    temp.write_text(json.dumps(value, indent=2) + "\n")
    temp.chmod(0o600)
    temp.replace(target)


if __name__ == "__main__":
    main()
