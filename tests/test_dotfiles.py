"""components/dotfiles and its pods: the rendered hook, run against scratch homes.

Run with python3 -B -m unittest discover -s tests -p test_dotfiles.py.
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
URL = "https://github.com/h-wb/dotfiles.git"
CLUSTER = (ROOT / "kubernetes/clusters/main/ks.yaml").read_text()
PIN = re.search(r'DOTFILES_REF: "([0-9a-f]{40})"', CLUSTER).group(1)


def run(*args, text=None, env=None, cwd=ROOT):
    result = subprocess.run(args, input=text, env=env, cwd=cwd, capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise AssertionError(f"{args[0]} failed: {result.stderr}")
    return result.stdout


def render(app):
    # What Flux does with ks.yaml: the app path plus spec.components, then
    # strict post-build substitution with the cluster's variables added.
    ks = json.loads(run("yq", "-o=json", "-I=0", ".", f"{app}/ks.yaml"))
    path = (ROOT / ks["spec"]["path"]).resolve()
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "kustomization.yaml").write_text(json.dumps({
            "apiVersion": "kustomize.config.k8s.io/v1beta1", "kind": "Kustomization",
            "resources": [os.path.relpath(path, tmp)],
            "components": [os.path.relpath((path / c).resolve(), tmp) for c in ks["spec"]["components"]],
        }))
        built = run("kustomize", "build", "--load-restrictor=LoadRestrictionsNone", tmp)
    variables = {**ks["spec"]["postBuild"]["substitute"], "SECRET_DOMAIN": "example.com",
                 "DOTFILES_REF": PIN}
    env = {key: os.environ[key] for key in ("HOME", "PATH") if key in os.environ}
    built = run("flux", "envsubst", "--strict", text=built, env={**env, **variables})
    return ks, json.loads(run("yq", "eval-all", "-o=json", "-I=0", "[.]", "-", text=built))


def one(docs, kind, name):
    return next(d for d in docs if d["kind"] == kind and d["metadata"]["name"] == name)


class Hook(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, docs = render("kubernetes/apps/main/default/code-server")
        cls.data = one(docs, "ConfigMap", "code-server-dotfiles")["data"]
        cls.hook = cls.data["dotfiles-bootstrap"]

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="dotfiles-hook-")
        self.addCleanup(temp.cleanup)
        self.tmp = Path(temp.name)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.dir = self.home / ".dotfiles"
        # GitHub's stand-in: a repo whose commits can be fetched by id.
        self.upstream = self.tmp / "dotfiles"
        (self.upstream / "scripts").mkdir(parents=True)
        self.git("init", "-q", "-b", "master", cwd=self.upstream)
        self.git("config", "uploadpack.allowReachableSHA1InWant", "true", cwd=self.upstream)
        (self.upstream / ".gitignore").write_text("*.local.toml\n")
        # pod-bootstrap records its argument, the pin it was told and the commit it runs.
        self.ref = self.commit("first", 'echo "run $* ref=$DOTFILES_REF head=$(git -C "$HOME/.dotfiles" rev-parse HEAD)"'
                                        ' >> "$HOME/bootstrap.runs"\n')

    def git(self, *args, cwd):
        return run("git", "-c", "user.name=t", "-c", "user.email=t@example.test", *args, cwd=cwd).strip()

    def commit(self, marker, body=None):
        if body is not None:
            (self.upstream / "scripts/pod-bootstrap").write_text(body)
        (self.upstream / "marker").write_text(marker + "\n")
        self.git("add", "-A", cwd=self.upstream)
        self.git("commit", "-q", "-m", marker, cwd=self.upstream)
        return self.git("rev-parse", "HEAD", cwd=self.upstream)

    def run_hook(self, *args, ref=None):
        self.assertEqual(self.hook.count(URL), 1)
        self.assertEqual(self.hook.count(f"ref={PIN}\n"), 1)
        script = self.tmp / "dotfiles-bootstrap"
        # Real git; only the remote is a local repo, and the pin one of its commits.
        script.write_text(self.hook.replace(URL, f"file://{self.upstream}")
                          .replace(f"ref={PIN}\n", f"ref={ref or self.ref}\n"))
        result = subprocess.run(["/bin/sh", str(script), *args], capture_output=True, text=True, timeout=120,
                                env={"HOME": str(self.home), "PATH": os.environ["PATH"]})
        self.assertEqual(result.returncode, 0, result.stderr)  # the pod always starts
        runs = self.home / "bootstrap.runs"
        lines = runs.read_text().splitlines() if runs.exists() else []
        runs.unlink(missing_ok=True)
        return result, lines

    def head(self):
        return self.git("rev-parse", "HEAD", cwd=self.dir)

    def test_inputs_are_the_pin_and_the_apps_environment(self):
        self.assertIn(f"ref={PIN}\n", self.hook)
        self.assertIn("env=code-server\n", self.hook)

    def test_empty_home_clones_the_pin_and_bootstraps(self):
        self.commit("later")  # the pin, not the default branch's tip
        _, runs = self.run_hook()
        self.assertEqual(self.head(), self.ref)
        self.assertEqual((self.dir / "marker").read_text(), "first\n")
        self.assertEqual(runs, [f"run code-server ref={self.ref} head={self.ref}"])

    def test_a_new_pin_moves_the_clone_and_stashes_local_changes(self):
        self.run_hook()
        (self.dir / "marker").write_text("edited\n")
        (self.dir / "local-work").write_text("untracked\n")
        (self.dir / "config.local.toml").write_text("[vars]\n")
        new = self.commit("second")
        _, runs = self.run_hook(ref=new)
        self.assertEqual(self.head(), new)
        self.assertEqual((self.dir / "marker").read_text(), "second\n")
        self.assertFalse((self.dir / "local-work").exists())
        self.assertTrue((self.dir / "config.local.toml").exists())  # ignored files stay
        stash = self.git("stash", "list", cwd=self.dir)
        self.assertIn(f"local changes before {new}", stash)
        self.assertEqual(self.git("show", "stash@{0}:marker", cwd=self.dir), "edited")
        self.assertEqual(self.git("show", "stash@{0}^3:local-work", cwd=self.dir), "untracked")
        self.assertEqual(runs, [f"run code-server ref={new} head={new}"])

    def test_a_clone_from_before_the_pin_is_moved_and_keeps_its_branch(self):
        # The old flow's clone: on master, maybe with commits never pushed.
        run("git", "clone", "-q", str(self.upstream), str(self.dir))
        (self.dir / "unpushed").write_text("work\n")
        self.git("add", "unpushed", cwd=self.dir)
        self.git("commit", "-q", "-m", "unpushed", cwd=self.dir)
        unpushed = self.head()
        new = self.commit("second")
        _, runs = self.run_hook(ref=new)
        self.assertEqual(self.head(), new)
        self.assertEqual(self.git("rev-parse", "master", cwd=self.dir), unpushed)
        self.assertEqual(runs, [f"run code-server ref={new} head={new}"])

    def test_failed_fetch_runs_the_previous_commit_and_says_so(self):
        self.run_hook()
        missing = "b" * 40
        result, runs = self.run_hook(ref=missing)
        self.assertIn(f"dotfiles: fetch failed for {missing}; keeping {self.ref[:7]}", result.stdout)
        self.assertEqual(self.head(), self.ref)
        # pod-bootstrap is told the pin, so it reports the run as stale.
        self.assertEqual(runs, [f"run code-server ref={missing} head={self.ref}"])

    def test_failed_clone_on_an_empty_home_still_starts_the_pod(self):
        shutil.rmtree(self.upstream)
        result, runs = self.run_hook()
        self.assertEqual(runs, [])
        self.assertFalse(self.dir.exists())
        self.assertIn("dotfiles: fetch failed", result.stdout)
        self.assertIn("nothing to run", result.stdout)

    def test_fetch_and_run_alone(self):
        _, runs = self.run_hook("fetch")
        self.assertEqual(runs, [])
        self.assertEqual(self.head(), self.ref)
        shutil.rmtree(self.upstream)
        _, runs = self.run_hook("run")
        self.assertEqual(runs, [f"run code-server ref={self.ref} head={self.ref}"])

    def test_failed_bootstrap_still_starts_the_pod(self):
        self.ref = self.commit("broken", "exit 3\n")
        result, _ = self.run_hook()
        self.assertIn("starting anyway", result.stdout)

    def test_desktop_entry_runs_only_the_bootstrap(self):
        entry = self.data["dotfiles-bootstrap.desktop"]
        self.assertIn("\nExec=/bin/sh /opt/dotfiles/dotfiles-bootstrap run\n", entry)


class Pods(unittest.TestCase):
    def test_code_server(self):
        ks, docs = render("kubernetes/apps/main/default/code-server")
        self.assertEqual(ks["spec"]["postBuild"]["substitute"]["DOTFILES_ENV"], "code-server")
        release = one(docs, "HelmRelease", "code-server")
        values = release["spec"]["values"]
        controller = values["controllers"]["code-server"]
        init = controller["initContainers"]["bootstrap"]
        self.assertEqual(init["command"], ["/bin/sh", "/opt/dotfiles/dotfiles-bootstrap"])
        mount = values["persistence"]["dotfiles"]
        self.assertEqual(mount["name"], "code-server-dotfiles")
        self.assertEqual(mount["advancedMounts"]["code-server"]["bootstrap"][0]["path"], "/opt/dotfiles")
        # A new pin changes the hook's ConfigMap; Reloader rolls the pod.
        self.assertEqual(controller["annotations"]["reloader.stakater.com/auto"], "true")
        app = controller["containers"]["app"]
        self.assertNotIn("--disable-workspace-trust", app["args"])
        self.assertFalse(any(arg.startswith("/") for arg in app["args"]), app["args"])
        for container in (app, init):
            self.assertEqual(container["envFrom"], [{"secretRef": {"name": "code-server-secret", "optional": True}}])
        template = one(docs, "ExternalSecret", "code-server")["spec"]["target"]["template"]["data"]
        self.assertEqual(list(template), ["PROTON_PASS_TOKEN"])
        self.assertFalse(values["defaultPodOptions"]["automountServiceAccountToken"])
        self.assertEqual(controller["strategy"], "Recreate")

    def test_neko(self):
        ks, docs = render("kubernetes/apps/main/default/neko")
        self.assertEqual(ks["spec"]["postBuild"]["substitute"]["DOTFILES_ENV"], "neko")
        values = one(docs, "HelmRelease", "neko")["spec"]["values"]
        controller = values["controllers"]["neko"]
        app = controller["containers"]["app"]
        # Fetched before the desktop starts, as the desktop's own user. The neko
        # image has no git, so the fetch runs in a pinned git image.
        init = controller["initContainers"]["dotfiles"]
        self.assertEqual(init["command"], ["/bin/sh", "/opt/dotfiles/dotfiles-bootstrap", "fetch"])
        self.assertEqual(init["image"]["repository"], "mirror.gcr.io/alpine/git")
        self.assertRegex(init["image"]["tag"], r"@sha256:[0-9a-f]{64}$")
        self.assertEqual((init["securityContext"]["runAsUser"], init["env"]["HOME"]), (1000, "/home/neko"))
        self.assertEqual(values["persistence"]["home"]["globalMounts"], [{"path": "/home/neko"}])
        mounts = values["persistence"]["dotfiles"]
        self.assertEqual(mounts["name"], "neko-dotfiles")
        self.assertEqual(mounts["advancedMounts"]["neko"]["dotfiles"], [{"path": "/opt/dotfiles", "readOnly": True}])
        # Run inside the session, by one system entry not named like the old user entry.
        self.assertEqual(mounts["advancedMounts"]["neko"]["app"], [
            {"path": "/opt/dotfiles", "readOnly": True},
            {"path": "/etc/xdg/autostart/dotfiles-bootstrap.desktop", "readOnly": True,
             "subPath": "dotfiles-bootstrap.desktop"}])
        self.assertNotIn("provision", values["persistence"])
        self.assertFalse(any("provision" in d["metadata"]["name"] for d in docs))
        self.assertEqual(controller["annotations"]["reloader.stakater.com/auto"], "true")


class Pin(unittest.TestCase):
    def test_one_pin_and_renovate_finds_it(self):
        renovate = (ROOT / ".renovaterc.json5").read_text()
        manager = re.search(r"""matchStrings: \[\s*'(# renovate: dotfiles[^']*)',?\s*\]""", renovate).group(1)
        # JSON5 string -> the regex Renovate compiles (named groups in Python's spelling).
        pattern = manager.replace("\\\\", "\\").replace("(?<", "(?P<")
        matches = re.findall(pattern, CLUSTER)
        self.assertEqual(matches, [PIN])
        self.assertIn('packageNameTemplate: "https://github.com/h-wb/dotfiles"', renovate)
        self.assertIn('datasourceTemplate: "git-refs"', renovate)
        # The rule that batches it matches the depName: packageName is the URL,
        # and Renovate's package-name matcher reads only that.
        dep = re.search(r'depNameTemplate: "([^"]+)"', renovate).group(1)
        rule = renovate[renovate.index('description: "The dotfiles pin'):]
        rule = rule[:rule.index("}")]
        self.assertIn(f'matchDepNames: ["{dep}"]', rule)
        self.assertNotIn("matchPackageNames", rule)
        for setting in ("automerge: false", 'schedule: ["* 0-1 * * *"]'):
            self.assertIn(setting, rule)

    def test_every_consumer_reads_the_pin(self):
        # Nothing else in kubernetes/ names a dotfiles commit or fetches the
        # dotfiles another way.
        users = {}
        for path in (ROOT / "kubernetes").rglob("*"):
            if path.is_file() and path.suffix not in (".md",):
                text = path.read_text(errors="ignore")
                if "github.com/h-wb/dotfiles" in text:
                    users[str(path.relative_to(ROOT))] = text
        self.assertEqual(sorted(users), [
            "kubernetes/apps/main/llm/paseo/common/helmrelease.yaml",
            "kubernetes/components/dotfiles/dotfiles-bootstrap",
        ])
        self.assertIn("dotfiles.git?ref=${DOTFILES_REF}", users["kubernetes/apps/main/llm/paseo/common/helmrelease.yaml"])
        self.assertIn("ref=${DOTFILES_REF}", users["kubernetes/components/dotfiles/dotfiles-bootstrap"])
        for text in users.values():
            self.assertEqual(re.findall(r"\b[0-9a-f]{40}\b", text), [])


if __name__ == "__main__":
    unittest.main()
