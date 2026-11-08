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

    def test_config_mounted_and_env_references_survive_substitution(self):
        for scope, app in (("general", "paseo"), ("private", "paseo-private")):
            with self.subTest(scope=scope):
                data = self.resource(scope, "ConfigMap", f"{app}-config")["data"]
                self.assertEqual({"paseo.json", "claude.json", "opencode.json"}, set(data))
                opencode = json.loads(data["opencode.json"])
                litellm = opencode["provider"]["litellm"]["options"]
                self.assertEqual("https://litellm.example.com/v1", litellm["baseURL"])
                self.assertEqual("{env:LITELLM_API_KEY}", litellm["apiKey"])
                values = self.resource(scope, "HelmRelease", app)["spec"]["values"]
                mounts = values["persistence"]["config"]["advancedMounts"][app]
                runtime = values["controllers"][app]
                containers = {**runtime["containers"], **runtime["initContainers"]}
                for container in ("tools", "app", "sshd"):
                    self.assertEqual([{"path": "/etc/paseo/config", "readOnly": True}], mounts[container])
                    self.assertEqual("/etc/paseo/config/opencode.json",
                                     containers[container]["env"]["OPENCODE_CONFIG"])
                self.assertNotIn("browser", mounts)
        claude = json.loads(self.resource("general", "ConfigMap", "paseo-config")["data"]["claude.json"])
        self.assertEqual({"x-api-key": "${MCP_API_KEY}"}, claude["mcpServers"]["toolhive-general"]["headers"])

    def test_only_general_routes_claude_through_litellm(self):
        secret = self.resource("general", "ExternalSecret", "paseo-litellm")["spec"]["target"]["template"]["data"]
        self.assertEqual("x-litellm-api-key: Bearer {{ .LITELLM_API_KEY }}", secret["ANTHROPIC_CUSTOM_HEADERS"])
        for scope, app in (("general", "paseo"), ("private", "paseo-private")):
            runtime = self.resource(scope, "HelmRelease", app)["spec"]["values"]["controllers"][app]
            for name, container in {**runtime["containers"], **runtime["initContainers"]}.items():
                if name == "browser":
                    continue
                env = container.get("env", {})
                self.assertNotIn("ANTHROPIC_API_KEY", env)
                self.assertEqual(scope == "general", "ANTHROPIC_BASE_URL" in env, (scope, name))

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

    def test_cloud_models_granted_to_general_only(self):
        models = {doc["spec"]["modelName"]: doc["spec"] for doc in self.docs if doc.get("kind") == "LiteLLMModel"}
        # Subscription pass-through: the gateway must hold no Anthropic credential.
        self.assertEqual("anthropic/*", models["anthropic/*"]["params"]["model"])
        self.assertFalse({"apiKey", "apiKeyRef"} & set(models["anthropic/*"]["params"]))
        keys = {doc["metadata"]["name"]: doc["spec"] for doc in self.docs if doc.get("kind") == "LiteLLMVirtualKey"}
        cloud = lambda key: [m for m in key["models"] if m.startswith(("anthropic/", "chatgpt/"))]
        self.assertIn("anthropic/*", keys["paseo-general"]["models"])
        self.assertEqual([], cloud(keys["paseo-private"]))


if __name__ == "__main__":
    unittest.main()
