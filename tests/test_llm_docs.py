"""The assistant documents' drawings follow their Mermaid text.

Run with python3 -B -m unittest discover -s tests -p test_llm_docs.py.
"""
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Drawings(unittest.TestCase):
    def test_committed_drawings_are_current(self):
        # Fails when a flow or a connection changed in the text but build.py was not run.
        result = subprocess.run([sys.executable, "-B", "kubernetes/apps/main/llm/docs/build.py", "--check"],
                                cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)


if __name__ == "__main__":
    unittest.main()
