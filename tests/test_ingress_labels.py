"""Ingress rules as pod labels, one cluster-wide rule each: `ingress.home.arpa/<gateway>:
allow` admits that Envoy gateway only; `ingress.home.arpa/lan: deny` refuses the LAN.

Run with python3 -B -m unittest discover -s tests -p test_ingress_labels.py.
"""
import json
import re
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
NETPOLS = "kubernetes/apps/main/kube-system/cilium/netpols"
GATEWAYS = {"envoy-internal", "envoy-external"}
VOCABULARY = {**{gateway: "allow" for gateway in GATEWAYS}, "lan": "deny"}
LABEL = re.compile(r"^\s*ingress\.home\.arpa/([\w-]+):\s*(\S+)", re.M)
# The apps whose own NetworkPolicy the gateway labels replaced; each admitted its gateway only.
LOCKED = {
    "kubernetes/apps/main/default/code-server/app": "envoy-external",
    "kubernetes/apps/main/default/orbit/app": "envoy-internal",
    "kubernetes/apps/main/llm/hermes/app": "envoy-internal",
}


def build(path):
    built = subprocess.run(["kustomize", "build", path], cwd=ROOT, capture_output=True, text=True,
                           timeout=60, check=True).stdout
    return json.loads(subprocess.run(["yq", "eval-all", "-o=json", "-I=0", "[.]", "-"], input=built,
                                     capture_output=True, text=True, timeout=60, check=True).stdout)


def pod_labels(release, controller):
    values = release["spec"]["values"]
    return {**values.get("defaultPodOptions", {}).get("labels", {}),
            **values["controllers"][controller].get("pod", {}).get("labels", {})}


class IngressLabels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = {d["metadata"]["name"]: d["spec"] for d in build(NETPOLS)
                     if d["kind"] == "CiliumClusterwideNetworkPolicy"}

    def test_each_gateway_label_admits_that_gateway_only(self):
        for gateway in GATEWAYS:
            self.assertEqual({
                "endpointSelector": {"matchLabels": {f"ingress.home.arpa/{gateway}": "allow"}},
                "ingress": [{"fromEndpoints": [{"matchLabels": {
                    "k8s:io.kubernetes.pod.namespace": "network",
                    "gateway.envoyproxy.io/owning-gateway-name": gateway}}]}],
            }, self.rules[f"ingress-{gateway}"], gateway)

    def test_the_lan_label_refuses_world_and_locks_nothing(self):
        self.assertEqual({
            "endpointSelector": {"matchLabels": {"ingress.home.arpa/lan": "deny"}},
            "enableDefaultDeny": {"ingress": False},
            "ingressDeny": [{"fromEntities": ["world"]}],
        }, self.rules["ingress-lan-deny"])

    def test_every_label_in_the_repo_has_a_rule(self):
        # A misspelt label matches no rule and leaves the pod open.
        for path in (ROOT / "kubernetes").rglob("*.yaml"):
            for name, value in LABEL.findall(path.read_text()):
                self.assertEqual(VOCABULARY.get(name), value, f"{path}: {name}")

    def test_the_login_less_load_balancers_keep_the_lan_off(self):
        for app, labels in {
            "observability/kube-prometheus-stack": ("prometheus", "prometheusSpec", "podMetadata", "labels"),
            "observability/victoria-logs": ("server", "podLabels"),
        }.items():
            docs = build(f"kubernetes/apps/main/{app}/app")
            values = next(d for d in docs if d["kind"] == "HelmRelease")["spec"]["values"]
            for key in labels:
                values = values[key]
            self.assertEqual("deny", values["ingress.home.arpa/lan"], app)
            self.assertTrue([d for d in docs if d["kind"] == "Service" and d["spec"].get("type") == "LoadBalancer"], app)

    def test_a_labelled_app_is_routed_through_its_gateway(self):
        # Otherwise the label refuses the gateway that serves it.
        for path in (ROOT / "kubernetes/apps").rglob("helmrelease.yaml"):
            text = path.read_text()
            labels = {name for name, _ in LABEL.findall(text)} & GATEWAYS
            if labels:
                routed = set(re.findall(r"parentRefs:\s*\n\s*- name: ([\w-]+)", text))
                self.assertEqual(labels, routed, path)

    def test_the_replaced_locks_admit_what_they_did(self):
        for app, gateway in LOCKED.items():
            docs = build(app)
            release = next(d for d in docs if d["kind"] == "HelmRelease")
            for controller in release["spec"]["values"]["controllers"]:
                self.assertEqual("allow", pod_labels(release, controller).get(f"ingress.home.arpa/{gateway}"), app)
            # No policy of its own admits anyone else.
            for doc in docs:
                if doc["kind"] in ("NetworkPolicy", "CiliumNetworkPolicy"):
                    self.assertNotIn("ingress", doc["spec"], app)
                    self.assertNotIn("Ingress", doc["spec"].get("policyTypes", []), app)


if __name__ == "__main__":
    unittest.main()
