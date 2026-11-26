"""Gateway locks as pod labels: `ingress.home.arpa/<gateway>: allow` admits that
Envoy gateway only, through one cluster-wide rule per gateway.

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
LABEL = re.compile(r"^\s*ingress\.home\.arpa/([\w-]+):\s*(\S+)", re.M)
# The apps whose own NetworkPolicy this replaced; each admitted its gateway only.
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

    def test_every_label_in_the_repo_has_a_rule(self):
        # A misspelt label matches no rule and leaves the pod open.
        for path in (ROOT / "kubernetes").rglob("*.yaml"):
            for name, value in LABEL.findall(path.read_text()):
                self.assertIn(name, GATEWAYS, path)
                self.assertEqual("allow", value, path)

    def test_a_labelled_app_is_routed_through_its_gateway(self):
        # Otherwise the label refuses the gateway that serves it.
        for path in (ROOT / "kubernetes/apps").rglob("helmrelease.yaml"):
            text = path.read_text()
            labels = set(LABEL.findall(text))
            if labels:
                routed = set(re.findall(r"parentRefs:\s*\n\s*- name: ([\w-]+)", text))
                self.assertEqual({name for name, _ in labels}, routed, path)

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
