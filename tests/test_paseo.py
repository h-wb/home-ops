"""Rendered Paseo permission boundaries and LiteLLM key grants.

Run with python3 -B -m unittest discover -s tests -p test_paseo.py.
"""
import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
# Vibe's own model, offered without a definition, and its ACP session modes.
VIBE_DEFAULT_MODEL = "mistral-medium-3.5"
VIBE_MODES = {"ask", "accept-edits", "auto-approve"}
# The read-only mode of each provider: Vibe has none, and `ask` waits for a yes on anything but reads.
READ_ONLY_MODE = {"claude": "plan", "opencode": "plan", "mistral-vibe": "ask"}


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

    def test_profiles_name_only_what_the_workshop_can_run(self):
        # An orchestrating agent launches a worker from a profile's provider, model
        # and mode. One the key cannot call only fails at the first prompt, and in
        # private the key is what keeps the work on trusted models.
        ids = {"general": ["orchestrate", "orchestrate-opus", "orchestrate-sol", "plan", "explore", "build", "review"],
               "private": ["plan", "build", "review"]}
        for scope, app in (("general", "paseo"), ("private", "paseo-private")):
            with self.subTest(scope=scope):
                data = self.resource(scope, "ConfigMap", f"{app}-config")["data"]
                paseo, opencode = json.loads(data["paseo.json"]), json.loads(data["opencode.json"])
                key = next(d for d in self.rendered[scope] if d.get("kind") == "LiteLLMVirtualKey")["spec"]
                enabled = {name for name, provider in paseo["agents"]["providers"].items()
                           if provider.get("enabled")}
                profiles = {profile["id"]: profile for profile in paseo["daemon"]["agentProfiles"]}
                self.assertEqual(ids[scope], list(profiles))
                for name, profile in profiles.items():
                    self.assertIn(profile["provider"], enabled, name)
                    self.assertTrue(profile["notes"], name)
                    if profile["provider"] == "claude":
                        self.assertIn("anthropic/*", key["models"], name)
                        continue
                    if profile["provider"] == "mistral-vibe":
                        vibe = paseo["agents"]["providers"]["mistral-vibe"]
                        models = {m["alias"] for m in json.loads(vibe["env"]["VIBE_MODELS"])}
                        self.assertIn(profile["model"], models | {VIBE_DEFAULT_MODEL}, name)
                        self.assertIn(profile["modeId"], VIBE_MODES, name)
                        # Paseo sets thinking through an ACP thought_level option, which Vibe lacks.
                        self.assertNotIn("thinkingOptionId", profile, name)
                        continue
                    self.assertEqual("opencode", profile["provider"], name)
                    gateway, _, model = profile["model"].partition("/")
                    self.assertEqual("litellm", gateway, name)
                    self.assertIn(model, key["models"], name)
                    # An OpenCode mode is one of its agents.
                    self.assertIn(profile["modeId"], opencode["agents"], name)
                    entry = opencode["providers"]["litellm"]["models"][model]
                    # A reasoning variant ("none") is a thinking option too.
                    # The chatgpt/* entries declare no reasoning: such a profile sets no option.
                    effort = entry.get("capabilities", {}).get("reasoning", {}).get("effort", [])
                    options = effort + [v["id"] for v in entry.get("variants", [])]
                    if options or "thinkingOptionId" in profile:
                        self.assertIn(profile.get("thinkingOptionId", options[0]), options, name)
                # Plan, Explore and Review must not edit; Review is a second opinion, so not Build's model.
                for name in {"plan", "explore", "review"} & set(profiles):
                    self.assertEqual(READ_ONLY_MODE[profiles[name]["provider"]], profiles[name]["modeId"], name)
                self.assertNotEqual(profiles["build"]["model"], profiles["review"]["model"])
        data = self.resource("general", "ConfigMap", "paseo-config")["data"]
        profiles = {p["id"]: p for p in json.loads(data["paseo.json"])["daemon"]["agentProfiles"]}
        agents = json.loads(data["opencode.json"])["agents"]
        # The orchestrator starts workers, so it cannot be read-only. Reading on the
        # builder's model saves nothing, as a profile or as OpenCode's own explorer.
        self.assertNotEqual("plan", profiles["orchestrate"]["modeId"])
        self.assertNotEqual(profiles["build"]["model"], profiles["explore"]["model"])
        self.assertNotEqual(agents["build"]["model"], agents["explorer"]["model"].partition("#")[0])
        private = json.loads(self.resource("private", "ConfigMap", "paseo-private-config")["data"]["paseo.json"])
        self.assertEqual({"mistral-vibe"}, {p["provider"] for p in private["daemon"]["agentProfiles"]})
        # No agent in private starts or prompts another one (the assistant is a provider there).
        for provider in ("opencode", "mistral-vibe"):
            self.assertEqual({"disabledTools": ["create_agent", "send_agent_prompt"]},
                             private["agents"]["providers"][provider]["paseoTools"], provider)

    def test_mistral_profiles_run_on_vibe(self):
        # A Mistral plan used through another harness counts as API use; Vibe over ACP
        # keeps the Vibe allowance, and calls Mistral directly with the workshop's key.
        for scope, app, secret, item in (("general", "paseo", "paseo-agents", "paseo-general"),
                                         ("private", "paseo-private", "paseo-private-agents", "paseo-private")):
            with self.subTest(scope=scope):
                data = self.resource(scope, "ConfigMap", f"{app}-config")["data"]
                paseo = json.loads(data["paseo.json"])
                vibe = paseo["agents"]["providers"]["mistral-vibe"]
                # Not a built-in provider: without these Paseo skips the entry.
                self.assertEqual(("acp", ["vibe-acp"], True), (vibe["extends"], vibe["command"], vibe["enabled"]))
                self.assertTrue(vibe["label"])
                profiles = paseo["daemon"]["agentProfiles"]
                self.assertTrue(any(p["provider"] == "mistral-vibe" for p in profiles))
                for profile in profiles:
                    self.assertFalse(profile.get("model", "").startswith("litellm/mistral/"), profile["id"])
                # Vibe's extra models are Mistral API ids, the same the gateway serves.
                key = next(d for d in self.rendered[scope] if d.get("kind") == "LiteLLMVirtualKey")["spec"]
                for model in json.loads(vibe["env"]["VIBE_MODELS"]):
                    self.assertEqual("mistral", model["provider"])
                    self.assertIn(f"mistral/{model['name']}", key["models"])
                # The key comes from the workshop's own item, into the app container only.
                spec = self.resource(scope, "ExternalSecret", secret)["spec"]
                self.assertEqual("{{ .MISTRAL_API_KEY }}", spec["target"]["template"]["data"]["MISTRAL_API_KEY"])
                self.assertIn({"extract": {"key": item}}, spec["dataFrom"])
                runtime = self.resource(scope, "HelmRelease", app)["spec"]["values"]["controllers"][app]
                ref = runtime["containers"]["app"]["env"]["MISTRAL_API_KEY"]["valueFrom"]["secretKeyRef"]
                self.assertEqual({"name": secret, "key": "MISTRAL_API_KEY"}, ref)
                self.assertNotIn("MISTRAL_API_KEY", runtime["initContainers"]["tools"].get("env", {}))

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

    def test_general_mounts_a_fresh_bot_tintin_installation_token(self):
        # The generator's permission map stays narrow and never holds workflows.
        generator = self.resource("general", "GithubAccessToken", "bot-tintin")["spec"]
        permissions = generator["permissions"]
        self.assertNotIn("workflows", permissions)
        self.assertLessEqual(set(permissions.values()), {"read", "write"})
        self.assertEqual({"contents": "write", "pull_requests": "write", "issues": "write"},
                         {key: permissions[key] for key in ("contents", "pull_requests", "issues")})
        # Installation tokens live 1h: the ExternalSecret must refresh under that.
        token = self.resource("general", "ExternalSecret", "bot-tintin-token")["spec"]
        self.assertEqual("bot-tintin-token", token["target"]["name"])
        seconds = {"s": 1, "m": 60, "h": 3600}[token["refreshInterval"][-1]]
        self.assertLess(int(token["refreshInterval"][:-1]) * seconds, 3600)
        # The token is rendered as gh's hosts.yml, never as a bare value.
        hosts = token["target"]["template"]["data"]
        self.assertEqual(["hosts.yml"], list(hosts))
        self.assertIn("github.com:", hosts["hosts.yml"])
        self.assertIn("oauth_token: {{ .token }}", hosts["hosts.yml"])
        # The general pod mounts that Secret as a directory (no subPath, so it
        # refreshes) and points GH_CONFIG_DIR at it. GH_TOKEN must be gone: gh
        # prefers it over hosts.yml, so the bot would never be used.
        values = self.resource("general", "HelmRelease", "paseo")["spec"]["values"]
        volume = values["persistence"]["bot-tintin-token"]
        secret = volume["volumeSpec"]["secret"]
        self.assertEqual("bot-tintin-token", secret["secretName"])
        self.assertIs(True, secret["optional"])
        mounts = volume["advancedMounts"]["paseo"]["app"]
        self.assertEqual(1, len(mounts))
        self.assertNotIn("subPath", mounts[0])
        self.assertTrue(mounts[0]["readOnly"])
        controller = values["controllers"]["paseo"]
        env = controller["containers"]["app"]["env"]
        self.assertEqual(mounts[0]["path"], env["GH_CONFIG_DIR"])
        for container in [*controller.get("initContainers", {}).values(),
                          *controller["containers"].values()]:
            self.assertNotIn("GH_TOKEN", container.get("env", {}))
            self.assertNotIn("GITHUB_TOKEN", container.get("env", {}))
            # paseo-agents still holds the personal GH_TOKEN for rollback.
            self.assertNotIn("paseo-agents", [ref.get("secretRef", {}).get("name")
                                              for ref in container.get("envFrom", [])])
        # Reloader must not recreate the pod each time a new token is minted.
        annotations = values["controllers"]["paseo"]["annotations"]
        self.assertEqual("true", annotations["reloader.stakater.com/auto"])
        self.assertIn("bot-tintin-token", annotations[
            "secrets.exclude.reloader.stakater.com/reload"].split(","))
        # The private scope renders no bot-tintin resource and no mount of it.
        self.assertFalse(any(doc["metadata"]["name"].startswith("bot-tintin")
                             for doc in self.rendered["private"]))
        private = self.resource("private", "HelmRelease", "paseo-private")["spec"]["values"]
        self.assertNotIn("bot-tintin-token", private["persistence"])
        self.assertNotIn("GH_CONFIG_DIR",
                         private["controllers"]["paseo-private"]["containers"]["app"].get("env", {}))

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
