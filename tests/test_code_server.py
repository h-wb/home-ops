"""code-server and components/dotfiles: the rendered hook, run against scratch homes.

Run with python3 -B -m unittest discover -s tests -p test_code_server.py.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
APP = "kubernetes/apps/main/default/code-server"
DOTFILES_URL = "https://github.com/h-wb/dotfiles.git"


def run(*args, text=None, env=None, cwd=ROOT):
    result = subprocess.run(args, input=text, env=env, cwd=cwd, capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise AssertionError(f"{args[0]} failed: {result.stderr}")
    return result.stdout


class CodeServerHook(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # What Flux does with ks.yaml: the app path plus spec.components, then
        # strict post-build substitution.
        ks = json.loads(run("yq", "-o=json", "-I=0", ".", f"{APP}/ks.yaml"))
        app = (ROOT / ks["spec"]["path"]).resolve()
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "kustomization.yaml").write_text(json.dumps({
                "apiVersion": "kustomize.config.k8s.io/v1beta1", "kind": "Kustomization",
                "resources": [os.path.relpath(app, tmp)],
                "components": [os.path.relpath((app / c).resolve(), tmp) for c in ks["spec"]["components"]],
            }))
            built = run("kustomize", "build", "--load-restrictor=LoadRestrictionsNone", tmp)
        variables = {**ks["spec"]["postBuild"]["substitute"], "SECRET_DOMAIN": "example.com"}
        env = {key: os.environ[key] for key in ("HOME", "PATH") if key in os.environ}
        built = run("flux", "envsubst", "--strict", text=built, env={**env, **variables})
        cls.docs = json.loads(run("yq", "eval-all", "-o=json", "-I=0", "[.]", "-", text=built))
        cls.release = cls.one("HelmRelease", "code-server")
        cls.controller = cls.release["spec"]["values"]["controllers"]["code-server"]
        cls.hook = cls.one("ConfigMap", "code-server-dotfiles")["data"]["dotfiles-bootstrap"]

    @classmethod
    def one(cls, kind, name):
        return next(d for d in cls.docs if d["kind"] == kind and d["metadata"]["name"] == name)

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="dotfiles-hook-")
        self.addCleanup(temp.cleanup)
        self.tmp = Path(temp.name)
        self.home = self.tmp / "home"
        self.home.mkdir()
        # The upstream checkout the hook clones: a pod-bootstrap that records each run and its arguments.
        self.upstream = self.tmp / "dotfiles"
        (self.upstream / "scripts").mkdir(parents=True)
        self.write_upstream('echo "run $*" >> "$HOME/bootstrap.runs"\n')

    def write_upstream(self, body):
        (self.upstream / "scripts/pod-bootstrap").write_text(body)
        ident = ["-c", "user.name=t", "-c", "user.email=t@example.test"]
        if not (self.upstream / ".git").exists():
            run("git", "init", "-q", "-b", "master", cwd=self.upstream)
        run("git", "add", ".", cwd=self.upstream)
        run("git", *ident, "commit", "-q", "-m", "x", cwd=self.upstream)

    def run_hook(self, *args, url=None):
        self.assertEqual(self.hook.count(DOTFILES_URL), 1)
        script = self.tmp / "dotfiles-bootstrap"
        script.write_text(self.hook.replace(DOTFILES_URL, str(url or self.upstream)))
        result = subprocess.run(["/bin/sh", str(script), *args], capture_output=True, text=True, timeout=120,
                                env={"HOME": str(self.home), "PATH": os.environ["PATH"]})
        self.assertEqual(result.returncode, 0, result.stderr)  # the pod always starts
        runs = self.home / "bootstrap.runs"
        return result, runs.read_text().splitlines() if runs.exists() else []

    def broken(self):
        return sorted(p.name for p in self.home.glob(".dotfiles.broken-*"))

    def test_empty_home_clones_and_bootstraps(self):
        _, runs = self.run_hook()
        self.assertTrue((self.home / ".dotfiles/scripts/pod-bootstrap").is_file())
        self.assertEqual(runs, ["run "])
        self.assertEqual(self.broken(), [])

    def test_cut_off_clone_is_moved_aside_and_recloned(self):
        (self.home / ".dotfiles/.git").mkdir(parents=True)
        _, runs = self.run_hook()
        self.assertTrue((self.home / ".dotfiles/scripts/pod-bootstrap").is_file())
        self.assertEqual(runs, ["run "])
        self.assertEqual(len(self.broken()), 1)

    def test_healthy_checkout_is_used_as_is(self):
        run("git", "clone", "-q", str(self.upstream), str(self.home / ".dotfiles"))
        (self.home / ".dotfiles/local-work").write_text("uncommitted\n")
        _, runs = self.run_hook(url=self.tmp / "must-not-be-cloned")
        self.assertTrue((self.home / ".dotfiles/local-work").exists())
        self.assertEqual(runs, ["run "])
        self.assertEqual(self.broken(), [])

    def test_arguments_reach_pod_bootstrap(self):
        # How neko would call it: its options pass through untouched.
        _, runs = self.run_hook("--pull", "--hold", "/x/.neko-hold", "--log", "neko-bootstrap")
        self.assertEqual(runs, ["run --pull --hold /x/.neko-hold --log neko-bootstrap"])

    def test_failed_clone_still_starts_the_pod(self):
        result, runs = self.run_hook(url=self.tmp / "missing")
        self.assertEqual(runs, [])
        self.assertFalse((self.home / ".dotfiles").exists())
        self.assertIn("starting anyway", result.stdout)
        _, runs = self.run_hook()  # the next start tries again
        self.assertEqual(runs, ["run "])

    def test_failed_bootstrap_still_starts_the_pod(self):
        self.write_upstream("exit 3\n")
        result, _ = self.run_hook()
        self.assertIn("starting anyway", result.stdout)

    def test_code_server_runs_the_component_hook(self):
        init = self.controller["initContainers"]["bootstrap"]
        self.assertEqual(init["command"], ["/bin/sh", "/opt/dotfiles/dotfiles-bootstrap"])
        mount = self.release["spec"]["values"]["persistence"]["dotfiles"]
        self.assertEqual(mount["name"], "code-server-dotfiles")
        self.assertEqual(mount["advancedMounts"]["code-server"]["bootstrap"][0]["path"], "/opt/dotfiles")

    def test_pod_shape(self):
        app = self.controller["containers"]["app"]
        self.assertNotIn("--disable-workspace-trust", app["args"])
        self.assertFalse(any(arg.startswith("/") for arg in app["args"]), app["args"])  # no folder: the dotfiles' repo list
        for container in (app, self.controller["initContainers"]["bootstrap"]):
            self.assertEqual(container["envFrom"], [{"secretRef": {"name": "code-server-secret", "optional": True}}])
        template = self.one("ExternalSecret", "code-server")["spec"]["target"]["template"]["data"]
        self.assertEqual(list(template), ["PROTON_PASS_TOKEN"])
        self.assertFalse(self.release["spec"]["values"]["defaultPodOptions"]["automountServiceAccountToken"])
        self.assertEqual(self.controller["strategy"], "Recreate")


if __name__ == "__main__":
    unittest.main()
