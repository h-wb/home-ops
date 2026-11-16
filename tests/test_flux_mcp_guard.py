"""The Flux MCP admission policy: reconcile passes, every other write is refused.

Run with python3 -B -m unittest discover -s tests -p test_flux_mcp_guard.py.
The policy's CEL is evaluated by cel-go (tests/cel), not by an API server, so
schema type-checking is not covered.
"""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
FLUX_MCP = "system:serviceaccount:llm:flux-mcp"

HELMRELEASE = {
    "apiVersion": "helm.toolkit.fluxcd.io/v2",
    "kind": "HelmRelease",
    "metadata": {
        "name": "code-server",
        "namespace": "default",
        "labels": {"app.kubernetes.io/name": "code-server"},
        "annotations": {"meta.helm.sh/release-name": "code-server"},
    },
    "spec": {
        "interval": "1h",
        "values": {"controllers": {"code-server": {"containers": {"app": {"image": {"tag": "1"}}}}}},
    },
}


def changed(edit):
    new = copy.deepcopy(HELMRELEASE)
    edit(new)
    return new


def annotate(**annotations):
    return changed(lambda o: o["metadata"]["annotations"].update(annotations))


class FluxMcpGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("go"):
            raise unittest.SkipTest("go is not installed")
        built = subprocess.run(["kustomize", "build", "kubernetes/apps/main/llm/toolhive/mcp-servers/flux"],
                               cwd=ROOT, capture_output=True, text=True, check=True).stdout
        docs = json.loads(subprocess.run(["yq", "eval-all", "-o=json", "-I=0", "[.]", "-"], input=built,
                                         capture_output=True, text=True, check=True).stdout)
        cls.policy = next(d for d in docs if d["kind"] == "ValidatingAdmissionPolicy"
                          and d["metadata"]["name"] == "flux-mcp-no-spec-changes")

    def evaluate(self, *cases):
        spec = self.policy["spec"]
        payload = {"matchConditions": spec["matchConditions"], "validations": spec["validations"],
                   "cases": [{"request": {"operation": op, "subResource": sub, "userInfo": {"username": user}},
                              "object": new, "oldObject": old} for op, sub, user, old, new in cases]}
        result = subprocess.run(["go", "run", "."], cwd=ROOT / "tests/cel", input=json.dumps(payload),
                                capture_output=True, text=True, timeout=300,
                                env={**os.environ, "GOFLAGS": "-mod=mod", "GOTOOLCHAIN": "local"})
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def update(self, new, sub="", user=FLUX_MCP, old=HELMRELEASE):
        return ("UPDATE", sub, user, old, new)

    def test_reconcile_requests_pass(self):
        bare = changed(lambda o: o["metadata"].pop("annotations"))
        cases = {
            "requestedAt": self.update(annotate(**{"reconcile.fluxcd.io/requestedAt": "1"})),
            "force and reset": self.update(annotate(**{"reconcile.fluxcd.io/requestedAt": "2",
                                                       "reconcile.fluxcd.io/forceAt": "2",
                                                       "reconcile.fluxcd.io/resetAt": "2"})),
            "again": self.update(annotate(**{"reconcile.fluxcd.io/requestedAt": "3"}),
                                 old=annotate(**{"reconcile.fluxcd.io/requestedAt": "2"})),
            "no annotations before": self.update(
                changed(lambda o: o["metadata"].update(annotations={"reconcile.fluxcd.io/requestedAt": "1"})),
                old=bare),
            "unchanged": self.update(HELMRELEASE),
        }
        for (name, _), result in zip(cases.items(), self.evaluate(*cases.values())):
            with self.subTest(name):
                self.assertTrue(result["matched"])
                self.assertEqual(result["denied"], [])

    def test_every_other_write_is_refused(self):
        container = {"image": {"repository": "busybox"}, "command": ["cat", "/home/coder/.config/gh/hosts.yml"]}
        cases = {
            "extra container": self.update(changed(
                lambda o: o["spec"]["values"]["controllers"]["code-server"]["containers"].update(x=container))),
            "suspend": self.update(changed(lambda o: o["spec"].update(suspend=True))),
            "label": self.update(changed(
                lambda o: o["metadata"]["labels"].update({"kustomize.toolkit.fluxcd.io/reconcile": "disabled"}))),
            "drop a label": self.update(changed(lambda o: o["metadata"].pop("labels"))),
            "prune annotation": self.update(annotate(**{"kustomize.toolkit.fluxcd.io/prune": "disabled"})),
            "operator annotation": self.update(annotate(**{"fluxcd.controlplane.io/reconcile": "disabled"})),
            "other reconcile.fluxcd.io key": self.update(annotate(**{"reconcile.fluxcd.io/other": "x"})),
            "drop an annotation": self.update(changed(lambda o: o["metadata"]["annotations"].clear())),
            "dangling owner": self.update(changed(lambda o: o["metadata"].update(ownerReferences=[
                {"apiVersion": "v1", "kind": "ConfigMap", "name": "gone",
                 "uid": "00000000-0000-0000-0000-000000000000"}]))),
            "finalizer": self.update(changed(lambda o: o["metadata"].update(finalizers=["x/y"]))),
            "status": self.update(changed(lambda o: o.update(status={"artifact": {"url": "http://evil"}})),
                                  sub="status"),
            "create": ("CREATE", "", FLUX_MCP, None, HELMRELEASE),
        }
        for (name, _), result in zip(cases.items(), self.evaluate(*cases.values())):
            with self.subTest(name):
                self.assertTrue(result["matched"])
                self.assertNotEqual(result["denied"], [])

    def test_other_users_are_not_matched(self):
        result, = self.evaluate(self.update(changed(lambda o: o["spec"].update(suspend=True)),
                                            user="system:serviceaccount:flux-system:kustomize-controller"))
        self.assertFalse(result["matched"])

    def test_match_covers_subresources(self):
        rules = self.policy["spec"]["matchConstraints"]["resourceRules"]
        self.assertTrue(all({"*", "*/*"} <= set(rule["resources"]) for rule in rules))


if __name__ == "__main__":
    unittest.main()
