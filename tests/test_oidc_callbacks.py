"""kanidm-provision deep-merges a ConfigMap's *.json files in key order and replaces
lists, so every redirect address has to be in state.json's one originUrl list.

Run with python3 -B -m unittest discover -s tests -p test_oidc_callbacks.py.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
CONFIGMAP = ROOT / "kubernetes/components/oidc/base/kanidm/configmap.yaml"


class ExtraCallbacks(unittest.TestCase):
    def test_extra_callbacks_join_the_main_list(self):
        text = CONFIGMAP.read_text()
        state, extra = text.split("  state.json: |", 1)[1], text.split("  extra.json: |", 1)[1].split("  custom.json:", 1)[0]
        self.assertIn('${CALLBACK}"${EXTRA_CALLBACKS:=}]', state)
        self.assertNotIn("originUrl", extra)

    def test_every_app_writes_a_comma_led_list(self):
        for path in (ROOT / "kubernetes/apps").rglob("ks.yaml"):
            for value in re.findall(r"^\s+OIDC_EXTRA_CALLBACKS: '(.*)'$", path.read_text(), re.M):
                self.assertRegex(value, r'^(, "https://[^"]+")+$', path)


if __name__ == "__main__":
    unittest.main()
