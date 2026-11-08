"""Run with python3 -m unittest discover -s tests -p 'test_data_scopes.py'."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib
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

    def test_claude_native_tools_require_key_grant(self):
        data = {"model": "anthropic/claude-test", "tools": [{"name": "Bash", "input_schema": {"type": "object"}}],
                "messages": [
                    {"role": "assistant", "content": [{"type": "tool_use", "id": "1", "name": "Bash", "input": {"command": "pwd"}}]},
                    {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "1", "content": "/workspace"}]},
                ]}
        with patch.object(self.guard, "_allows_private_model", return_value=False):
            for granted in (False, True):
                with self.subTest(granted=granted):
                    key = types.SimpleNamespace(metadata={"allow_general_agent_tools": str(granted).lower()})
                    if granted:
                        self.assertIs(data, asyncio.run(self.guard.guard_instance.async_pre_call_hook(key, None, data, None)))
                    else:
                        with self.assertRaises(Exception):
                            asyncio.run(self.guard.guard_instance.async_pre_call_hook(key, None, data, None))
            # Request metadata cannot grant the privilege.
            data["metadata"] = {"allow_general_agent_tools": "true"}
            with self.assertRaises(Exception):
                asyncio.run(self.guard.guard_instance.async_pre_call_hook(types.SimpleNamespace(), None, data, None))

    def test_codex_namespace_and_custom_tool_history(self):
        data = {"tools": [{"type": "namespace", "name": "functions", "tools": [
            {"type": "function", "name": "exec_command"}, {"type": "custom", "name": "apply_patch"},
        ]}, {"type": "web_search"}], "input": [
            {"type": "custom_tool_call", "name": "apply_patch", "call_id": "1", "input": "*** Begin Patch"},
            {"type": "custom_tool_call_output", "call_id": "1", "output": "done"},
        ]}
        self.assertTrue(self.guard._only_general_tools(data, True))
        self.assertFalse(self.guard._only_general_tools(data))
        data["input"][1]["call_id"] = "unknown"
        self.assertFalse(self.guard._only_general_tools(data, True))

    def test_general_agent_grant_keeps_private_mcp_blocked_in_each_protocol(self):
        for name in ("mcp__toolhive-general__call_tool", "mcp__toolhive_general__call_tool", "mcp__toolhive_general.call_tool"):
            for nested, allowed in (("github_list_repos", True), ("memini_memory_recall", False), ("dawarich_locations", False)):
                with self.subTest(name=name, nested=nested):
                    args = {"tool_name": nested}
                    histories = [
                        {"messages": [{"role": "assistant", "tool_calls": [{"id": "1", "function": {"name": name, "arguments": json.dumps(args)}}]}]},
                        {"input": [{"type": "function_call", "call_id": "1", "name": name, "arguments": json.dumps(args)}]},
                        {"messages": [{"role": "assistant", "content": [{"type": "tool_use", "id": "1", "name": name, "input": args}]}]},
                    ]
                    for data in histories:
                        self.assertEqual(allowed, self.guard._only_general_tools(data, True))

    def test_scoped_memory_and_unknown_tools(self):
        for name, allowed in (("mcp__memini_general__memory_recall", True),
                              ("mcp__memini_general.memory_recall", True),
                              ("mcp__chrome-devtools__take_snapshot", True),
                              ("mcp__paseo__create_agent", True),
                              ("mcp__memini-private__memory_recall", False),
                              ("metabase_query", False), ("unknown_tool", False)):
            data = {"tools": [{"type": "function", "name": name}]}
            self.assertEqual(allowed, self.guard._only_general_tools(data, True), name)
        for kind in ("tool_result", "custom_tool_call_output", "function_call_output", "mcp_call", "mcp_list_tools"):
            self.assertFalse(self.guard._only_general_tools({"input": [{"type": kind}]}, True), kind)


SCOPES_DIR = ROOT / "kubernetes/components/agent-data-policy/scopes"


class ScopeFragments(unittest.TestCase):
    """The per-scope agent config fragments must match the shared policy.

    They live next to policy.json in components/agent-data-policy/scopes; each
    app's ${APP}-scope ConfigMap references them, the pod base mounts the
    ConfigMap at /etc/paseo/scope, and dotfiles' mise bootstrap merges it into
    the agent homes. These tests keep the fragments and policy.json together.
    """

    def fragment(self, scope, name):
        text = (SCOPES_DIR / scope / name).read_text().replace("${SECRET_DOMAIN}", "example.com")
        return text if name.endswith(".toml") else json.loads(text)

    def test_fragments_match_policy_scopes(self):
        for scope in POLICY["scopes"]:
            with self.subTest(scope=scope):
                settings = POLICY["scopes"][scope]
                frag = self.fragment(scope, "scope.json")
                providers = frag["agents"]["providers"]
                # Pod rolls interrupt running agents; resume them on the next start.
                self.assertIs(True, frag["agents"]["resumeOnStartup"])
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
        claude = self.fragment("general", "claude.json")["mcpServers"]
        self.assertEqual("https://mcp-general.example.com/mcp", claude["toolhive-general"]["url"])
        self.assertEqual("$${MCP_API_KEY}", claude["toolhive-general"]["headers"]["x-api-key"])
        self.assertIn("memini-general", claude)
        codex = self.fragment("general", "codex.toml")
        self.assertIn("mcp_servers.toolhive-general", codex)
        self.assertIn('"x-api-key" = "MCP_API_KEY"', codex)
        self.assertEqual({}, self.fragment("private", "claude.json"))

    def test_scope_grants_are_declared_eligible(self):
        for scope, settings in POLICY["scopes"].items():
            for provider in settings["providers"]:
                self.assertIn(scope, POLICY["providers"][provider]["allowed_data_scopes"], provider)

    def test_vibe_models_and_background_calls_use_gateway(self):
        for scope in POLICY["scopes"]:
            env = self.fragment(scope, "scope.json")["agents"]["providers"]["mistral-vibe"]["env"]
            provider, = json.loads(env["VIBE_PROVIDERS"])
            self.assertEqual("https://litellm.example.com/v1", provider["api_base"])
            self.assertEqual("LITELLM_API_KEY", provider["api_key_env_var"])
            aliases = {model["alias"] for model in json.loads(env["VIBE_MODELS"])}
            self.assertIn(env["VIBE_ACTIVE_MODEL"], aliases)
            self.assertTrue(set(json.loads(env["VIBE_UTILITY_MODELS"]).values()) <= aliases)
            self.assertEqual(["litellm-mistral-*"], json.loads(env["VIBE_ALLOWED_MODELS"]))


class PaseoRendering(unittest.TestCase):
    """Exercise Kustomize and Flux substitution using the repo's pinned tools."""

    @staticmethod
    def run_tool(*args, text=None, env=None):
        result = subprocess.run(args, input=text, env=env, cwd=ROOT,
                                capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise AssertionError(f"{args[0]} failed: {result.stderr}")
        return result.stdout

    @classmethod
    def documents(cls, text):
        return json.loads(cls.run_tool("yq", "eval-all", "-o=json", "-I=0", "[.]", "-", text=text))

    @classmethod
    def substitute(cls, text, variables):
        # Model controller substitution without borrowing credentials from the
        # shell running the tests. Secrets belong in runtime env references.
        env = {key: os.environ[key] for key in ("HOME", "PATH") if key in os.environ}
        return cls.run_tool("flux", "envsubst", text=text, env={**env, **variables})

    @classmethod
    def setUpClass(cls):
        parent = cls.run_tool("kustomize", "build", "kubernetes/apps/main/agents",
                              "--load-restrictor=LoadRestrictionsNone")
        variables = {"CLUSTER": "main", "SECRET_DOMAIN": "example.com"}
        children = cls.documents(cls.substitute(parent, variables))
        cls.rendered = {}
        for child in children:
            if child.get("kind") != "Kustomization" or child["metadata"]["name"] not in ("paseo", "paseo-private"):
                continue
            spec = child["spec"]
            scope = spec["postBuild"]["substitute"]["PASEO_DATA_SCOPE"]
            built = cls.run_tool("kustomize", "build", spec["path"],
                                 "--load-restrictor=LoadRestrictionsNone")
            cls.rendered[scope] = cls.documents(cls.substitute(
                built, {**variables, **spec["postBuild"]["substitute"]}))

    def resource(self, scope, kind, name):
        return next(doc for doc in self.rendered[scope]
                    if doc.get("kind") == kind and doc["metadata"]["name"] == name)

    def test_runtime_auth_references_survive_flux_substitution(self):
        data = self.resource("general", "ConfigMap", "paseo-scope")["data"]
        claude = json.loads(data["claude.json"])["mcpServers"]
        self.assertEqual("https://mcp-general.example.com/mcp", claude["toolhive-general"]["url"])
        self.assertEqual({"x-api-key": "${MCP_API_KEY}"}, claude["toolhive-general"]["headers"])
        self.assertEqual({"Authorization": "Bearer ${MEMINI_API_KEY}"}, claude["memini-general"]["headers"])
        codex = tomllib.loads(data["codex.toml"])["mcp_servers"]
        self.assertEqual({"x-api-key": "MCP_API_KEY"}, codex["toolhive-general"]["env_http_headers"])
        self.assertEqual("MEMINI_API_KEY", codex["memini-general"]["bearer_token_env_var"])

    def test_subscription_credentials_and_routes(self):
        data = self.resource("general", "ConfigMap", "paseo-scope")["data"]
        codex = tomllib.loads(data["codex.toml"])
        provider = codex["model_providers"][codex["model_provider"]]
        self.assertEqual("https://litellm.example.com/v1", provider["base_url"])
        self.assertTrue(provider["requires_openai_auth"])
        self.assertFalse(provider["supports_websockets"])
        self.assertEqual({"x-litellm-api-key": "LITELLM_API_KEY"}, provider["env_http_headers"])
        self.assertNotIn("env_key", provider)
        secret = self.resource("general", "ExternalSecret", "paseo-litellm")["spec"]["target"]["template"]["data"]
        self.assertEqual("x-litellm-api-key: Bearer {{ .LITELLM_API_KEY }}", secret["ANTHROPIC_CUSTOM_HEADERS"])
        for name, controller in (("general", "paseo"), ("private", "paseo-private")):
            values = self.resource(name, "HelmRelease", controller)["spec"]["values"]
            hosts = values["defaultPodOptions"]["hostAliases"][0]["hostnames"]
            self.assertIn("litellm.example.com", hosts)
            runtime = values["controllers"][controller]
            containers = {**runtime["containers"], **runtime["initContainers"]}
            for container in ("tools", "app", "sshd"):
                if name == "general":
                    self.assertEqual("https://litellm.example.com", containers[container]["env"]["ANTHROPIC_BASE_URL"])
                    secrets = [entry["secretRef"]["name"] for entry in containers[container]["envFrom"]]
                    self.assertIn("paseo-litellm", secrets)
                else:
                    self.assertNotIn("ANTHROPIC_BASE_URL", containers[container]["env"])

    def test_all_provisioning_containers_can_read_scope_fragments(self):
        for scope, app in (("general", "paseo"), ("private", "paseo-private")):
            with self.subTest(scope=scope):
                data = self.resource(scope, "ConfigMap", f"{app}-scope")["data"]
                self.assertEqual({"scope.json", "claude.json", "codex.toml"}, set(data))
                values = self.resource(scope, "HelmRelease", app)["spec"]["values"]
                volume = values["persistence"]["scope"]
                self.assertEqual(f"{app}-scope", volume["name"])
                mounts = volume["advancedMounts"][app]
                for container in ("tools", "app", "sshd"):
                    with self.subTest(container=container):
                        paths = {entry["path"]: entry for entry in mounts.get(container, [])}
                        self.assertEqual({f"/etc/paseo/scope/{key}" for key in data}, set(paths))
                        for key in data:
                            entry = paths[f"/etc/paseo/scope/{key}"]
                            self.assertEqual(key, entry["subPath"])
                            self.assertTrue(entry["readOnly"])
                self.assertNotIn("browser", mounts)

    def test_general_has_no_direct_kubernetes_credentials_or_grants(self):
        values = self.resource("general", "HelmRelease", "paseo")["spec"]["values"]
        self.assertIs(False, values["defaultPodOptions"]["automountServiceAccountToken"])
        # A projected token would bypass automountServiceAccountToken: false.
        for volume in values["persistence"].values():
            sources = volume.get("volumeSpec", {}).get("projected", {}).get("sources", [])
            self.assertFalse(any("serviceAccountToken" in source for source in sources))
        scratch = self.documents(self.run_tool(
            "kustomize", "build", "kubernetes/apps/main/agents/paseo/scratch"))
        # Check both Flux inventories: removing only the app's ClusterRoleBindings
        # would leave namespace edit/exec/Secret access through the scratch binding.
        for doc in self.rendered["general"] + scratch:
            if doc.get("kind") in ("RoleBinding", "ClusterRoleBinding"):
                self.assertFalse(any(subject.get("kind") == "ServiceAccount"
                                     and subject.get("name") == "paseo"
                                     and subject.get("namespace") == "agents"
                                     for subject in doc.get("subjects", [])))
        self.assertTrue(any(doc.get("kind") == "ResourceQuota" for doc in scratch))

    def test_general_network_policy_blocks_direct_control_plane_only(self):
        policy = self.resource("general", "CiliumNetworkPolicy", "paseo-toolhive-only")["spec"]
        self.assertEqual({"app.kubernetes.io/name": "paseo"},
                         policy["endpointSelector"]["matchLabels"])
        self.assertEqual([{"toEntities": ["all"]}], policy["egress"])
        denied = {}
        for rule in policy["egressDeny"]:
            ports = {entry["port"] for group in rule["toPorts"]
                     for entry in group["ports"] if entry["protocol"] == "TCP"}
            for entity in rule["toEntities"]:
                denied.setdefault(entity, set()).update(ports)
        self.assertIn("443", denied["kube-apiserver"])
        self.assertTrue({"6443", "7445", "50000"}.issubset(denied["all"]))
        # ToolHive gateway, providers, memory and DNS must not be caught by
        # destination-independent port denies.
        self.assertFalse({"443", "4483", "8080", "53"} & denied["all"])
        self.assertFalse(any(doc.get("kind") == "CiliumNetworkPolicy"
                             for doc in self.rendered["private"]))

    def test_private_retains_only_its_explicit_hermes_token_mount(self):
        values = self.resource("private", "HelmRelease", "paseo-private")["spec"]["values"]
        self.assertIs(False, values["defaultPodOptions"]["automountServiceAccountToken"])
        token = values["persistence"]["kube-api-token"]
        self.assertEqual({"paseo-private"}, set(token["advancedMounts"]))
        self.assertEqual({"app"}, set(token["advancedMounts"]["paseo-private"]))
        self.assertTrue(any("serviceAccountToken" in source
                            for source in token["volumeSpec"]["projected"]["sources"]))


class LiteLLMRendering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        built = PaseoRendering.run_tool("kustomize", "build", "kubernetes/apps/main/llm/litellm/app",
                                       "--load-restrictor=LoadRestrictionsNone")
        cls.docs = PaseoRendering.documents(built)

    def test_subscription_routes_and_key_isolation(self):
        models = {doc["spec"]["modelName"]: doc["spec"] for doc in self.docs if doc.get("kind") == "LiteLLMModel"}
        for alias, upstream in (("anthropic/*", "anthropic/*"), ("gpt-*", "chatgpt/gpt-*"), ("codex-*", "chatgpt/codex-*")):
            self.assertEqual(upstream, models[alias]["params"]["model"])
            self.assertNotIn("apiKeyRef", models[alias]["params"])
            self.assertNotIn("apiKey", models[alias]["params"])
        keys = {doc["metadata"]["name"]: doc["spec"] for doc in self.docs if doc.get("kind") == "LiteLLMVirtualKey"}
        self.assertEqual("true", keys["paseo-general"]["metadata"]["allow_general_agent_tools"])
        for name in ("paseo-general", "paseo-private"):
            key = keys[name]
            self.assertNotIn("allow_tool_policy_override", key.get("metadata", {}))
            for alias in ("anthropic/*", "gpt-*", "codex-*"):
                self.assertEqual(name == "paseo-general", alias in key["models"])
        self.assertNotIn("allow_general_agent_tools", keys["paseo-private"].get("metadata", {}))


if __name__ == "__main__":
    unittest.main()
