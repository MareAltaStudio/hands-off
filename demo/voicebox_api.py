"""Talk to a local Voicebox (jamiepine/voicebox) backend: start it if needed and list its routes.

    uv run --no-project --with requests python voicebox_api.py routes
"""

import os
import subprocess
import sys
import time

import requests

BASE = "http://127.0.0.1:17493"
DATA = os.path.join(os.environ["APPDATA"], "sh.voicebox.app")
BACKEND = os.path.join(DATA, "backends", "cuda", "voicebox-server-cuda.exe")


def alive() -> bool:
    try:
        return requests.get(f"{BASE}/health", timeout=3).status_code < 400
    except requests.RequestException:
        return False


def ensure() -> None:
    if alive():
        return
    subprocess.Popen([BACKEND, "--data-dir", DATA, "--port", "17493"], stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)
    for _ in range(90):
        time.sleep(1)
        if alive():
            # without this the backend's own watchdog stops it, since its parent isn't the app
            requests.post(f"{BASE}/watchdog/disable", timeout=5)
            return
    raise SystemExit("Voicebox did not answer in 90 s")


if __name__ == "__main__":
    ensure()
    if sys.argv[1:] == ["routes"]:
        spec = requests.get(f"{BASE}/openapi.json", timeout=10).json()
        for path, ops in spec["paths"].items():
            print(path, ",".join(ops))
