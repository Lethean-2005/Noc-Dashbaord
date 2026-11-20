"""Start the current worker, gracefully handing off from an older project folder."""
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def start_worker(read_worker_status):
    from app.services.worker_handoff import is_launched_worker

    instance = ROOT / 'instance'
    log = ROOT / 'logs' / 'worker-startup.log'
    log.parent.mkdir(exist_ok=True)
    if log.exists() and log.stat().st_size > 1048576:
        log.write_bytes(b'')
    with log.open('ab') as errors:
        process = subprocess.Popen(
            [sys.executable, str(ROOT / 'worker.py')], cwd=ROOT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            start_new_session=os.name != 'nt', stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=errors,
        )
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        status = read_worker_status(instance)
        if status.get('healthy') and is_launched_worker(status.get('pid'), process.pid):
            print('Sync worker is running for this project.')
            return 0
        if process.poll() is not None:
            print('Worker exited with code ' + str(process.returncode) + '. Check ' + str(log) + ' and logs/worker-error.log.')
            tail = log.read_text(encoding='utf-8', errors='replace')[-2000:].strip()
            if tail:
                print(tail)
            return 1
        time.sleep(0.25)
    print('Worker is still starting. Check /api/v1/system/sync and logs/worker-app.log before retrying.')
    return 1


def main():
    sys.path.insert(0, str(ROOT))
    from app.worker_runtime import read_worker_status
    from app.services.worker_handoff import WorkerHandoffError, prepare_worker_start, worker_startup_lock

    print('Checking sync worker...', flush=True)
    try:
        with worker_startup_lock():
            if prepare_worker_start(ROOT):
                return 0
            return start_worker(read_worker_status)
    except (WorkerHandoffError, OSError) as error:
        print('Worker startup could not continue: ' + str(error))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
