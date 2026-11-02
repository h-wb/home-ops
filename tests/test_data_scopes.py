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
POLICY = json.loads((ROOT / "kubernetes/components/agent-data-policy/policy.json").read_text().replace("${SECRET_DOMAIN}", "example.com"))


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


AGENTS_APPS = ROOT / "kubernetes/apps/main/agents"


class ScopeFragments(unittest.TestCase):
    """The per-app agent config fragments must match the shared policy.

    The pod base mounts each app's ${APP}-scope ConfigMap at /etc/paseo/scope;
    dotfiles' mise bootstrap merges it into the agent homes. These tests keep
    the fragments and policy.json from drifting apart.
    """

    def fragment(self, app, name):
        text = (AGENTS_APPS / app / "app" / name).read_text().replace("${SECRET_DOMAIN}", "example.com")
        return text if name.endswith(".toml") else json.loads(text)

    def test_fragments_match_policy_scopes(self):
        for app, scope in (("paseo-general", "general"), ("paseo-private", "private")):
            with self.subTest(app=app):
                settings = POLICY["scopes"][scope]
                frag = self.fragment(app, "scope.json")
                providers = frag["agents"]["providers"]
                # Every provider in the policy registry is pinned in the fragment.
                self.assertEqual(set(POLICY["providers"]), set(providers))
                for name, entry in providers.items():
                    self.assertEqual(name in settings["providers"], entry["enabled"], name)
                # Vibe's MCP servers come from the scope's endpoints.
                servers = json.loads(providers["mistral-vibe"]["env"]["VIBE_MCP_SERVERS"])
                names = [s["name"] for s in servers]
                self.assertIn(f"toolhive-{scope}", names)
                for s in servers:
                    self.assertIn(s["url"], (settings["mcp_url"], settings["memory_url"]))
                    self.assertNotIn("secret", json.dumps(s).lower())
                if scope == "general":
                    self.assertIn("memini-general", names)
                    self.assertNotIn("metadataGeneration", frag["agents"])
                else:
                    self.assertEqual(["toolhive-private"], names)
                    self.assertEqual([{"provider": "mistral-vibe"}], frag["agents"]["metadataGeneration"]["providers"])
                    self.assertIn("create_agent", providers["mistral-vibe"]["paseoTools"]["disabledTools"])

    def test_native_client_fragments(self):
        claude = self.fragment("paseo-general", "claude.json")["mcpServers"]
        self.assertEqual("https://mcp-general.example.com/mcp", claude["toolhive-general"]["url"])
        self.assertEqual("${MCP_API_KEY}", claude["toolhive-general"]["headers"]["x-api-key"])
        self.assertIn("memini-general", claude)
        codex = self.fragment("paseo-general", "codex.toml")
        self.assertIn("mcp_servers.toolhive-general", codex)
        self.assertIn('"x-api-key" = "MCP_API_KEY"', codex)
        self.assertEqual({}, self.fragment("paseo-private", "claude.json"))

    def test_scope_grants_are_declared_eligible(self):
        for scope, settings in POLICY["scopes"].items():
            for provider in settings["providers"]:
                self.assertIn(scope, POLICY["providers"][provider]["allowed_data_scopes"], provider)


if __name__ == "__main__":
    unittest.main()
