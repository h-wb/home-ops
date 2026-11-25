"""The Obsidian vault's app (default/obsidian-vault): its Seekstone servers, who may
reach each one, and how the gateways in llm list them.

Run with python3 -B -m unittest discover -s tests -p test_obsidian_vault.py.
"""
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
APP = "kubernetes/apps/main/default/obsidian-vault"
ENTRIES = "kubernetes/apps/main/llm/toolhive/mcp-servers/vault"


def build(path):
    built = subprocess.run(["kustomize", "build", path], cwd=ROOT, capture_output=True, text=True,
                           timeout=60, check=True).stdout
    return json.loads(subprocess.run(["yq", "eval-all", "-o=json", "-I=0", "[.]", "-"], input=built,
                                     capture_output=True, text=True, timeout=60, check=True).stdout)


def yaml_all(path):
    return json.loads(subprocess.run(["yq", "eval-all", "-o=json", "-I=0", "[.]", str(ROOT / path)],
                                     capture_output=True, text=True, timeout=60, check=True).stdout)


def gateways(*names):
    return {"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "llm"}},
            "podSelector": {"matchExpressions": [{"key": "app.kubernetes.io/instance", "operator": "In",
                                                  "values": list(names)}]}}


class ObsidianVault(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs = build(f"{APP}/app")
        cls.servers = {d["metadata"]["name"]: d["spec"] for d in cls.docs if d["kind"] == "MCPServer"}

    def resource(self, kind, name):
        return next(d for d in self.docs if d["kind"] == kind and d["metadata"]["name"] == name)

    def env(self, server):
        return {e["name"]: e["value"] for e in self.servers[server]["env"]}

    def test_the_gateways_list_the_servers_under_their_old_names(self):
        # Same workload names, so every tool name agents and routines use stays.
        entries = {d["metadata"]["name"]: d["spec"] for d in yaml_all(f"{ENTRIES}/mcpserverentry.yaml")}
        self.assertEqual({"vault-ro", "vault-inbox", "vault-review"}, set(entries))
        for name, spec in entries.items():
            with self.subTest(name=name):
                self.assertEqual(f"http://mcp-{name}-proxy.default.svc.cluster.local:8080/mcp", spec["remoteUrl"])
                self.assertEqual(8080, self.servers[name]["proxyPort"])
                self.assertEqual("streamable-http", spec["transport"])
                self.assertEqual({"name": "mcp-tools"}, spec["groupRef"])
        # Only the entries are in llm; the volume, the sync and the servers are the app's.
        self.assertEqual(["kustomization.yaml", "mcpserverentry.yaml"],
                         sorted(p.name for p in (ROOT / ENTRIES).iterdir()))

    def test_every_server_shares_the_vault_volume_and_is_in_no_group(self):
        self.assertEqual({"vault-ro", "vault-inbox", "vault-n8n", "vault-review"}, set(self.servers))
        for name, spec in self.servers.items():
            with self.subTest(name=name):
                self.assertNotIn("groupRef", spec)
                pod = spec["podTemplateSpec"]["spec"]
                claims = [v["persistentVolumeClaim"]["claimName"] for v in pod["volumes"] if "persistentVolumeClaim" in v]
                self.assertEqual(["obsidian-vault"], claims)
                affinity = pod["affinity"]["podAffinity"]["requiredDuringSchedulingIgnoredDuringExecution"]
                self.assertEqual([{"app.kubernetes.io/name": "obsidian-vault"}],
                                 [a["labelSelector"]["matchLabels"] for a in affinity])

    def test_each_server_writes_only_its_folders(self):
        self.assertEqual("1", self.env("vault-ro")["SEEKSTONE_READ_ONLY"])
        self.assertEqual("Notes/**,AI/**,Archives/**", self.env("vault-inbox")["SEEKSTONE_WRITE_PATHS"])
        n8n = self.env("vault-n8n")
        self.assertEqual("Notes/**,References/**", n8n["SEEKSTONE_WRITE_PATHS"])
        # It reads everything, as the REST API it replaces did: a moved journal note must be found.
        self.assertNotIn("SEEKSTONE_READ_PATHS", n8n)
        self.assertEqual("/audit/vault-n8n.jsonl", n8n["SEEKSTONE_AUDIT_FILE"])
        for name in ("vault-inbox", "vault-n8n"):
            # The undo journal would live in the vault and could be synced.
            self.assertEqual("0", self.env(name)["SEEKSTONE_HISTORY"])

    def test_each_proxy_answers_only_its_clients(self):
        def ingress(policy):
            return self.resource("NetworkPolicy", policy)["spec"]["ingress"]
        port = [{"port": 8080, "protocol": "TCP"}]
        self.assertEqual([{"from": [gateways("mcp-private", "mcp-assistant")], "ports": port}], ingress("vault-private"))
        self.assertEqual(["vault-ro", "vault-inbox"], self.resource("NetworkPolicy", "vault-private")["spec"]
                         ["podSelector"]["matchExpressions"][0]["values"])
        general = {"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "llm"}},
                   "podSelector": {"matchLabels": {"app.kubernetes.io/instance": "mcp-general"}}}
        self.assertEqual([{"from": [general], "ports": port}], ingress("vault-review"))
        n8n = {"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "automation"}},
               "podSelector": {"matchLabels": {"app.kubernetes.io/name": "n8n", "app.kubernetes.io/controller": "n8n"}}}
        self.assertEqual([{"from": [n8n], "ports": port}], ingress("vault-n8n"))
        # Backends answer ToolHive's pods here only (the proxies).
        tools = self.resource("NetworkPolicy", "vault-tools")["spec"]
        self.assertEqual({"toolhive": "true"}, tools["podSelector"]["matchLabels"])
        self.assertEqual([{"from": [{"podSelector": {"matchLabels": {"toolhive": "true"}}}]}], tools["ingress"])

    def test_the_sync_pod_reaches_only_obsidian(self):
        egress = self.resource("CiliumNetworkPolicy", "obsidian-vault")["spec"]["egress"]
        self.assertEqual([{"matchName": "obsidian.md"}, {"matchPattern": "*.obsidian.md"}], egress[1]["toFQDNs"])
        self.assertEqual(["Ingress"], self.resource("NetworkPolicy", "obsidian-vault")["spec"]["policyTypes"])
        self.assertNotIn("ingress", self.resource("NetworkPolicy", "obsidian-vault")["spec"])

    def test_the_app_is_backed_up_in_default(self):
        ks = yaml_all(f"{APP}/ks.yaml")[0]
        self.assertEqual(("obsidian-vault", "default"), (ks["metadata"]["name"], ks["metadata"]["namespace"]))
        self.assertIn("../../../../../components/kopiur/backup", ks["spec"]["components"])
        self.assertEqual(f"./{APP}/app", ks["spec"]["path"])
        self.assertIn({"name": "toolhive", "namespace": "llm"}, ks["spec"]["dependsOn"])
        # The component's PersistentVolumeClaim is named after the app: the claim the servers mount.
        self.assertEqual("obsidian-vault", ks["spec"]["postBuild"]["substitute"]["APP"])
        self.assertIn("./obsidian-vault/ks.yaml", (ROOT / "kubernetes/apps/main/default/kustomization.yaml").read_text())


if __name__ == "__main__":
    unittest.main()
