"""Rendered Paseo permission boundaries and LiteLLM key grants.

Run with python3 -B -m unittest discover -s tests -p test_paseo.py.
"""
import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


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
        parent = cls.run_tool("kustomize", "build", "kubernetes/apps/main/llm",
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

    def test_config_mounted_and_env_references_survive_substitution(self):
        for scope, app in (("general", "paseo"), ("private", "paseo-private")):
            with self.subTest(scope=scope):
                data = self.resource(scope, "ConfigMap", f"{app}-config")["data"]
                # MCP servers are dotfiles' (conf.d/ai), rendered at pod start.
                self.assertEqual({"paseo.json", "opencode.json"}, set(data))
                opencode = json.loads(data["opencode.json"])
                self.assertNotIn("mcp", opencode)
                self.assertNotIn("plugins", opencode)
                litellm = opencode["providers"]["litellm"]["settings"]
                self.assertEqual("http://litellm.llm.svc.cluster.local:4000/v1", litellm["baseURL"])
                self.assertEqual("{env:LITELLM_API_KEY}", litellm["apiKey"])
                values = self.resource(scope, "HelmRelease", app)["spec"]["values"]
                mounts = values["persistence"]["config"]["advancedMounts"][app]
                runtime = values["controllers"][app]
                containers = {**runtime["containers"], **runtime["initContainers"]}
                for container in ("tools", "app"):
                    self.assertEqual([{"path": "/etc/paseo/config", "readOnly": True}], mounts[container])
                    self.assertEqual("/etc/paseo/config/opencode.json",
                                     containers[container]["env"]["OPENCODE_CONFIG"])
                self.assertNotIn("browser", mounts)

    def test_pods_reach_toolhive_in_cluster_without_a_key(self):
        # llm/toolhive's NetworkPolicy admits each scope's pod to its gateway;
        # a key in the pod could be used from anywhere on the LAN.
        for scope, app in (("general", "paseo"), ("private", "paseo-private")):
            with self.subTest(scope=scope):
                values = self.resource(scope, "HelmRelease", app)["spec"]["values"]
                runtime = values["controllers"][app]
                for name, container in {**runtime["containers"], **runtime["initContainers"]}.items():
                    self.assertNotIn("MCP_API_KEY", container.get("env", {}), name)
                secret = self.resource(scope, "ExternalSecret", app)["spec"]["target"]["template"]["data"]
                self.assertNotIn("MCP_API_KEY", secret)
                self.assertNotIn("hostAliases", values["defaultPodOptions"])

    def test_each_pod_holds_its_own_scopes_memini_key(self):
        # Bitwarden `memini` fields are <SCOPE>_<HOLDER>; this holder is `paseo`.
        for scope, app, secret in (("general", "paseo", "paseo-agents"),
                                   ("private", "paseo-private", "paseo-private-agents")):
            with self.subTest(scope=scope):
                spec = self.resource(scope, "ExternalSecret", secret)["spec"]
                self.assertEqual("{{ .%s_PASEO }}" % scope.upper(),
                                 spec["target"]["template"]["data"]["MEMINI_API_KEY"])
                self.assertIn({"extract": {"key": "memini"}}, spec["dataFrom"])
                runtime = self.resource(scope, "HelmRelease", app)["spec"]["values"]["controllers"][app]
                ref = runtime["containers"]["app"]["env"]["MEMINI_API_KEY"]["valueFrom"]["secretKeyRef"]
                self.assertEqual(secret, ref["name"])
                self.assertEqual("true", runtime["annotations"]["reloader.stakater.com/auto"])

    def test_only_general_routes_claude_through_litellm(self):
        secret = self.resource("general", "ExternalSecret", "paseo-agents")["spec"]["target"]["template"]["data"]
        self.assertNotIn("ANTHROPIC_CUSTOM_HEADERS", secret)
        app = self.resource("general", "HelmRelease", "paseo")["spec"]["values"]["controllers"]["paseo"]
        self.assertEqual({"value": "x-litellm-api-key: Bearer $(LITELLM_API_KEY)", "dependsOn": "LITELLM_API_KEY"},
                         app["containers"]["app"]["env"]["ANTHROPIC_CUSTOM_HEADERS"])
        with self.assertRaises(StopIteration):
            self.resource("private", "ExternalSecret", "paseo-agents")
        for scope, app in (("general", "paseo"), ("private", "paseo-private")):
            runtime = self.resource(scope, "HelmRelease", app)["spec"]["values"]["controllers"][app]
            for name, container in {**runtime["containers"], **runtime["initContainers"]}.items():
                if name == "browser":
                    continue
                env = container.get("env", {})
                self.assertNotIn("ANTHROPIC_API_KEY", env)
                self.assertEqual(scope == "general", "ANTHROPIC_BASE_URL" in env, (scope, name))
                # The virtual key binds the operator's Secret directly, in the
                # pods' own namespace (the CR sits beside them).
                litellm = env["LITELLM_API_KEY"]["valueFrom"]["secretKeyRef"]
                self.assertEqual("api-key", litellm["key"])
                self.assertEqual(f"litellm-paseo-{scope}", litellm["name"])

    def test_opencode_reaches_models_through_the_gateway_only(self):
        for scope, app in (("general", "paseo"), ("private", "paseo-private")):
            with self.subTest(scope=scope):
                config = json.loads(self.resource(scope, "ConfigMap", f"{app}-config")["data"]["opencode.json"])
                self.assertEqual(["litellm"], list(config["providers"]))
                key = next(d for d in self.rendered[scope] if d.get("kind") == "LiteLLMVirtualKey")["spec"]
                # Offering a model the key cannot call only fails at the first prompt.
                self.assertFalse(set(config["providers"]["litellm"]["models"]) - set(key["models"]))
                secret = self.resource(scope, "ExternalSecret", app)["spec"]["target"]["template"]["data"]
                self.assertNotIn("MISTRAL_API_KEY", secret)
        # OpenCode's own free hosted models need no key, so private names the gateway alone.
        private = json.loads(self.resource("private", "ConfigMap", "paseo-private-config")["data"]["opencode.json"])
        self.assertEqual(["litellm"], private["enabled_providers"])

    def test_general_has_no_direct_kubernetes_credentials_or_grants(self):
        values = self.resource("general", "HelmRelease", "paseo")["spec"]["values"]
        self.assertIs(False, values["defaultPodOptions"]["automountServiceAccountToken"])
        # A projected token would bypass automountServiceAccountToken: false.
        for volume in values["persistence"].values():
            sources = volume.get("volumeSpec", {}).get("projected", {}).get("sources", [])
            self.assertFalse(any("serviceAccountToken" in source for source in sources))
        for doc in self.rendered["general"]:
            if doc.get("kind") in ("RoleBinding", "ClusterRoleBinding"):
                self.assertFalse(any(subject.get("kind") == "ServiceAccount"
                                     and subject.get("name") == "paseo"
                                     for subject in doc.get("subjects", [])))

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

    def test_virtual_keys_live_beside_the_pods_with_scope_grants(self):
        keys = {}
        for scope in ("general", "private"):
            for doc in self.rendered[scope]:
                if doc.get("kind") == "LiteLLMVirtualKey":
                    keys[scope] = doc["spec"]
        cloud = lambda key: [m for m in key["models"] if m.startswith(("anthropic/", "chatgpt/", "gpt-", "codex-"))]
        self.assertEqual("llm", keys["general"]["proxyNamespace"])
        self.assertIn("anthropic/*", keys["general"]["models"])
        self.assertEqual([], cloud(keys["private"]))
        for scope in ("general", "private"):
            self.assertEqual(f"litellm-paseo-{scope}", keys[scope]["secretName"])

    def test_private_retains_only_its_explicit_hermes_token_mount(self):
        values = self.resource("private", "HelmRelease", "paseo-private")["spec"]["values"]
        self.assertIs(False, values["defaultPodOptions"]["automountServiceAccountToken"])
        token = values["persistence"]["kube-api-token"]
        self.assertEqual({"paseo-private"}, set(token["advancedMounts"]))
        self.assertEqual({"app"}, set(token["advancedMounts"]["paseo-private"]))
        self.assertTrue(any("serviceAccountToken" in source
                            for source in token["volumeSpec"]["projected"]["sources"]))

    def test_tools_init_container_provisions_with_native_mise_bootstrap(self):
        for scope, app in (("general", "paseo"), ("private", "paseo-private")):
            with self.subTest(scope=scope):
                self.assertFalse(any(doc.get("kind") == "ConfigMap"
                                     and doc["metadata"]["name"] == f"{app}-provision"
                                     for doc in self.rendered[scope]))
                values = self.resource(scope, "HelmRelease", app)["spec"]["values"]
                runtime = values["controllers"][app]
                tools = runtime["initContainers"]["tools"]
                # No script: the app's own image, mise from an image volume.
                self.assertEqual(runtime["containers"]["app"]["image"], tools["image"])
                self.assertEqual(["mise"], tools["command"])
                args = tools["args"]
                self.assertEqual("bootstrap", args[0])
                for flag in ("--from", "--from-dir", "--config-dir",
                             "--yes", "--force-dotfiles", "--skip-dirty", "--locked"):
                    self.assertIn(flag, args)
                self.assertNotIn("--update", args)
                self.assertIn("https://github.com/h-wb/dotfiles.git", args)
                self.assertEqual("/home/paseo/.dotfiles", args[args.index("--from-dir") + 1])
                self.assertEqual(".", args[args.index("--config-dir") + 1])
                self.assertFalse(any(k.startswith("MISE_") for k in tools["env"]))
                self.assertTrue(tools["env"]["PATH"].startswith("/opt/mise/usr/local/bin:"))
                # git must trust the root-owned emptyDir before dotfiles renders anything.
                self.assertEqual({"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "safe.directory",
                                  "GIT_CONFIG_VALUE_0": "/home/paseo/.dotfiles"},
                                 {k: tools["env"][k] for k in ("GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0")})
                self.assertEqual("safe.directory", runtime["containers"]["app"]["env"]["GIT_CONFIG_KEY_0"])
                persistence = values["persistence"]
                # A fresh clone every start, read-only for the agents.
                dotfiles = persistence["home-dotfiles"]
                self.assertEqual("emptyDir", dotfiles["type"])
                self.assertEqual([{"path": "/home/paseo/.dotfiles"}], dotfiles["advancedMounts"][app]["tools"])
                self.assertEqual([{"path": "/home/paseo/.dotfiles", "readOnly": True}],
                                 dotfiles["advancedMounts"][app]["app"])
                # Shims link to the mise binary, so it sits at one path in both.
                mise = persistence["mise"]
                self.assertEqual("image", mise["type"])
                self.assertEqual("ghcr.io/jdx/mise", mise["image"]["repository"])
                for container in ("tools", "app"):
                    self.assertEqual([{"path": "/opt/mise", "readOnly": True}],
                                     mise["advancedMounts"][app][container])
                self.assertNotIn("provision", values["persistence"])
                for container in ("tools", "app"):
                    mounts = values["persistence"]["config"]["advancedMounts"][app][container]
                    self.assertEqual([{"path": "/etc/paseo/config", "readOnly": True}], mounts)
                self.assertEqual(scope == "private", args[-1] == "--skip=repos,task")


class LiteLLMRendering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        built = PaseoRendering.run_tool("kustomize", "build", "kubernetes/apps/main/llm/litellm/app",
                                       "--load-restrictor=LoadRestrictionsNone")
        cls.docs = PaseoRendering.documents(built)

    def test_cloud_models_granted_to_general_only(self):
        models = {doc["spec"]["modelName"]: doc["spec"] for doc in self.docs if doc.get("kind") == "LiteLLMModel"}
        # Subscription pass-through: the gateway must hold no Anthropic credential.
        self.assertEqual("anthropic/*", models["anthropic/*"]["params"]["model"])
        self.assertFalse({"apiKey", "apiKeyRef"} & set(models["anthropic/*"]["params"]))
        # The paseo virtual keys (whose CRs sit beside the pods since the
        # jory-shape move) are asserted in PaseoRendering below.


if __name__ == "__main__":
    unittest.main()
