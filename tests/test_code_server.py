"""code-server: the rendered bootstrap hook, run against scratch home directories.

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
HOME = "/home/coder"
DOTFILES_URL = "https://github.com/h-wb/dotfiles.git"


def run(*args, text=None, env=None, cwd=ROOT):
    result = subprocess.run(args, input=text, env=env, cwd=cwd, capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise AssertionError(f"{args[0]} failed: {result.stderr}")
    return result.stdout


class CodeServerHook(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ks = json.loads(run("yq", "-o=json", "-I=0", ".", f"{APP}/ks.yaml"))
        variables = {**ks["spec"]["postBuild"]["substitute"], "SECRET_DOMAIN": "example.com"}
        env = {key: os.environ[key] for key in ("HOME", "PATH") if key in os.environ}
        built = run("flux", "envsubst", "--strict", text=run("kustomize", "build", f"{APP}/app"),
                    env={**env, **variables})
        docs = json.loads(run("yq", "eval-all", "-o=json", "-I=0", "[.]", "-", text=built))
        cls.docs = {doc["kind"]: doc for doc in docs}
        controller = cls.docs["HelmRelease"]["spec"]["values"]["controllers"]["code-server"]
        cls.controller = controller
        command = controller["initContainers"]["bootstrap"]["command"]
        assert command[:2] == ["/bin/sh", "-c"], command
        cls.hook = command[2]

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="code-server-hook-")
        self.addCleanup(temp.cleanup)
        self.tmp = Path(temp.name)
        self.home = self.tmp / "home"
        self.home.mkdir()
        # The upstream checkout the hook clones: a pod-bootstrap that records each run.
        self.upstream = self.tmp / "dotfiles"
        (self.upstream / "scripts").mkdir(parents=True)
        (self.upstream / "scripts/pod-bootstrap").write_text('echo run >> "$HOME/bootstrap.runs"\n')
        ident = ["-c", "user.name=t", "-c", "user.email=t@example.test"]
        for args in (["init", "-q", "-b", "master"], ["add", "."], [*ident, "commit", "-q", "-m", "x"]):
            run("git", "-C", str(self.upstream), *args)

    def hook_for(self, url):
        self.assertEqual(self.hook.count(DOTFILES_URL), 1)
        return self.hook.replace(HOME, str(self.home)).replace(DOTFILES_URL, str(url))

    def run_hook(self, url=None):
        env = {"HOME": str(self.home), "PATH": os.environ["PATH"]}
        result = subprocess.run(["/bin/sh", "-c", self.hook_for(url or self.upstream)], env=env,
                                capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr)  # the editor always starts
        runs = self.home / "bootstrap.runs"
        return result, runs.read_text().count("run") if runs.exists() else 0

    def broken(self):
        return sorted(p.name for p in self.home.glob(".dotfiles.broken-*"))

    def test_empty_home_clones_and_bootstraps(self):
        _, runs = self.run_hook()
        self.assertTrue((self.home / ".dotfiles/scripts/pod-bootstrap").is_file())
        self.assertEqual(runs, 1)
        self.assertEqual(self.broken(), [])

    def test_cut_off_clone_is_moved_aside_and_recloned(self):
        (self.home / ".dotfiles/.git").mkdir(parents=True)
        _, runs = self.run_hook()
        self.assertTrue((self.home / ".dotfiles/scripts/pod-bootstrap").is_file())
        self.assertEqual(runs, 1)
        self.assertEqual(len(self.broken()), 1)

    def test_healthy_checkout_is_used_as_is(self):
        run("git", "clone", "-q", str(self.upstream), str(self.home / ".dotfiles"))
        (self.home / ".dotfiles/local-work").write_text("uncommitted\n")
        _, runs = self.run_hook(url=self.tmp / "must-not-be-cloned")
        self.assertTrue((self.home / ".dotfiles/local-work").exists())
        self.assertEqual(runs, 1)
        self.assertEqual(self.broken(), [])

    def test_failed_clone_still_starts_the_editor(self):
        result, runs = self.run_hook(url=self.tmp / "missing")
        self.assertEqual(runs, 0)
        self.assertFalse((self.home / ".dotfiles").exists())
        self.assertIn("starting the editor anyway", result.stdout)
        # The next start tries again.
        _, runs = self.run_hook()
        self.assertEqual(runs, 1)

    def test_failed_bootstrap_still_starts_the_editor(self):
        (self.upstream / "scripts/pod-bootstrap").write_text("exit 3\n")
        run("git", "-C", str(self.upstream), "-c", "user.name=t", "-c", "user.email=t@example.test",
            "commit", "-q", "-am", "fail")
        result, _ = self.run_hook()
        self.assertIn("starting the editor anyway", result.stdout)

    def test_pod_shape(self):
        app = self.controller["containers"]["app"]
        self.assertNotIn("--disable-workspace-trust", app["args"])
        self.assertFalse(any(arg.startswith("/") for arg in app["args"]), app["args"])  # no folder: the dotfiles' repo list
        for container in (app, self.controller["initContainers"]["bootstrap"]):
            self.assertEqual(container["envFrom"], [{"secretRef": {"name": "code-server-secret", "optional": True}}])
        template = self.docs["ExternalSecret"]["spec"]["target"]["template"]["data"]
        self.assertEqual(list(template), ["PROTON_PASS_TOKEN"])
        values = self.docs["HelmRelease"]["spec"]["values"]
        self.assertFalse(values["defaultPodOptions"]["automountServiceAccountToken"])
        self.assertEqual(self.controller["strategy"], "Recreate")


if __name__ == "__main__":
    unittest.main()
