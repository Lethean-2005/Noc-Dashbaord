"""Dedicated sync/alert process. Run from the same project as run.py."""
import argparse
import json
import os
import signal
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--check", action="store_true", help="Validate schedules without syncing or sending")
    actions.add_argument("--status", action="store_true", help="Read the latest heartbeat without starting jobs")
    actions.add_argument("--stop", action="store_true", help="Request graceful stop of the current worker")
    parser.add_argument("--instance-path", type=Path, help="Override the shared cache directory")
    args = parser.parse_args(argv)

    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    # Keep all worker file handles separate from web log rotation on Windows.
    defaults = {"LOG_PATH": "app.log", "LOG_ERROR_PATH": "error.log", "ATTEMPTS_LOG_PATH": "attempts.log",
                "DASHBOARD_LOG_PATH": "dashboard.log", "TELEGRAM_LOG_PATH": "telegram.log",
                "WEBHOOK_LOG_PATH": "webhook.log", "REQUEST_LOG_PATH": "requests.log"}
    for key, name in defaults.items():
        configured = Path(os.environ.get(key, str(Path("logs") / name)))
        worker_path = configured.with_name("worker-" + configured.name)
        os.environ[key] = os.environ.get("WORKER_" + key, str(worker_path))
    from app import create_app
    from app.background import _validate_scheduler_offsets, configured_jobs
    from app.config import config_map
    from app.worker_runtime import WorkerAlreadyRunning, read_worker_status, request_worker_stop
    from app.utils.logger import get_logger

    instance_path = str(args.instance_path.resolve()) if args.instance_path else str(ROOT / "instance")
    if args.stop:
        if not request_worker_stop(instance_path):
            print("No current worker heartbeat found. No stop request was sent.")
            return 1
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if read_worker_status(instance_path).get("state") == "stopped":
                print("Sync worker stopped. Saved data and alert history were preserved.")
                return 0
            time.sleep(0.25)
        print("Stop requested; waiting for in-flight work. Check worker.py --status before updating files.")
        return 1
    if args.status:
        status = read_worker_status(instance_path)
        print(json.dumps(status, indent=2))
        return 0 if status["healthy"] else 1
    if args.check:
        config = config_map[os.environ.get("APP_ENV", "default")]
        _validate_scheduler_offsets()
        values = {name: getattr(config, name) for name in dir(config) if name.isupper()}
        jobs = configured_jobs(values)
        for _, key in jobs:
            if values[key] <= 0:
                raise ValueError(f"{key} must be positive")
        print(json.dumps({"timezone": values["TIMEZONE"], "jobs": [
            {"module": module, "interval_seconds": values[key]} for module, key in jobs
        ]}, indent=2))
        return 0

    logger = get_logger(__name__)
    try:
        app = create_app(instance_path=instance_path, process_role="worker")
    except WorkerAlreadyRunning as error:
        logger.warning(str(error))
        return 2
    except Exception:
        logger.exception("Worker startup failed")
        return 1
    runtime = app.extensions.get("sync_worker")
    if runtime is None:
        logger.error("Worker jobs are disabled in testing configuration")
        return 1

    def stop(signum, frame):
        runtime.request_stop()

    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), stop)
    try:
        next_heartbeat = time.monotonic() + 15
        while not runtime.stop_event.wait(1):
            runtime.check_stop_request()
            if runtime.stop_event.is_set():
                break
            if time.monotonic() >= next_heartbeat:
                runtime.write_status()
                next_heartbeat = time.monotonic() + 15
            if any(not thread.is_alive() for thread in app.extensions.get("scheduler_threads", [])):
                raise RuntimeError("A scheduler thread stopped unexpectedly")
    except Exception:
        logger.exception("Worker stopped after a runtime error")
        return_code = 1
    else:
        return_code = 0
    finally:
        while not runtime.shutdown():
            logger.warning("Waiting for in-flight sync/alert work before worker shutdown")
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
