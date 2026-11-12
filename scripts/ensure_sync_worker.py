"""Start the independent worker if needed, without a visible console."""
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    sys.path.insert(0, str(ROOT))
    from app.worker_runtime import read_worker_status

    instance = ROOT / "instance"
    if read_worker_status(instance)["healthy"]:
        return 0
    process = subprocess.Popen(
        [sys.executable, str(ROOT / "worker.py")], cwd=ROOT,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        start_new_session=os.name != "nt", stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if read_worker_status(instance)["healthy"]:
            return 0
        if process.poll() is not None:
            print("Worker did not start. Check logs/worker-error.log and stop any older dashboard scheduler.")
            return 1
        time.sleep(0.25)
    print("Worker is still starting. Check /api/v1/system/sync and logs/worker-app.log.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
