"""ToolHive gateway scopes: who may reach mcp-general and mcp-private, in-cluster
and through Envoy.

Run with python3 -B -m unittest discover -s tests -p test_toolhive.py.
"""
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
CONFIG = "kubernetes/apps/main/llm/toolhive/config"
ENVOY = {"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "network"}},
         "podSelector": {"matchLabels": {"app.kubernetes.io/managed-by": "envoy-gateway"}}}
PROMETHEUS = [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "observability"}},
               "podSelector": {"matchLabels": {"app.kubernetes.io/name": "prometheus"}}}]


def pods(**labels):
    return {"podSelector": {"matchLabels": labels}}


def yaml_of(path):
    return json.loads(subprocess.run(["yq", "-o=json", "-I=0", ".", str(path)], capture_output=True,
                                     text=True, timeout=60, check=True).stdout)


def yaml_text(text):
    return json.loads(subprocess.run(["yq", "-o=json", "-I=0", "."], input=text, capture_output=True,
                                     text=True, timeout=60, check=True).stdout)


class ToolHiveScopes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        built = subprocess.run(["kustomize", "build", CONFIG], cwd=ROOT, capture_output=True,
                               text=True, timeout=60, check=True).stdout
        cls.docs = json.loads(subprocess.run(["yq", "eval-all", "-o=json", "-I=0", "[.]", "-"],
                                             input=built, capture_output=True, text=True,
                                             timeout=60, check=True).stdout)

    def resource(self, kind, name):
        return next(d for d in self.docs if d["kind"] == kind and d["metadata"]["name"] == name)

    def test_each_gateway_admits_only_its_scope(self):
        expected = {
            "mcp-private": [ENVOY, pods(**{"app.kubernetes.io/name": "paseo-private"})],
            # In-cluster only: no Envoy route, the assistant alone.
            "mcp-assistant": [pods(**{"app.kubernetes.io/name": "hermes-private", "assistant.scope": "private"})],
            "mcp-general": [ENVOY, pods(**{"app.kubernetes.io/name": "paseo"})],
        }
        for gateway, clients in expected.items():
            with self.subTest(gateway=gateway):
                spec = self.resource("NetworkPolicy", gateway)["spec"]
                self.assertEqual({"app.kubernetes.io/instance": gateway}, spec["podSelector"]["matchLabels"])
                self.assertEqual([
                    {"from": clients, "ports": [{"port": 4483, "protocol": "TCP"}]},
                    {"from": PROMETHEUS, "ports": [{"port": 9464, "protocol": "TCP"}]},
                ], spec["ingress"])

    def test_the_assistant_sees_real_tool_names(self):
        # "Writes ask" is decided per tool name; the optimizer would leave only find_tool/call_tool.
        config = self.resource("VirtualMCPServer", "mcp-assistant")["spec"]["config"]
        self.assertNotIn("optimizer", config)
        hermes = (ROOT / "kubernetes/apps/main/llm/hermes/app/config.yaml").read_text()
        self.assertIn("url: http://vmcp-mcp-assistant.llm.svc.cluster.local:4483/mcp\n", hermes)
        self.assertIn("    trust: untrusted\n", hermes)

    def test_tool_servers_answer_toolhive_only(self):
        # Otherwise any pod in the cluster reaches a tool server around the gateways.
        spec = self.resource("NetworkPolicy", "tool-servers")["spec"]
        self.assertEqual({"toolhive": "true"}, spec["podSelector"]["matchLabels"])
        self.assertEqual([{"key": "app.kubernetes.io/name", "operator": "NotIn", "values": ["virtualmcpserver"]}],
                         spec["podSelector"]["matchExpressions"])
        self.assertEqual([{"from": [pods(toolhive="true")]}], spec["ingress"])

    def test_general_gateway_never_lists_private_data(self):
        # Cloud models sit behind general; private's gateway serves everything.
        private = {"vault-ro", "vault-inbox", "personal-tasks", "dawarich", "dawarich-ops", "metabase", "homeassistant",
                   "ticktick"}
        aggregation = self.resource("VirtualMCPServer", "mcp-general")["spec"]["config"]["aggregation"]
        self.assertEqual("deny", aggregation["defaultToolVisibility"])
        self.assertFalse({t["workload"] for t in aggregation["tools"]} & private)
        # TickTick is listed under its entry's name, with a token from Bitwarden.
        server = ROOT / "kubernetes/apps/main/llm/toolhive/mcp-servers/ticktick"
        entry = (server / "mcpserverentry.yaml").read_text()
        self.assertIn("\n  name: ticktick\n", entry)
        self.assertIn("\n  remoteUrl: https://mcp.ticktick.com\n", entry)
        self.assertIn('authorization: "Bearer {{ .TICKTICK_API_TOKEN }}"', (server / "externalsecret.yaml").read_text())
        self.assertIn("mcp-servers/ticktick\n", (ROOT / "kubernetes/apps/main/llm/toolhive/ks.yaml").read_text())

    def test_dawarich_ops_entry_reuses_the_dawarich_header(self):
        # One user API key: the ops entry mounts the secret mcp-dawarich owns.
        entry = yaml_of(ROOT / "kubernetes/apps/main/llm/toolhive/mcp-servers/dawarich-ops/mcpserverentry.yaml")["spec"]
        self.assertEqual("http://dawarich-ops.default.svc.cluster.local:3100/mcp", entry["remoteUrl"])
        self.assertEqual([{"headerName": "Authorization",
                           "valueSecretRef": {"name": "toolhive-dawarich", "key": "authorization"}}],
                         entry["headerForward"]["addHeadersFromSecret"])
        self.assertEqual({"name": "mcp-tools"}, entry["groupRef"])
        server = ROOT / "kubernetes/apps/main/llm/toolhive/mcp-servers/dawarich-ops"
        self.assertFalse((server / "externalsecret.yaml").exists())
        ks = json.loads(subprocess.run(["yq", "eval-all", "-o=json", "-I=0", "[.]",
                                        str(ROOT / "kubernetes/apps/main/llm/toolhive/ks.yaml")],
                                       capture_output=True, text=True, timeout=60, check=True).stdout)
        spec = next(d for d in ks if d["metadata"]["name"] == "mcp-dawarich-ops")["spec"]
        self.assertEqual("./kubernetes/apps/main/llm/toolhive/mcp-servers/dawarich-ops", spec["path"])
        self.assertIn({"name": "dawarich-ops", "namespace": "default"}, spec["dependsOn"])
        self.assertIn({"name": "mcp-dawarich", "namespace": "llm"}, spec["dependsOn"])

    def test_dawarich_ops_admits_only_the_gateways_and_the_prefect_worker(self):
        # It holds the user's API key and writes: nothing else may reach its port.
        built = subprocess.run(["kustomize", "build", "kubernetes/apps/main/default/dawarich/ops"], cwd=ROOT,
                               capture_output=True, text=True, timeout=60, check=True).stdout
        docs = json.loads(subprocess.run(["yq", "eval-all", "-o=json", "-I=0", "[.]", "-"], input=built,
                                         capture_output=True, text=True, timeout=60, check=True).stdout)
        policy = next(d for d in docs if d["kind"] == "NetworkPolicy")["spec"]
        self.assertEqual({"app.kubernetes.io/name": "dawarich-ops", "app.kubernetes.io/instance": "dawarich-ops",
                          "app.kubernetes.io/controller": "dawarich-ops"}, policy["podSelector"]["matchLabels"])
        self.assertEqual(["Ingress"], policy["policyTypes"])
        gateways = {"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "llm"}},
                    "podSelector": {"matchExpressions": [{"key": "app.kubernetes.io/instance", "operator": "In",
                                                          "values": ["mcp-private", "mcp-assistant",
                                                                     "mcp-general"]}]}}
        worker = {"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "automation"}},
                  "podSelector": {"matchLabels": {"app.kubernetes.io/name": "prefect",
                                                  "app.kubernetes.io/controller": "worker"}}}
        self.assertEqual([{"from": [gateways, worker], "ports": [{"port": 3100, "protocol": "TCP"}]}],
                         policy["ingress"])
        # The policy selects the pod the HelmRelease makes, and the gateway's URL is its Service.
        release = next(d for d in docs if d["kind"] == "HelmRelease")
        self.assertEqual("dawarich-ops", release["metadata"]["name"])
        values = release["spec"]["values"]
        self.assertEqual(["dawarich-ops"], list(values["controllers"]))
        self.assertEqual({"controller": "dawarich-ops", "ports": {"http": {"port": 3100}}}, values["service"]["app"])
        self.assertNotIn("route", values)

    def test_envoy_takes_one_key_per_external_client_and_scope(self):
        # Bitwarden fields are <SCOPE>_<HOLDER>; the Envoy client is the holder.
        routes = {"mcp-private-api-key": ("mcp-private-api-keys", "PRIVATE_WORKSTATION"),
                  "mcp-general-api-key": ("mcp-general-api-keys", "GENERAL_WORKSTATION")}
        for policy, (secret, field) in routes.items():
            with self.subTest(policy=policy):
                refs = self.resource("SecurityPolicy", policy)["spec"]["apiKeyAuth"]["credentialRefs"]
                self.assertEqual([secret], [r["name"] for r in refs])
                spec = self.resource("ExternalSecret", secret)["spec"]
                self.assertEqual({"workstation": "{{ .%s }}" % field}, spec["target"]["template"]["data"])
                self.assertEqual([{"extract": {"key": "toolhive"}}], spec["dataFrom"])

    def test_gateways_share_sessions_and_expose_metrics_off_the_mcp_port(self):
        telemetry = self.resource("MCPTelemetryConfig", "prometheus")["spec"]["prometheus"]
        self.assertEqual({"enabled": True, "metricsOnTransportPort": False}, telemetry)
        prefixes = set()
        for gateway in ("mcp-private", "mcp-assistant", "mcp-general"):
            spec = self.resource("VirtualMCPServer", gateway)["spec"]
            self.assertEqual({"name": "prometheus"}, spec["telemetryConfigRef"])
            self.assertEqual({"name": "toolhive-config-redis", "key": "password"},
                             spec["sessionStorage"]["passwordRef"])
            prefixes.add(spec["sessionStorage"]["keyPrefix"])
        self.assertEqual(3, len(prefixes))
        redis = self.resource("ExternalSecret", "toolhive-config-redis")["spec"]
        self.assertEqual({"password": "{{ .REDIS_PASSWORD }}"}, redis["target"]["template"]["data"])
        self.assertEqual([{"extract": {"key": "toolhive"}}], redis["dataFrom"])
        # Nothing is generated in-cluster: every value is in Bitwarden.
        self.assertFalse([d for d in self.docs if d["kind"] == "Password"])
        endpoint = self.resource("PodMonitor", "toolhive-vmcp")["spec"]["podMetricsEndpoints"][0]
        self.assertEqual("$1:9464", endpoint["relabelings"][0]["replacement"])


