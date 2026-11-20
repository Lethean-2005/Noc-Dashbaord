"""Graceful Windows worker handoff between dashboard project folders."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shlex
import socket
import subprocess
import time

from app.services.leader_lock import _LOCK_PORT
from app.worker_runtime import read_worker_status, request_worker_stop

HANDOFF_TIMEOUT = 90
STATUS_TIMEOUT = 30
STARTUP_MUTEX_NAME = "Global\\NocDashboardWorkerStartup"


class WorkerHandoffError(RuntimeError):
    pass


@contextmanager
def worker_startup_lock():
    """Serialize launchers across project folders; Windows releases abandoned locks."""
    if os.name != 'nt':
        yield
        return
    import ctypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    kernel.WaitForSingleObject.restype = ctypes.c_ulong
    kernel.ReleaseMutex.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.CreateMutexW(None, False, STARTUP_MUTEX_NAME)
    if not handle:
        raise WorkerHandoffError('Cannot acquire the dashboard startup lock.')
    acquired = False
    try:
        acquired = kernel.WaitForSingleObject(handle, 180000) in (0, 128)
        if not acquired:
            raise WorkerHandoffError('Another dashboard startup is still in progress. Try again shortly.')
        yield
    finally:
        if acquired:
            kernel.ReleaseMutex(handle)
        kernel.CloseHandle(handle)


def port_is_available():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            probe.bind(('127.0.0.1', _LOCK_PORT))
            return True
        except OSError:
            return False


def read_lock_owner():
    if os.name != 'nt':
        raise WorkerHandoffError('Automatic cross-folder worker handoff is supported on Windows. Stop the old worker first.')
    script = """$ErrorActionPreference='Stop';
$c=Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort __PORT__ -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1;
if($c){Get-CimInstance Win32_Process -Filter ('ProcessId='+$c.OwningProcess) | Select-Object ProcessId,CommandLine,ExecutablePath | ConvertTo-Json -Compress}
""".replace('__PORT__', str(_LOCK_PORT))
    try:
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                                capture_output=True, text=True, timeout=15,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode or not result.stdout.strip():
            raise ValueError('Owner unavailable')
        raw = json.loads(result.stdout)
        return {'pid': int(raw['ProcessId']), 'command_line': raw.get('CommandLine') or ''}
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError) as error:
        raise WorkerHandoffError('Cannot identify the scheduler lock owner. No process was stopped.') from error


def worker_location(owner):
    """Accept an absolute dashboard Python script, never a substring match."""
    try:
        args = shlex.split(owner['command_line'], posix=False)
    except ValueError as error:
        raise WorkerHandoffError('Cannot read the old worker command. No process was stopped.') from error
    args = [arg.strip('"') for arg in args]
    if len(args) < 2 or not Path(args[0]).name.lower().startswith('python'):
        raise WorkerHandoffError('The scheduler port belongs to an unrecognized process. It was left running.')
    script_arg = None
    for arg in args[1:]:
        if arg in ('-c', '-m'):
            break
        if not arg.startswith('-'):
            script_arg = arg
            break
    script = Path(script_arg or '')
    if not script.is_absolute() or script.name.lower() not in ('worker.py', 'run.py'):
        raise WorkerHandoffError('Cannot identify an absolute dashboard worker path. No process was stopped.')
    root = script.parent.resolve()
    if not script.is_file() or not (root / 'app' / '__init__.py').is_file():
        raise WorkerHandoffError('The lock owner is not a verified dashboard project. It was left running.')
    if script.name.lower() == 'run.py':
        raise WorkerHandoffError('An older embedded scheduler is running in ' + str(root) + '. Close that old dashboard first.')
    if not (root / 'app' / 'worker_runtime.py').is_file():
        raise WorkerHandoffError('The old worker does not support graceful handoff. Stop it manually first.')
    instance = root / 'instance'
    for index, arg in enumerate(args):
        if arg == '--instance-path' and index + 1 < len(args):
            instance = Path(args[index + 1])
        elif arg.startswith('--instance-path='):
            instance = Path(arg.split('=', 1)[1])
    if not instance.is_absolute():
        raise WorkerHandoffError('The old worker uses a relative custom instance path. Stop it manually first.')
    return root, instance.resolve()


def matching_status(instance, pid):
    deadline = time.monotonic() + STATUS_TIMEOUT
    while True:
        status = read_worker_status(instance)
        if status.get('pid') == pid and status.get('heartbeat_age_seconds', 999) <= 60:
            return status
        if port_is_available():
            return None
        if time.monotonic() >= deadline:
            raise WorkerHandoffError('The old worker heartbeat is missing, stale or belongs to another process. No stop request was sent.')
        time.sleep(0.5)


def prepare_worker_start(project_root):
    """Return True to reuse a healthy current worker, False when a new one can start."""
    if port_is_available():
        return False
    owner = read_lock_owner()
    old_root, instance = worker_location(owner)
    status = matching_status(instance, owner['pid'])
    if status is None or port_is_available():
        return False
    if old_root == Path(project_root).resolve() and status.get('healthy'):
        print('Current sync worker is healthy; reusing it.')
        return True
    print('Stopping previous sync worker in ' + str(old_root) + ' ...', flush=True)
    if not request_worker_stop(instance):
        raise WorkerHandoffError('Cannot request a graceful stop of the old worker. No new worker was started.')
    print('Waiting for in-progress sync and alert jobs to finish...', flush=True)
    deadline = time.monotonic() + HANDOFF_TIMEOUT
    while not port_is_available():
        if time.monotonic() >= deadline:
            raise WorkerHandoffError('The old worker is still finishing work. Retry later; no force-stop was performed.')
        time.sleep(0.5)
    print('Previous worker stopped. Starting the worker for this project.', flush=True)
    return False


def is_launched_worker(worker_pid, launcher_pid):
    """Recognize the actual Python child behind a Windows venv launcher."""
    try:
        worker_pid, launcher_pid = int(worker_pid), int(launcher_pid)
    except (ValueError, TypeError):
        return False
    if worker_pid == launcher_pid:
        return True
    if os.name != 'nt' or min(worker_pid, launcher_pid) <= 0:
        return False
    script = """$candidate=__WORKER__; $expected=__LAUNCHER__; $matched=$false;
