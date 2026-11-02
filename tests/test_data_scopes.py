"""Run with python3 -m unittest discover -s tests -p 'test_data_scopes.py'."""
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / "kubernetes/components/agent-data-policy/policy.json").read_text())


def load_guard():
    fastapi = types.ModuleType("fastapi")
    class HTTPException(Exception):
        def __init__(self, **kwargs):
            self.status_code = kwargs["status_code"]
    fastapi.HTTPException = HTTPException
    logger = types.ModuleType("litellm.integrations.custom_logger")
    logger.CustomLogger = object
    spec = importlib.util.spec_from_file_location("scope_guard", ROOT / "kubernetes/apps/main/llm/litellm/app/patches/homeops_data_scope_guard.py")
    guard = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"fastapi": fastapi, "litellm.integrations.custom_logger": logger}), patch.object(Path, "read_text", return_value=json.dumps(POLICY)):
        spec.loader.exec_module(guard)
    return guard


class DataScopes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard = load_guard()

    def test_mistral_available_in_both_scopes(self):
        for scope in ("general", "private"):
            self.assertIn("mistral-vibe", POLICY["scopes"][scope]["providers"])

    def test_private_excludes_general_only_providers(self):
        for provider in POLICY["scopes"]["private"]["providers"]:
            self.assertIn("private", POLICY["providers"][provider]["allowed_data_scopes"])
        self.assertNotIn("claude", POLICY["scopes"]["private"]["providers"])
        self.assertNotIn("codex", POLICY["scopes"]["private"]["providers"])

    def test_backend_endpoints(self):
        for model, url, expected in [
            ("mistral/mistral-small-latest", None, True),
            ("mistral/mistral-small-latest", "https://api.mistral.ai/v1", True),
            ("mistral/mistral-small-latest", "https://api.mistral.ai.evil.example/v1", False),
            ("mistral/mistral-small-latest", "https://api.mistral.ai:444/v1", False),
            ("mistral/mistral-small-latest", "https://evil.example/v1", False),
            ("openai/local", "http://embed.llm.svc.cluster.local:8080/v1", True),
            ("openai/local", "http://192.168.27.65:1234/v1", True),
            ("openai/gpt", "https://api.openai.com/v1", False),
            ("unknown/model", None, False),
        ]:
            with self.subTest(model=model, url=url):
                self.assertEqual(expected, self.guard._allows_private_deployment({"litellm_params": {"model": model, "api_base": url}}))

    def test_mixed_alias_fails_closed(self):
        server = types.ModuleType("litellm.proxy.proxy_server")
        server.llm_router = types.SimpleNamespace(get_model_list=lambda **kw: [
            {"litellm_params": {"model": "mistral/small"}},
            {"litellm_params": {"model": "openai/gpt", "api_base": "https://api.openai.com/v1"}},
        ])
        with patch.dict(sys.modules, {"litellm.proxy.proxy_server": server}):
            self.assertFalse(self.guard._allows_private_model("mixed"))

    def test_private_history_cannot_switch_to_general_backend(self):
        data = {"model": "general", "messages": [
            {"role": "assistant", "tool_calls": [{"id": "1", "function": {"name": "call_tool", "arguments": json.dumps({"tool_name": "memini_memory_recall"})}}]},
            {"role": "tool", "tool_call_id": "1", "content": "private memory"},
        ]}
        with patch.object(self.guard, "_allows_private_model", return_value=False):
            with self.assertRaises(Exception) as caught:
                asyncio.run(self.guard.guard_instance.async_pre_call_hook(types.SimpleNamespace(), None, data, None))
        self.assertEqual(400, caught.exception.status_code)

    def test_general_gateway_call_allowed_but_private_nested_call_denied(self):
        self.assertTrue(self.guard._general_call("call_tool", '{"tool_name":"github_list_repos"}'))
        self.assertFalse(self.guard._general_call("call_tool", '{"tool_name":"dawarich_locations"}'))
        self.assertFalse(self.guard._general_call("call_tool", 'invalid-json'))

    def test_orphan_tool_result_denied(self):
        self.assertFalse(self.guard._only_general_tools({"messages": [{"role": "tool", "tool_call_id": "missing", "content": "secret"}]}))


if __name__ == "__main__":
    unittest.main()
