"""Egress allows for pods labelled `policy.home.arpa/egress: internet`.

Any Cilium rule with an egress section switches the pods it selects to "only what
is allowed". So every allow written for the label must also select on it, or it
would cut an unlabelled pod off the internet.

Run with python3 -B -m unittest discover -s tests -p test_egress_labels.py.
"""
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
LABEL = {"policy.home.arpa/egress": "internet"}


def yaml_docs(path):
    return [d for d in json.loads(subprocess.run(["yq", "eval-all", "-o=json", "-I=0", "[.]", str(path)],
                                                 capture_output=True, text=True, timeout=60, check=True).stdout) if d]


class EgressAllows(unittest.TestCase):
    def test_app_template_rules_select_the_label(self):
        found = 0
        for path in (ROOT / "kubernetes/apps").rglob("helmrelease.yaml"):
            for doc in yaml_docs(path):
                policies = ((doc.get("spec") or {}).get("values") or {}).get("networkpolicies") or {}
                for name, policy in policies.items():
                    if policy.get("egress"):
                        found += 1
                        self.assertEqual("cilium", policy.get("type"), f"{path}: {name}")
                        self.assertEqual(LABEL, policy.get("extraSelectorLabels"), f"{path}: {name}")
        self.assertGreaterEqual(found, 4)

    def test_the_components_allow_labelled_pods_their_own_database_and_cache(self):
        for path, target, port in (
            ("kubernetes/components/cnpg/base/networkpolicy-egress.yaml", {"cnpg.io/cluster": "postgres-${APP}"}, "5432"),
            ("kubernetes/components/dragonfly/networkpolicy-egress.yaml", {"app": "${APP}-dragonfly"}, "6379"),
        ):
            spec = yaml_docs(ROOT / path)[0]["spec"]
            self.assertEqual({"app.kubernetes.io/instance": "${APP}", **LABEL}, spec["endpointSelector"]["matchLabels"])
            self.assertEqual([{"toEndpoints": [{"matchLabels": target}],
                               "toPorts": [{"ports": [{"port": port, "protocol": "TCP"}]}]}], spec["egress"])
            name = Path(path).parent / "kustomization.yaml"
            self.assertIn("./networkpolicy-egress.yaml", (ROOT / name).read_text())


if __name__ == "__main__":
    unittest.main()
