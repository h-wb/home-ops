"""Keeps private data away from cloud models: no tool calling on a non-local model.

Tools are how a model reads the house: ToolHive exposes Metabase (health), Dawarich
(location), memory, n8n, GitHub and the cluster. A cloud model may chat, and may
use the cluster and repository tools (CLOUD_TOOL_PREFIXES, what the mcp-ops
gateway serves). Any other tool definition, call or result is refused unless every
backend behind the requested alias is local.

- Local means a private address: the MacBook over WireGuard or an in-cluster
  Service. Anything else, including an alias this hook cannot resolve, counts as
  cloud (fail closed). No list of cloud model names to keep in step.
- Both gateways speak find_tool/call_tool, so the names alone prove nothing: every
  call in the conversation is checked for the tool it actually ran. A private
  tool's result can only arrive together with the call that produced it, and that
  request is refused. find_tool is allowed (it returns tool descriptions, not data).
- A consumer that should be allowed (e.g. a reviewer of public repositories) gets
  `metadata: {allow_cloud_tools: "true"}` on its LiteLLMVirtualKey.

What this cannot see: text an application pastes into the prompt itself (Open
WebUI's attached files and knowledge, or its legacy non-native tool mode). The
gateway only sees messages; it blocks the tool-calling protocol, not copied text.

Loaded through `litellm_settings.callbacks`. It only uses LiteLLM's public callback
interface (`async_pre_call_hook`) and the router's `get_model_list`.
"""

import ipaddress
import json
import logging
import os
from urllib.parse import urlparse

from fastapi import HTTPException
from litellm.integrations.custom_logger import CustomLogger

log = logging.getLogger("LiteLLM Proxy")

_LOCAL_SUFFIXES = (".svc", ".svc.cluster.local", ".cluster.local", ".local", ".internal")
_TOOL_KEYS = ("tools", "functions", "tool_choice", "function_call")
_TOOL_ROLES = ("tool", "function")
_OPS_PREFIXES = tuple(
    p.strip() for p in os.environ.get("CLOUD_TOOL_PREFIXES", "kubectl_,flux_,github_").split(",") if p.strip()
)
_GATEWAY_TOOLS = ("find_tool", "call_tool")
_TOOL_ITEM_TYPES = ("function_call", "function_call_output", "mcp_call", "mcp_list_tools", "tool_result", "tool_use")


def _is_local_base(api_base):
    if not api_base or not isinstance(api_base, str):
        return False
    host = urlparse(api_base).hostname or ""
    if not host:
        return False
    if host == "localhost" or "." not in host:  # bare in-cluster service name
        return True
    try:
        address = ipaddress.ip_address(host)
        return address.is_private or address.is_loopback
    except ValueError:
        return host.endswith(_LOCAL_SUFFIXES)


def _is_local_model(alias):
    """True only when the alias resolves and all of its deployments are local."""
    try:
        from litellm.proxy.proxy_server import llm_router

        deployments = llm_router.get_model_list(model_name=alias) if llm_router else None
        if not deployments:
            return False
        return all(_is_local_base((d.get("litellm_params") or {}).get("api_base")) for d in deployments)
    except Exception:
        log.warning("cloud tool guard: could not classify %r, treating it as cloud", alias, exc_info=True)
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


def _ops_name(name):
    return isinstance(name, str) and name.startswith(_OPS_PREFIXES)


def _ops_call(name, arguments):
    """True when one tool call is find_tool, or runs a cluster/repository tool."""
    if name == "find_tool" or _ops_name(name):
        return True
    if name != "call_tool":
        return False
    try:
        args = json.loads(arguments) if isinstance(arguments, str) else arguments
        return _ops_name((args or {}).get("tool_name"))
    except Exception:
        return False


def _only_ops_tools(data):
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
        if name not in _GATEWAY_TOOLS and not _ops_name(name):
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
            if not _ops_call(fn.get("name"), fn.get("arguments")):
                return False
            checked.add(call.get("id"))
        if item.get("type") == "function_call":
            if not _ops_call(item.get("name"), item.get("arguments")):
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


class CloudToolGuard(CustomLogger):
    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
        if not isinstance(data, dict) or not _carries_tools(data):
            return data
        alias = data.get("model")
        if _is_local_model(alias):
            return data
        metadata = getattr(user_api_key_dict, "metadata", None) or {}
        if str(metadata.get("allow_cloud_tools", "")).lower() == "true":
            return data
        if _only_ops_tools(data):
            return data
        key_alias = getattr(user_api_key_dict, "key_alias", None)
        log.warning("cloud tool guard: refused tools on %r for key %r", alias, key_alias)
        raise HTTPException(
            status_code=400,
            detail={
                "error": (
                    f"These tools are not allowed on '{alias}': it is not a local model, and only "
                    "cluster and repository tools (kubectl, flux, github) may be used with it. "
                    "Personal data (Metabase, Dawarich, memory, n8n) needs a local model; a "
                    "conversation that already used those tools cannot continue on a cloud model."
                )
            },
        )


guard_instance = CloudToolGuard()
log.info("cloud tool guard: loaded, non-local models get %s tools only", "/".join(_OPS_PREFIXES))
