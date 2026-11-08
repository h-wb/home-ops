"""`hermes acp` behind Paseo: Paseo sends its own workspace path as each session's cwd, which
does not exist in this pod, and Hermes rejects it (invalid_params). Relay stdin line by line,
replacing every params.cwd with the Hermes workspace; stdout is Hermes's own, untouched.
"""

import json
import os
import signal
import subprocess
import sys

CWD = os.environ.get("HERMES_ACP_CWD", "/data/hermes/workspace")
os.makedirs(CWD, exist_ok=True)

hermes = subprocess.Popen(["/opt/hermes/bin/hermes", "acp"], stdin=subprocess.PIPE)
signal.signal(signal.SIGTERM, lambda *_: hermes.terminate())

for line in sys.stdin.buffer:
    try:
        message = json.loads(line)
    except ValueError:
        message = None
    params = message.get("params") if isinstance(message, dict) else None
    if isinstance(params, dict) and "cwd" in params:
        params["cwd"] = CWD
        line = json.dumps(message, separators=(",", ":")).encode() + b"\n"
    hermes.stdin.write(line)
    hermes.stdin.flush()

hermes.stdin.close()
sys.exit(hermes.wait())
