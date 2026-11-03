"""Enforce tool history against the shared general/private backend policy.

Every deployment behind an alias must be eligible for private data before the
request may carry private tool calls or results. Gateway call_tool arguments are
inspected too. General tool prefixes and endpoint eligibility come from the
home-ops policy mounted at /etc/agent-data-policy/policy.json. Missing policy
fails startup; unknown backends get general tools only. Pasted private text and
attachments are outside this protocol guard. Direct subscription agents bypass
LiteLLM and are separated by their execution environments instead.

The separately scoped public-repository reviewer key retains an explicit tool
policy override. This is never granted to interactive Paseo keys.
"""

import ipaddress
import json
import logging
from pathlib import Path
from urllib.parse import urlparse

from fastapi import HTTPException
from litellm.integrations.custom_logger import CustomLogger

log = logging.getLogger("LiteLLM Proxy")

_POLICY = json.loads(Path("/etc/agent-data-policy/policy.json").read_text())
_LOCAL_RULE = _POLICY["private_backends"]["local"]
_MISTRAL_RULE = _POLICY["private_backends"]["mistral"]
_LOCAL_SUFFIXES = tuple(_LOCAL_RULE["host_suffixes"])
_TOOL_KEYS = ("tools", "functions", "tool_choice", "function_call")
_TOOL_ROLES = ("tool", "function")
_GENERAL_PREFIXES = tuple(_POLICY["general_tool_prefixes"])
_GATEWAY_TOOLS = ("find_tool", "call_tool")
_TOOL_ITEM_TYPES = ("function_call", "function_call_output", "mcp_call", "mcp_list_tools", "tool_result", "tool_use")


def _is_local_base(api_base):
    if "private" not in _LOCAL_RULE["allowed_data_scopes"]:
        return False
    if not api_base or not isinstance(api_base, str):
        return False
    host = urlparse(api_base).hostname or ""
    if not host:
        return False
    if host == "localhost" or (_LOCAL_RULE["allow_bare_service_names"] and "." not in host):  # bare in-cluster service name
        return True
    try:
        address = ipaddress.ip_address(host)
        return _LOCAL_RULE["allow_private_ips"] and (address.is_private or address.is_loopback)
    except ValueError:
        return host.endswith(_LOCAL_SUFFIXES)


def _allows_private_deployment(deployment):
    params = deployment.get("litellm_params") or {}
    api_base = params.get("api_base")
    model = params.get("model") or ""
    # Classify the actual endpoint, including all deployments behind aliases.
    if ("private" in _MISTRAL_RULE["allowed_data_scopes"]
            and isinstance(model, str) and model.startswith(_MISTRAL_RULE["model_prefix"])):
        if not api_base:
            return True  # LiteLLM defaults to the official Mistral endpoint.
        if isinstance(api_base, str):
            parsed = urlparse(api_base)
            if (parsed.scheme == "https" and parsed.hostname == _MISTRAL_RULE["https_host"]
                    and not parsed.username and not parsed.password
                    and parsed.port in (None, 443)):
                return True
    return _is_local_base(api_base)


def _allows_private_model(alias):
    """True only when every resolved backend is eligible for private data."""
    try:
        from litellm.proxy.proxy_server import llm_router

        deployments = llm_router.get_model_list(model_name=alias) if llm_router else None
        if not deployments:
            return False
        return all(_allows_private_deployment(d) for d in deployments)
    except Exception:
        log.warning("data scope guard: could not classify %r, allowing general data only", alias, exc_info=True)
        return False


def _carries_tools(data):
    if any(data.get(key) for key in _TOOL_KEYS):
        return True
    items = list(data.get("messages") or [])
    inputs = data.get("input")
    if isinstance(inputs, list):
        items += inputs
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("role") in _TOOL_ROLES or item.get("tool_calls") or item.get("type") in _TOOL_ITEM_TYPES:
            return True
        content = item.get("content")
        if isinstance(content, list) and any(
            isinstance(part, dict) and part.get("type") in _TOOL_ITEM_TYPES for part in content
        ):
            return True
    return False


def _general_name(name):
    return isinstance(name, str) and name.startswith(_GENERAL_PREFIXES)


def _gateway_tool(name):
    """find_tool/call_tool, with or without a client's server prefix.

    Open WebUI names an MCP tool `<server id>_<tool>`, e.g. `toolhive-ops_call_tool`.
    The prefix is the client's own label, so it is not trusted for anything.
    """
    if not isinstance(name, str):
        return None
    for tool in _GATEWAY_TOOLS:
        if name == tool or name.endswith("_" + tool):
            return tool
    return None


def _general_call(name, arguments):
    """True when one tool call is find_tool, or runs a cluster/repository tool."""
    kind = _gateway_tool(name)
    if kind == "find_tool" or _general_name(name):
        return True
    if kind != "call_tool":
        return False
    try:
        args = json.loads(arguments) if isinstance(arguments, str) else arguments
        return _general_name((args or {}).get("tool_name"))
    except Exception:
        return False


def _only_general_tools(data):
    """True when everything tool-related in the request is a cluster/repository tool.

    Anything this does not recognise (legacy functions, hosted or MCP tool types,
    content-part tool blocks, a result with no visible call) counts as not allowed.
    """
    if data.get("functions") or data.get("function_call"):
        return False
    for tool in data.get("tools") or []:
        if not isinstance(tool, dict) or tool.get("type") != "function":
            return False
        name = (tool.get("function") or {}).get("name") or tool.get("name")
        if not _gateway_tool(name) and not _general_name(name):
            return False
    items = list(data.get("messages") or [])
    if isinstance(data.get("input"), list):
        items += data["input"]
    checked = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        for call in item.get("tool_calls") or []:
            fn = (call or {}).get("function") or {}
            if not _general_call(fn.get("name"), fn.get("arguments")):
                return False
            checked.add(call.get("id"))
        if item.get("type") == "function_call":
            if not _general_call(item.get("name"), item.get("arguments")):
                return False
            checked.add(item.get("call_id"))
        elif item.get("type") in _TOOL_ITEM_TYPES and item.get("type") != "function_call_output":
            return False
        content = item.get("content")
        if isinstance(content, list) and any(
            isinstance(part, dict) and part.get("type") in _TOOL_ITEM_TYPES for part in content
        ):
            return False
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("role") == "function":
            return False
        if item.get("role") == "tool" and item.get("tool_call_id") not in checked:
            return False
        if item.get("type") == "function_call_output" and item.get("call_id") not in checked:
            return False
    return True


class DataScopeGuard(CustomLogger):
    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
        if not isinstance(data, dict) or not _carries_tools(data):
            return data
        alias = data.get("model")
        if _allows_private_model(alias):
            return data
        metadata = getattr(user_api_key_dict, "metadata", None) or {}
        if str(metadata.get("allow_tool_policy_override", "")).lower() == "true":
            return data
        if _only_general_tools(data):
            return data
        key_alias = getattr(user_api_key_dict, "key_alias", None)
        log.warning("data scope guard: refused tools on %r for key %r", alias, key_alias)
        raise HTTPException(
            status_code=400,
            detail={
                "error": (
                    f"These tools are not allowed on '{alias}': its backend is not approved for private data, and only "
                    "cluster, repository, n8n and Anki tools (kubectl, flux, github, n8n, anki) may be used with it. "
                    "Personal data (Metabase, Dawarich, memory) needs local inference or Mistral; a "
                    "conversation that already used those tools cannot continue on a general-only backend."
                )
            },
        )


guard_instance = DataScopeGuard()
log.info("data scope guard: loaded, general-only backends get %s tools only", "/".join(_GENERAL_PREFIXES))
