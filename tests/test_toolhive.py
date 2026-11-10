"""ToolHive gateway scopes: who may reach mcp-general (mcp-ops) and mcp-private
(mcp-gateway), in-cluster and through Envoy.

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
            "mcp-gateway": [ENVOY, pods(**{"app.kubernetes.io/name": "hermes-private",
                                           "assistant.scope": "private"}),
                            pods(**{"app.kubernetes.io/name": "paseo-private"})],
            "mcp-ops": [ENVOY, pods(**{"app.kubernetes.io/name": "paseo"})],
        }
        for gateway, clients in expected.items():
            with self.subTest(gateway=gateway):
                spec = self.resource("NetworkPolicy", gateway)["spec"]
                self.assertEqual({"app.kubernetes.io/instance": gateway}, spec["podSelector"]["matchLabels"])
                self.assertEqual([
                    {"from": clients, "ports": [{"port": 4483, "protocol": "TCP"}]},
                    {"from": PROMETHEUS, "ports": [{"port": 9464, "protocol": "TCP"}]},
                ], spec["ingress"])

    def test_general_gateway_never_lists_private_data(self):
        # Cloud models sit behind general; private's gateway serves everything.
        private = {"vault-ro", "vault-inbox", "personal-tasks", "dawarich", "metabase", "homeassistant"}
        aggregation = self.resource("VirtualMCPServer", "mcp-ops")["spec"]["config"]["aggregation"]
        self.assertEqual("deny", aggregation["defaultToolVisibility"])
        self.assertFalse({t["workload"] for t in aggregation["tools"]} & private)

    def test_envoy_takes_one_key_per_external_client_and_scope(self):
        # Bitwarden fields are <SCOPE>_<HOLDER>; the Envoy client is the holder.
        routes = {"mcp-gateway-api-key": ("mcp-gateway-api-keys", "PRIVATE_WORKSTATION"),
                  "mcp-ops-api-key": ("mcp-ops-api-keys", "GENERAL_WORKSTATION")}
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
        for gateway in ("mcp-gateway", "mcp-ops"):
            spec = self.resource("VirtualMCPServer", gateway)["spec"]
            self.assertEqual({"name": "prometheus"}, spec["telemetryConfigRef"])
            self.assertEqual({"name": "toolhive-config-redis", "key": "password"},
                             spec["sessionStorage"]["passwordRef"])
            prefixes.add(spec["sessionStorage"]["keyPrefix"])
        self.assertEqual(2, len(prefixes))
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

    def test_one_release_labelled_on_its_pods(self):
        # The NetworkPolicies select pods; a controller label never reaches them.
        releases = [d for d in self.docs if d["kind"] == "HelmRelease"]
        self.assertEqual(["hermes-private"], [r["metadata"]["name"] for r in releases])
        main = releases[0]["spec"]["values"]["controllers"]["main"]
        self.assertEqual({"assistant.scope": "private"}, main["pod"]["labels"])
        self.assertNotIn("labels", main)

    def test_key_grants_no_cloud_model_and_only_private_paseo_may_exec(self):
        keys = [d for d in self.docs if d["kind"] == "LiteLLMVirtualKey"]
        self.assertEqual(["hermes-private"], [k["metadata"]["name"] for k in keys])
        cloud = ("anthropic/", "chatgpt/", "gpt-", "codex-")
        self.assertFalse([m for m in keys[0]["spec"]["models"] if m.startswith(cloud)])
        subjects = [s["name"] for d in self.docs if d["kind"] == "RoleBinding" for s in d["subjects"]]
        self.assertEqual(["paseo-private"], subjects)


if __name__ == "__main__":
    unittest.main()
