"""Enforce tool history against the shared general/private backend policy.

Every deployment behind an alias must be eligible for private data before the
request may carry private tool calls or results. Gateway call_tool arguments are
inspected too. General tool prefixes and endpoint eligibility come from the
home-ops policy mounted at /etc/agent-data-policy/policy.json. Missing policy
fails startup; unknown backends get general tools only. Pasted private text and
attachments are outside this protocol guard. The general execution environment's
key additionally permits the native coding tools declared in the shared policy.
MCP calls and history are still checked; this grant is not a policy override.

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
_AGENT_TOOLS = _POLICY["general_agent_tools"]
_AGENT_NAMES = frozenset(_AGENT_TOOLS["names"])
_AGENT_MCP_PREFIXES = tuple(_AGENT_TOOLS["mcp_prefixes"])
_AGENT_HOSTED_TYPES = frozenset(_AGENT_TOOLS["hosted_types"])
_GATEWAY_TOOLS = ("find_tool", "call_tool")
_CALL_TYPES = ("function_call", "custom_tool_call", "tool_use")
_RESULT_TYPES = ("function_call_output", "custom_tool_call_output", "tool_result")
_HOSTED_CALL_TYPES = frozenset(kind + "_call" for kind in _AGENT_HOSTED_TYPES)
_TOOL_ITEM_TYPES = frozenset((*_CALL_TYPES, *_RESULT_TYPES, "mcp_call", "mcp_list_tools")) | _HOSTED_CALL_TYPES


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


def _general_name(name, allow_agent_tools=False):
    if not isinstance(name, str):
        return False
    if name.startswith("functions."):
        name = name.removeprefix("functions.")
    if name.startswith("mcp__"):
        name = name.replace(".", "__")
    return name.startswith(_GENERAL_PREFIXES) or (
        allow_agent_tools and (name in _AGENT_NAMES or name.startswith(_AGENT_MCP_PREFIXES))
    )


def _gateway_tool(name):
    """find_tool/call_tool, with or without a client's server prefix.

    Open WebUI names an MCP tool `<server id>_<tool>`, e.g. `toolhive-ops_call_tool`.
    The prefix is the client's own label, so it is not trusted for anything.
    """
    if not isinstance(name, str):
        return None
    if name.startswith("mcp__"):
        name = name.replace(".", "__")
    for tool in _GATEWAY_TOOLS:
        if name == tool or name.endswith("_" + tool):
            return tool
    return None


def _general_call(name, arguments, allow_agent_tools=False):
    """True when one tool call is find_tool, or runs a cluster/repository tool."""
    kind = _gateway_tool(name)
    if kind == "find_tool":
        return True
    if kind != "call_tool":
        return _general_name(name, allow_agent_tools)
    try:
        args = json.loads(arguments) if isinstance(arguments, str) else arguments
        return _general_name((args or {}).get("tool_name"))
    except Exception:
        return False


def _general_definition(tool, allow_agent_tools):
    if not isinstance(tool, dict):
        return False
    kind = tool.get("type")
    if kind == "namespace":
        # Codex groups native and MCP tools into namespaces. Qualify MCP names
        # so a private server's memory_recall cannot look like a general tool.
        namespace = tool.get("name") or ""
        children = tool.get("tools") or []
        if namespace.startswith("mcp__"):
            children = [{**child, "name": namespace + "__" + child.get("name", "")} for child in children]
        return bool(children) and all(_general_definition(child, allow_agent_tools) for child in children)
    if allow_agent_tools and kind in _AGENT_HOSTED_TYPES:
        return True
    # Anthropic definitions have input_schema and no type. OpenAI supports
    # nested Chat functions, flat Responses functions and native custom tools.
    if kind not in (None, "function", "custom") or (kind is None and "input_schema" not in tool):
        return False
    if kind == "custom" and not allow_agent_tools:
        return False
    name = (tool.get("function") or {}).get("name") or tool.get("name")
    return bool(_gateway_tool(name)) or _general_name(name, allow_agent_tools)


def _only_general_tools(data, allow_agent_tools=False):
    """Check Chat, Responses and Anthropic tools and their complete visible history.

    Unknown definitions, hosted MCP connections and orphan results fail closed.
    Native coding tools require an authenticated key grant, never request metadata.
    """
    if data.get("functions") or data.get("function_call"):
        return False
    for tool in data.get("tools") or []:
        if not _general_definition(tool, allow_agent_tools):
            return False
    choice = data.get("tool_choice")
    if isinstance(choice, dict):
        name = (choice.get("function") or {}).get("name") or choice.get("name")
        if name and not (_gateway_tool(name) or _general_name(name, allow_agent_tools)):
            return False
    items = list(data.get("messages") or [])
    if isinstance(data.get("input"), list):
        items += data["input"]
    checked = set()
    results = []
    for item in items:
        if not isinstance(item, dict):
            continue
        for call in item.get("tool_calls") or []:
            fn = (call or {}).get("function") or {}
            if not _general_call(fn.get("name"), fn.get("arguments"), allow_agent_tools):
                return False
            if call.get("id"):
                checked.add(call["id"])
        content = item.get("content")
        parts = [item] + (content if isinstance(content, list) else [])
        for part in parts:
            if not isinstance(part, dict):
                continue
            kind = part.get("type")
            if kind in _CALL_TYPES:
                args = part.get("input") if kind in ("tool_use", "custom_tool_call") else part.get("arguments")
                if not _general_call(part.get("name"), args, allow_agent_tools):
                    return False
                call_id = part.get("call_id") or part.get("id")
                if call_id:
                    checked.add(call_id)
            elif kind in _RESULT_TYPES:
                results.append(part.get("tool_use_id") if kind == "tool_result" else part.get("call_id"))
            elif kind in _HOSTED_CALL_TYPES:
                if not allow_agent_tools:
                    return False
            elif kind in _TOOL_ITEM_TYPES:
                return False
        if item.get("role") == "function":
            return False
        if item.get("role") == "tool":
            results.append(item.get("tool_call_id"))
    return all(result in checked for result in results)


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
        allow_agent_tools = str(metadata.get("allow_general_agent_tools", "")).lower() == "true"
        if _only_general_tools(data, allow_agent_tools):
            return data
        key_alias = getattr(user_api_key_dict, "key_alias", None)
        log.warning("data scope guard: refused tools on %r for key %r", alias, key_alias)
        raise HTTPException(
            status_code=400,
            detail={
                "error": (
                    f"These tools are not allowed on '{alias}': its backend is not approved for private data, and only "
                    "general tools and explicitly granted native agent tools may be used with it. "
                    "Private tools and memory need local inference or Mistral; a "
                    "conversation that already used those tools cannot continue on a general-only backend."
                )
            },
        )


guard_instance = DataScopeGuard()
log.info("data scope guard: loaded, general-only backends get %s tools only", "/".join(_GENERAL_PREFIXES))
