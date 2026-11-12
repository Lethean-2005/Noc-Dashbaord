"""Single worker ownership, heartbeat and graceful shutdown."""
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.background import start_worker_jobs
from app.services.leader_lock import is_leader, release_leadership
from app.utils.logger import get_logger

logger = get_logger(__name__)
STATUS_NAME = "sync-worker-status.json"
STOP_NAME = "sync-worker-stop.json"
_active_runtime = None
_runtime_lock = threading.Lock()


class WorkerAlreadyRunning(RuntimeError):
    """Another worker or an older embedded scheduler owns the machine lock."""


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def read_worker_status(instance_path):
    """Read a small status file; never query source systems or trigger jobs."""
    try:
        value = json.loads((Path(instance_path) / STATUS_NAME).read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("Invalid worker status")
        jobs = value.get("jobs", {})
        if not isinstance(jobs, dict) or any(not isinstance(job, dict) for job in jobs.values()):
            raise ValueError("Invalid job status")
        updated = datetime.fromisoformat(value["heartbeat_at"])
        age = (datetime.now(timezone.utc) - updated).total_seconds()
    except (OSError, ValueError, KeyError, TypeError):
        return {"state": "unavailable", "healthy": False, "jobs": {}}
    value["heartbeat_age_seconds"] = round(max(0, age), 1)
    value["healthy"] = (value.get("state") == "running" and 0 <= age <= 60
                        and bool(jobs) and all(job.get("thread_alive", False) for job in jobs.values()))
    value["has_job_errors"] = any(job.get("last_error") for job in jobs.values())
    return value


def request_worker_stop(instance_path):
    """Target the current worker session so an old request cannot stop a restart."""
    status = read_worker_status(instance_path)
    if status.get("state") == "stopped":
        return True
    if status.get("state") not in {"running", "starting", "stopping"} or status.get("heartbeat_age_seconds", 999) > 60:
        return False
    target = Path(instance_path) / STOP_NAME
    temporary = target.with_name(f"{STOP_NAME}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps({key: status[key] for key in ("pid", "started_at")}), encoding="utf-8")
    os.replace(temporary, target)
    return True


class WorkerRuntime:
    def __init__(self, app):
        self.app = app
        self.stop_event = threading.Event()
        self.jobs = {}
        self.jobs_lock = threading.Lock()
        self.owned = False
        self.started_at = utc_now()
        self.state = "starting"
        app.extensions["sync_worker"] = self
        app.extensions["scheduler_stop_event"] = self.stop_event

    def acquire(self):
        global _active_runtime
        with _runtime_lock:
            if _active_runtime is not None or not is_leader():
                raise WorkerAlreadyRunning(
                    "Another sync worker or older dashboard scheduler is running. "
                    "Stop the old scheduler before starting this worker."
                )
            _active_runtime = self
            self.owned = True

    def start(self):
        if not self.owned:
            raise RuntimeError("Worker must own the scheduler lock before starting jobs")
        self.write_status()
        start_worker_jobs(self.app)
        self.state = "running"
        self.write_status()
        logger.info("Dedicated sync worker started; web processes do not run scheduled jobs")

    def register_job(self, name, interval_seconds):
        with self.jobs_lock:
            self.jobs[name] = {"interval_seconds": interval_seconds, "state": "waiting"}

    def record_job(self, name, **changes):
        with self.jobs_lock:
            self.jobs[name].update(changes)

    def write_status(self):
        threads = {thread.name: thread.is_alive() for thread in self.app.extensions.get("scheduler_threads", [])}
        with self.jobs_lock:
            jobs = {name: {**value, "thread_alive": threads.get(name, False)}
                    for name, value in self.jobs.items()}
        status = {"pid": os.getpid(), "state": self.state, "started_at": self.started_at,
                  "heartbeat_at": utc_now(), "timezone": self.app.config["TIMEZONE"], "jobs": jobs}
        target = Path(self.app.instance_path) / STATUS_NAME
        temporary = target.with_name(f"{STATUS_NAME}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(status), encoding="utf-8")
        os.replace(temporary, target)

    def check_stop_request(self):
        try:
            request = json.loads((Path(self.app.instance_path) / STOP_NAME).read_text(encoding="utf-8"))
            if request.get("pid") == os.getpid() and request.get("started_at") == self.started_at:
                self.request_stop()
        except (OSError, ValueError, AttributeError):
            pass

    def request_stop(self):
        self.state = "stopping"
        self.stop_event.set()

    def shutdown(self, timeout=30):
        """Wait for in-flight jobs before relinquishing leadership."""
        from app.services.scheduler_utils import join_scheduler_threads

        self.request_stop()
        self.write_status()
        if not join_scheduler_threads(self.app, timeout):
            return False
        self.state = "stopped"
        self.write_status()
        global _active_runtime
        with _runtime_lock:
            if self.owned:
                release_leadership()
                self.owned = False
                _active_runtime = None
        return True

    def abort_startup(self):
        # Do not release the lock while a partially started job can still run.
        self.request_stop()
        while not self.shutdown():
            logger.warning("Waiting for background work to stop after startup failure")
