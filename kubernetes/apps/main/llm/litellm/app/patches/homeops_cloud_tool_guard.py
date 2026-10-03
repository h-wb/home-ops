"""Keeps private data away from cloud models: no tool calling on a non-local model.

Tools are how a model reads the house: ToolHive exposes Metabase (health), Dawarich
(location), n8n, GitHub and the cluster. A cloud model may be used for plain chat,
but a request that carries tool definitions or tool results is refused unless every
backend behind the requested alias is local.

- Local means a private address: the MacBook over WireGuard or an in-cluster
  Service. Anything else, including an alias this hook cannot resolve, counts as
  cloud (fail closed). No list of cloud model names to keep in step.
- A consumer that should be allowed (e.g. a reviewer of public repositories) gets
  `metadata: {allow_cloud_tools: "true"}` on its LiteLLMVirtualKey.

What this cannot see: text an application pastes into the prompt itself (Open
WebUI's attached files and knowledge, or its legacy non-native tool mode). The
gateway only sees messages; it blocks the tool-calling protocol, not copied text.

Loaded through `litellm_settings.callbacks`. It only uses LiteLLM's public callback
interface (`async_pre_call_hook`) and the router's `get_model_list`.
"""

import ipaddress
import logging
from urllib.parse import urlparse

from fastapi import HTTPException
from litellm.integrations.custom_logger import CustomLogger

log = logging.getLogger("LiteLLM Proxy")

_LOCAL_SUFFIXES = (".svc", ".svc.cluster.local", ".cluster.local", ".local", ".internal")
_TOOL_KEYS = ("tools", "functions", "tool_choice", "function_call")
_TOOL_ROLES = ("tool", "function")
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
        key_alias = getattr(user_api_key_dict, "key_alias", None)
        log.warning("cloud tool guard: refused tools on %r for key %r", alias, key_alias)
        raise HTTPException(
            status_code=400,
            detail={
                "error": (
                    f"Tools are not allowed on '{alias}': it is not a local model, and tool results "
                    "(Metabase, Dawarich, n8n, the cluster) must not leave the house. Use a local "
                    "model for anything that needs tools."
                )
            },
        )


guard_instance = CloudToolGuard()
log.info("cloud tool guard: loaded, tools are refused on non-local models")