class MeminiStaysOutOfToolHive(unittest.TestCase):
    def test_no_gateway_carries_memini(self):
        # Clients connect to their scope's memini directly (like jory's): the
        # gateways' optimizer would hide memory tools behind find_tool, and memini
        # would see ToolHive instead of the client.
        ks = (ROOT / "kubernetes/apps/main/llm/toolhive/ks.yaml").read_text()
        self.assertNotIn("mcp-servers/memini", ks)
        self.assertFalse((ROOT / "kubernetes/apps/main/llm/toolhive/mcp-servers/memini").exists())
        keys = (ROOT / "kubernetes/apps/main/llm/memini-private/app/externalsecret.yaml").read_text()
        self.assertNotIn("PRIVATE_TOOLHIVE", keys)


class HermesIsPrivateOnly(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        built = subprocess.run(["kustomize", "build", "kubernetes/apps/main/llm/hermes/app"], cwd=ROOT,
                               capture_output=True, text=True, timeout=60, check=True).stdout
        cls.docs = json.loads(subprocess.run(["yq", "eval-all", "-o=json", "-I=0", "[.]", "-"],
                                             input=built, capture_output=True, text=True,
                                             timeout=60, check=True).stdout)

    def docs_config(self):
        config = next(d for d in self.docs if d["kind"] == "ConfigMap"
                      and d["metadata"]["name"] == "hermes-config-private")["data"]["config.yaml"]
        return json.loads(subprocess.run(["yq", "-o=json", "-I=0", ".", "-"], input=config, capture_output=True,
                                         text=True, timeout=60, check=True).stdout)

    def test_one_release_labelled_on_its_pods(self):
        # The NetworkPolicies select pods; a controller label never reaches them.
        releases = [d for d in self.docs if d["kind"] == "HelmRelease"]
        self.assertEqual(["hermes-private"], [r["metadata"]["name"] for r in releases])
        main = releases[0]["spec"]["values"]["controllers"]["main"]
        self.assertEqual({"assistant.scope": "private"}, main["pod"]["labels"])
        self.assertNotIn("labels", main)

    def test_general_memory_is_read_only_for_the_private_side(self):
        # Private facts must never be written into the store general agents read.
        keys = (ROOT / "kubernetes/apps/main/llm/memini-general/app/externalsecret.yaml").read_text()
        for holder in ("hermes", "paseo-private"):
            entry = keys[keys.index(f"- name: {holder}\n"):]
            self.assertIn("read_only: true", entry.split("- name:")[1], holder)
        config = (ROOT / "kubernetes/apps/main/llm/hermes/app/config.yaml").read_text()
        server = config[config.index("  general_memory:"):]
        self.assertIn("include: [memory_recall, memory_briefing, memory_get, memory_list, memory_history]", server)
        # The private workshop gets the store's address and its key; dotfiles renders the server.
        release = (ROOT / "kubernetes/apps/main/llm/paseo/private/helmrelease.yaml").read_text()
        self.assertIn("MEMINI_GENERAL_URL: &general-memory http://memini-general.llm.svc.cluster.local:8080", release)
        self.assertIn("MEMINI_GENERAL_URL: *general-memory", release)
        self.assertIn("key: MEMINI_GENERAL_API_KEY", release)

    def test_egress_is_the_named_services_and_telegram(self):
        # The pod holds private data: everything it may reach is listed here.
        policy = next(d for d in self.docs if d["kind"] == "NetworkPolicy")["spec"]
        self.assertEqual(["Ingress", "Egress"], policy["policyTypes"])
        self.assertNotIn("ingress", policy)
        reach = {(next(iter(peer["podSelector"]["matchLabels"].values())), port["port"])
                 for rule in policy["egress"] for peer in rule["to"] for port in rule["ports"]}
        self.assertEqual({("kube-dns", 53), ("litellm", 4000), ("memini", 8080), ("memini-code", 8080),
                          ("mcp-assistant", 4483), ("paseo", 6767), ("paseo-private", 6767)}, reach)
        cilium = [d["spec"] for d in self.docs if d["kind"] == "CiliumNetworkPolicy"]
        self.assertEqual(1, len(cilium))
        self.assertEqual({"app.kubernetes.io/name": "hermes-private", "assistant.scope": "private"},
                         cilium[0]["endpointSelector"]["matchLabels"])
        self.assertNotIn("ingress", cilium[0])
        dns, internet = cilium[0]["egress"]
        self.assertEqual(["toEndpoints", "toPorts"], sorted(dns))
        self.assertEqual({"toFQDNs": [{"matchName": "api.telegram.org"}],
                          "toPorts": [{"ports": [{"port": "443", "protocol": "TCP"}]}]}, internet)

    def test_workshop_handoffs_ask_every_time_and_bring_no_shell(self):
        # The daemons serve terminals, a browser and schedules too. The assistant registers
        # only lookups, and the two tools that start work, which must ask on every call.
        config = self.docs_config()["mcp_servers"]
        lookups = ["list_profiles", "list_workspaces", "list_agents", "get_agent_status", "get_agent_activity"]
        for scope, host in (("general", "paseo"), ("private", "paseo-private")):
            with self.subTest(scope=scope):
                status, start = config[f"{scope}_workshop_status"], config[f"{scope}_workshop"]
                url = f"http://{host}.llm.svc.cluster.local:6767/mcp/agents"
                self.assertEqual([url, url], [status["url"], start["url"]])
                self.assertEqual(lookups, status["tools"]["include"])
                self.assertEqual(["create_agent", "send_agent_prompt"], start["tools"]["include"])
                self.assertEqual("untrusted", start["trust"])
                # Over the chat's limit from the first call: the answer covers one call, no "always".
                self.assertEqual({"create_agent", "send_agent_prompt"}, set(start["tool_costs"]))
                for cost in start["tool_costs"].values():
                    self.assertGreater(cost["credits"], start["spend_limit"])
                self.assertGreater(start["spend_limit"], 0)
                for server in (status, start):
                    self.assertEqual(f"Bearer $${{PASEO_{scope.upper()}_PASSWORD}}", server["headers"]["Authorization"])
        release = next(d for d in self.docs if d["kind"] == "HelmRelease")
        env = release["spec"]["values"]["controllers"]["main"]["containers"]["hermes"]["env"]
        for scope in ("GENERAL", "PRIVATE"):
            self.assertEqual({"name": "hermes-workshops", "key": f"PASEO_{scope}_PASSWORD"},
                             env[f"PASEO_{scope}_PASSWORD"]["valueFrom"]["secretKeyRef"])
        ks = (ROOT / "kubernetes/apps/main/llm/paseo/ks.yaml").read_text()
        for host in ("paseo.llm.svc.cluster.local", "paseo-private.llm.svc.cluster.local"):
            self.assertIn("," + host + "\n", ks)  # the daemon refuses a Host it does not know

    def test_telegram_polls_and_answers_only_the_allowed_users(self):
        release = next(d for d in self.docs if d["kind"] == "HelmRelease")
        env = release["spec"]["values"]["controllers"]["main"]["containers"]["hermes"]["env"]
        # No webhook, so nothing connects in; no allow-all; no bare-IP fallback.
        self.assertFalse({"TELEGRAM_WEBHOOK_URL", "TELEGRAM_ALLOW_ALL_USERS", "TELEGRAM_FALLBACK_IPS"} & set(env))
        self.assertEqual("true", env["HERMES_TELEGRAM_DISABLE_FALLBACK_IPS"])
        self.assertEqual("http://127.0.0.1:9", env["HTTPS_PROXY"])
        for name in ("NO_PROXY", "no_proxy"):
            self.assertEqual(".svc.cluster.local,.svc,localhost,127.0.0.1,api.telegram.org", env[name])
        fields = ("TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_USERS", "TELEGRAM_HOME_CHANNEL")
        for field in fields:
            self.assertEqual({"name": "hermes-messaging", "key": field}, env[field]["valueFrom"]["secretKeyRef"])
        secret = next(d for d in self.docs if d["kind"] == "ExternalSecret")["spec"]
        self.assertEqual({f: "{{ .%s }}" % f for f in fields}, secret["target"]["template"]["data"])
        self.assertEqual([{"extract": {"key": "hermes"}}], secret["dataFrom"])
        config = (ROOT / "kubernetes/apps/main/llm/hermes/app/config.yaml").read_text()
        self.assertIn("\nunauthorized_dm_behavior: ignore\n", config)

    def test_routines_are_read_only_and_bring_no_shell(self):
        config = yaml_of(ROOT / "kubernetes/apps/main/llm/hermes/app/config.yaml")
        # Skills and sub-agents are on; everything that is a shell or a way out stays off,
        # and so does the tool that would let the assistant schedule jobs by itself.
        off = set(config["agent"]["disabled_toolsets"])
        self.assertLessEqual({"terminal", "code_execution", "file", "browser", "computer_use", "web",
                              "search", "x_search", "cronjob"}, off)
        self.assertFalse({"skills", "delegation"} & off)
        # Nobody answers a scheduled run, so it must not be able to approve itself.
        self.assertEqual({"mode": "manual", "cron_mode": "deny"}, config["approvals"])
        self.assertEqual({"external_dirs": ["/opt/hermes-routines/skills", "/opt/dotfiles-skills"],
                          "write_approval": True}, config["skills"])
        self.assertEqual(1, config["delegation"]["max_spawn_depth"])
        # Schedules and "today" are on the user's clock, and a routine's message can be answered.
        self.assertEqual("America/Toronto", config["timezone"])
        self.assertTrue(config["cron"]["mirror_delivery"])
        values = next(d for d in self.docs if d["kind"] == "HelmRelease")["spec"]["values"]
        # The folder is mounted whole, read-only; the init container lays the skills out in a
        # volume that only it may write.
        self.assertEqual([{"path": "/opt/hermes-routines/src", "readOnly": True}],
                         values["persistence"]["routines"]["globalMounts"])
        laid_out = values["persistence"]["routine-skills"]["advancedMounts"]["main"]
        self.assertEqual([{"path": "/opt/hermes-routines/skills"}], laid_out["routines"])
        self.assertEqual([{"path": "/opt/hermes-routines/skills", "readOnly": True}], laid_out["hermes"])
        main = values["controllers"]["main"]
        sync = main["initContainers"]["routines"]
        self.assertEqual(main["containers"]["hermes"]["image"], sync["image"])
        self.assertEqual(10000, sync["securityContext"]["runAsUser"])
        self.assertFalse(sync["securityContext"]["allowPrivilegeEscalation"])
        routines = next(d for d in self.docs if d["kind"] == "ConfigMap" and d["metadata"]["name"] == "hermes-routines")
        self.assertNotIn("${", routines["data"]["sync.sh"])  # Flux would substitute it
        # Every skill is named after its file, and every folder in the repo is shipped. One with
        # a schedule names a model the assistant's key allows.
        allowed = next(d for d in self.docs if d["kind"] == "LiteLLMVirtualKey")["spec"]["models"]
        folder = ROOT / "kubernetes/apps/main/llm/hermes/app/routines"
        skills = {key[:-3]: text for key, text in routines["data"].items() if key.endswith(".md")}
        self.assertEqual({d.name for d in folder.iterdir() if d.is_dir()}, set(skills))
        scheduled = []
        for name, text in skills.items():
            front = yaml_text(text.split("\n---\n")[0])
            self.assertEqual(name, front["name"])
            if "metadata" in front:
                self.assertIn(front["metadata"]["model"], allowed, name)
                self.assertRegex(front["metadata"]["schedule"], r"^\S+ \S+ \S+ \S+ \S+$", name)
                scheduled.append(name)
        self.assertIn("daily-briefing", scheduled)

    def test_dotfiles_skills_are_synced_pinned_and_read_only(self):
        # The shared skills folder in h-wb/dotfiles (conf.d/ai/skills) reaches the pod
        # the way the Memini plugin does: a Job fetches the repo at a pinned, checksummed
        # ref into a volume mounted read-only. The pod's egress never sees GitHub.
        config = yaml_of(ROOT / "kubernetes/apps/main/llm/hermes/app/config.yaml")
        self.assertEqual(["/opt/hermes-routines/skills", "/opt/dotfiles-skills"],
                         config["skills"]["external_dirs"])
        values = next(d for d in self.docs if d["kind"] == "HelmRelease")["spec"]["values"]
        mount = values["persistence"]["dotfiles-skills"]
        self.assertEqual("hermes-skills", mount["existingClaim"])
        self.assertEqual([{"path": "/opt/dotfiles-skills", "readOnly": True}], mount["globalMounts"])
        job = next(d for d in self.docs if d["kind"] == "Job" and d["metadata"]["name"] == "hermes-skills-sync")
        env = {e["name"]: e["value"] for e in job["spec"]["template"]["spec"]["containers"][0]["env"]}
        self.assertEqual(40, len(env["DOTFILES_REF"]))  # a commit sha
        self.assertEqual(64, len(env["DOTFILES_TAR_SHA256"]))  # sha256 of the tarball
        volumes = {v["name"]: v for v in job["spec"]["template"]["spec"]["volumes"]}
        self.assertEqual("hermes-skills", volumes["skills"]["persistentVolumeClaim"]["claimName"])
        self.assertTrue(volumes["scripts"]["configMap"]["name"].startswith("hermes-skills-sync"))
        script = next(d for d in self.docs if d["kind"] == "ConfigMap"
                      and d["metadata"]["name"].startswith("hermes-skills-sync"))["data"]["sync.sh"]
        self.assertNotIn("${", script)  # Flux would substitute it
        self.assertIn("codeload.github.com/h-wb/dotfiles", script)
        self.assertIn("conf.d/ai/skills", script)
        self.assertIn("sha256sum -c", script)
        pvc = next(d for d in self.docs if d["kind"] == "PersistentVolumeClaim"
                   and d["metadata"]["name"] == "hermes-skills")
        self.assertEqual(["ReadWriteMany"], pvc["spec"]["accessModes"])

    def test_key_grants_no_cloud_model_and_only_private_paseo_may_exec(self):
        keys = [d for d in self.docs if d["kind"] == "LiteLLMVirtualKey"]
        self.assertEqual(["hermes-private"], [k["metadata"]["name"] for k in keys])
        cloud = ("anthropic/", "chatgpt/", "gpt-", "codex-")
        self.assertFalse([m for m in keys[0]["spec"]["models"] if m.startswith(cloud)])
        subjects = [s["name"] for d in self.docs if d["kind"] == "RoleBinding" for s in d["subjects"]]
        self.assertEqual(["paseo-private"], subjects)


if __name__ == "__main__":
    unittest.main()
