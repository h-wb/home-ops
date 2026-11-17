"""components/dotfiles and its pods: the rendered hook, run against scratch homes.

Run with python3 -B -m unittest discover -s tests -p test_dotfiles.py.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CODELOAD = "https://codeload.github.com/h-wb/dotfiles/tar.gz/"
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
        self.served = self.tmp / "codeload"
        self.served.mkdir()
        self.upstream = self.tmp / "dotfiles"
        (self.upstream / "scripts").mkdir(parents=True)
        run("git", "init", "-q", "-b", "master", cwd=self.upstream)
        # pod-bootstrap records its argument, the pin it was told and the one it runs.
        self.serve(PIN, 'echo "run $* ref=$DOTFILES_REF pinned=$(cat "$HOME/.dotfiles/.pinned-commit")"'
                        ' >> "$HOME/bootstrap.runs"\n')

    def serve(self, ref, body, script="scripts/pod-bootstrap"):
        # A tarball laid out as codeload's: one top folder, named after repo and ref.
        for old in self.upstream.glob("scripts/*"):
            old.unlink()
        (self.upstream / script).parent.mkdir(parents=True, exist_ok=True)
        (self.upstream / script).write_text(body)
        (self.upstream / "marker").write_text(ref + "\n")
        run("git", "add", "-A", cwd=self.upstream)
        run("git", "-c", "user.name=t", "-c", "user.email=t@example.test", "commit", "-q", "-m", ref,
            cwd=self.upstream)
        run("git", "archive", "--format=tar.gz", f"--prefix=dotfiles-{ref}/", "-o",
            str(self.served / ref), "HEAD", cwd=self.upstream)

    def run_hook(self, *args):
        self.assertEqual(self.hook.count(CODELOAD), 1)
        script = self.tmp / "dotfiles-bootstrap"
        # Real curl and tar; only the host is a local folder.
        script.write_text(self.hook.replace(CODELOAD, f"file://{self.served}/"))
        result = subprocess.run(["/bin/sh", str(script), *args], capture_output=True, text=True, timeout=120,
                                env={"HOME": str(self.home), "PATH": os.environ["PATH"]})
        self.assertEqual(result.returncode, 0, result.stderr)  # the pod always starts
        runs = self.home / "bootstrap.runs"
        lines = runs.read_text().splitlines() if runs.exists() else []
        runs.unlink(missing_ok=True)
        return result, lines

    def leftovers(self):
        return sorted(p.name for p in self.home.iterdir() if p.name.startswith(".dotfiles."))

    def test_inputs_are_the_pin_and_the_apps_environment(self):
        self.assertIn(f"ref={PIN}\n", self.hook)
        self.assertIn("env=code-server\n", self.hook)

    def test_empty_home_fetches_the_pin_and_bootstraps(self):
        result, runs = self.run_hook()
        self.assertEqual((self.home / ".dotfiles/marker").read_text(), PIN + "\n")
        self.assertEqual((self.home / ".dotfiles/.pinned-commit").read_text(), PIN + "\n")
        self.assertEqual(runs, [f"run code-server ref={PIN} pinned={PIN}"])
        self.assertEqual(self.leftovers(), [])

    def test_whatever_was_there_is_replaced_fresh(self):
        # A checkout from the pin: none of it survives a start, local edits included.
        self.run_hook()
        (self.home / ".dotfiles/local-work").write_text("uncommitted\n")
        _, runs = self.run_hook()
        self.assertEqual(sorted(p.name for p in (self.home / ".dotfiles").iterdir()),
                         [".pinned-commit", "marker", "scripts"])
        self.assertEqual(runs, [f"run code-server ref={PIN} pinned={PIN}"])
        self.assertEqual(self.leftovers(), [])

    def test_a_clone_from_before_the_pin_is_kept_aside_once(self):
        # The old flow's git clone may hold unpushed work or a config.local.toml.
        old = self.home / ".dotfiles"
        (old / ".git").mkdir(parents=True)
        (old / "config.local.toml").write_text("[vars]\n")
        _, runs = self.run_hook()
        kept = self.home / ".dotfiles.pre-pin"
        self.assertTrue((kept / "config.local.toml").exists())
        self.assertEqual(runs, [f"run code-server ref={PIN} pinned={PIN}"])
        # Only the first one: a later clone is replaced like anything else.
        (old / ".git").mkdir()
        self.run_hook()
        self.assertFalse((old / ".git").exists())
        self.assertTrue((kept / "config.local.toml").exists())
        self.assertEqual(self.leftovers(), [".dotfiles.pre-pin"])

    def test_failed_fetch_runs_the_previous_checkout_and_says_so(self):
        self.run_hook()
        (self.served / PIN).unlink()
        result, runs = self.run_hook()
        self.assertIn("keeping the checkout already here", result.stdout)
        self.assertEqual(runs, [f"run code-server ref={PIN} pinned={PIN}"])
        self.assertEqual(self.leftovers(), [])

    def test_failed_fetch_on_an_empty_home_still_starts_the_pod(self):
        (self.served / PIN).unlink()
        result, runs = self.run_hook()
        self.assertEqual(runs, [])
        self.assertFalse((self.home / ".dotfiles").exists())
        self.assertIn("nothing to run", result.stdout)
        self.assertEqual(self.leftovers(), [])

    def test_a_tarball_without_the_script_is_not_swapped_in(self):
        self.run_hook()
        self.serve(PIN, "echo\n", script="scripts/other")
        result, runs = self.run_hook()
        self.assertEqual(len(runs), 1)
        self.assertTrue((self.home / ".dotfiles/scripts/pod-bootstrap").exists())
        self.assertIn("keeping the checkout already here", result.stdout)

    def test_fetch_and_run_alone(self):
        _, runs = self.run_hook("fetch")
        self.assertEqual(runs, [])
        self.assertTrue((self.home / ".dotfiles/.pinned-commit").exists())
        (self.served / PIN).unlink()
        _, runs = self.run_hook("run")
        self.assertEqual(runs, [f"run code-server ref={PIN} pinned={PIN}"])

    def test_failed_bootstrap_still_starts_the_pod(self):
        self.serve(PIN, "exit 3\n")
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
        # Fetched before the desktop starts, as the desktop's own user, by the desktop's image.
        init = controller["initContainers"]["dotfiles"]
        self.assertEqual(init["command"], ["/bin/sh", "/opt/dotfiles/dotfiles-bootstrap", "fetch"])
        self.assertEqual(init["image"], app["image"])
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
        for setting in ("platformAutomerge: false", 'automergeSchedule: ["* 3-5 * * *"]',
                        'schedule: ["* 0-1 * * *"]'):
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
            "kubernetes/apps/main/llm/hermes/app/skills-sync/sync.sh",
            "kubernetes/apps/main/llm/paseo/common/helmrelease.yaml",
            "kubernetes/components/dotfiles/dotfiles-bootstrap",
        ])
        self.assertIn("dotfiles.git?ref=${DOTFILES_REF}", users["kubernetes/apps/main/llm/paseo/common/helmrelease.yaml"])
        self.assertIn("ref=${DOTFILES_REF}", users["kubernetes/components/dotfiles/dotfiles-bootstrap"])
        job = (ROOT / "kubernetes/apps/main/llm/hermes/app/skills-sync/job.yaml").read_text()
        self.assertIn('value: "${DOTFILES_REF}"', job)
        for text in [*users.values(), job]:
            self.assertEqual(re.findall(r"\b[0-9a-f]{40}\b", text), [])


if __name__ == "__main__":
    unittest.main()