for($i=0;$i -lt 8 -and $candidate -gt 0;$i++){
 if($candidate -eq $expected){$matched=$true;break}
 $process=Get-CimInstance Win32_Process -Filter ('ProcessId='+$candidate) -ErrorAction SilentlyContinue;
 if(-not $process){break}; $candidate=$process.ParentProcessId
}; if($matched){'true'}else{'false'}
""".replace('__WORKER__', str(worker_pid)).replace('__LAUNCHER__', str(launcher_pid))
    try:
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                                capture_output=True, text=True, timeout=15,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        return result.returncode == 0 and result.stdout.strip().lower() == 'true'
    except (OSError, subprocess.TimeoutExpired):
        return False


def stop_current_worker(project_root):
    """Stop this project's worker after web shutdown; leave other folders alone."""
    try:
        with worker_startup_lock():
            if port_is_available():
                print('Sync worker is already stopped.')
                return True
            owner = read_lock_owner()
            root, instance = worker_location(owner)
            if root != Path(project_root).resolve():
                print('Another project owns the worker; leaving it running.')
                return True
            if matching_status(instance, owner['pid']) is None:
                return True
            print('Stopping the sync worker; waiting for in-progress jobs...', flush=True)
            if not request_worker_stop(instance):
                raise WorkerHandoffError('Cannot request shutdown. Keep the old folder until the worker stops.')
            deadline = time.monotonic() + HANDOFF_TIMEOUT
            while not port_is_available():
                if time.monotonic() >= deadline:
                    raise WorkerHandoffError('Worker is still finishing work. Do not delete the old folder yet; check worker.py --status.')
                time.sleep(0.5)
            print('Dashboard and sync worker are now stopped.', flush=True)
            return True
    except (WorkerHandoffError, OSError) as error:
        print('Worker shutdown: ' + str(error))
        return False
