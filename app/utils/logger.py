"""Centralized application logger configuration.

Every module gets its logger via get_logger(__name__). Each logger writes
to the console (colored per label) plus its own file: LOG_PATH for
everything at LOG_LEVEL+, LOG_ERROR_PATH for ERROR/CRITICAL only,
ATTEMPTS_LOG_PATH for retry_fetch()'s own ATTEMPT/SUCCESS/FAILED records,
DASHBOARD_LOG_PATH for dashboard.py's per-table last_synced_at,
TELEGRAM_LOG_PATH/WEBHOOK_LOG_PATH for their own alert modules, and
REQUEST_LOG_PATH for app/__init__.py's per-request timing hook (method,
path, status, duration, remote address — one line per HTTP request) —
each kept separate so one job's history is readable without grepping it
out of app.log's general noise.

Reads *_PATH straight from the environment rather than Flask's
app.config, since loggers are module-level singletons created at import
time, often before any Flask app exists. Each file rotates at
LOG_MAX_BYTES (default 10MB), keeping LOG_BACKUP_COUNT (default 5) old
copies.

Under pytest, all paths redirect into a temp directory instead of logs/
— detected via "pytest" in sys.modules rather than PYTEST_CURRENT_TEST,
since this module is imported once at collection time, before that
would be set for any specific test.
"""

import logging
import logging.handlers
import os
import sys
import tempfile

import colorama

# Enables ANSI color codes on legacy Windows consoles (cmd.exe) by patching
# sys.stdout with a translating wrapper; a no-op on terminals that already
# support ANSI (Windows Terminal, VS Code, Linux/Mac).
colorama.init()

_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
_LOG_MAX_BYTES = int(os.environ.get("LOG_MAX_BYTES", 10 * 1024 * 1024))
_LOG_BACKUP_COUNT = int(os.environ.get("LOG_BACKUP_COUNT", 5))

if "pytest" in sys.modules:
    _log_dir = os.path.join(tempfile.gettempdir(), "noc-dashboard-test-logs")
    _LOG_PATH = os.path.join(_log_dir, "app.log")
    _LOG_ERROR_PATH = os.path.join(_log_dir, "error.log")
    _ATTEMPTS_LOG_PATH = os.path.join(_log_dir, "attempts.log")
    _DASHBOARD_LOG_PATH = os.path.join(_log_dir, "dashboard.log")
    _TELEGRAM_LOG_PATH = os.path.join(_log_dir, "telegram.log")
    _WEBHOOK_LOG_PATH = os.path.join(_log_dir, "webhook.log")
    _REQUEST_LOG_PATH = os.path.join(_log_dir, "requests.log")
else:
    _LOG_PATH = os.environ.get("LOG_PATH", "logs/app.log")
    _LOG_ERROR_PATH = os.environ.get("LOG_ERROR_PATH", "logs/error.log")
    _ATTEMPTS_LOG_PATH = os.environ.get("ATTEMPTS_LOG_PATH", "logs/attempts.log")
    _DASHBOARD_LOG_PATH = os.environ.get("DASHBOARD_LOG_PATH", "logs/dashboard.log")
    _TELEGRAM_LOG_PATH = os.environ.get("TELEGRAM_LOG_PATH", "logs/telegram.log")
    _WEBHOOK_LOG_PATH = os.environ.get("WEBHOOK_LOG_PATH", "logs/webhook.log")
    _REQUEST_LOG_PATH = os.environ.get("REQUEST_LOG_PATH", "logs/requests.log")

_RESET = colorama.Style.RESET_ALL

# ANSI color per displayed label — used only by the console handler below.
_LABEL_COLOR = {
    "INFO": colorama.Fore.GREEN,
    "START": colorama.Fore.BLUE,
    "COMPLETED": colorama.Fore.GREEN,
    "ATTEMPT": colorama.Fore.YELLOW,
    "SUCCESS": colorama.Fore.GREEN,
    "FAILED": colorama.Fore.RED,
    "TOTAL": colorama.Fore.MAGENTA,
    "DATA": colorama.Fore.GREEN,
    "DEBUG": colorama.Fore.CYAN,
    "WARNING": colorama.Fore.YELLOW,
    "ERROR": colorama.Fore.RED,
    "CRITICAL": colorama.Style.BRIGHT + colorama.Fore.RED,
}

_LABEL_WIDTH = 10
_JOB_WIDTH = 30

# scheduler_utils.py logs one of these plain markers at the start of every
# background sync cycle ("START"), one at the end ("COMPLETED (X.XXs)" /
# "FAILED (X.XXs): ..."), and one when work() returns a row count
# ("Total: synced N row(s) in X.XXs") — each rendered here as its own
# LABEL/color instead of the raw INFO/ERROR Python log level, so a quick
# glance at logs/app.log (or the console) reads like a table of job
# lifecycle events rather than a wall of identical "INFO" lines.
#
# postgres_sync_utils.py's retry_fetch() (shared by ape_alarm/site_lookup/
# incident/etc.) logs its own three message shapes on top of that: a
# "Postgres {label} sync attempt N/M failed, retrying in Xs: ..." WARNING
# per retry, a "Postgres {label} sync succeeded on attempt N/M, got R
# row(s) in X.XXs" INFO once the fetch lands (whether on the first try or
# after some retries), and a "Postgres {label} sync failed after M
# attempts: ..." ERROR if every attempt is exhausted — mapped to
# ATTEMPT/SUCCESS/FAILED here so a retry storm (e.g. ape_alarm's "conflict
# with recovery" against object_138), and how it resolved, is just as easy
# to spot as a job's own lifecycle events. app/routes/dashboard.py's own
# "Dashboard data as of: ..." line maps to DATA the same way.
_ALL_TASKS_THREAD_NAME = "all-tasks-summary"  # must match all_tasks_scheduler.py's thread_name
_DASHBOARD_LOGGER_NAME = "app.routes.dashboard"  # must match dashboard.py's get_logger(__name__)
_TELEGRAM_LOGGER_NAME = (
    "app.services.telegram.telegram_alert"  # must match telegram_alert.py's get_logger(__name__)
)
_WEBHOOK_LOGGER_NAME = "webhook"  # must match webhook/__init__.py's get_logger(__name__)
_REQUEST_LOGGER_NAME = "app.request_timing"  # must match the name passed to get_logger() in app/__init__.py's request-timing hook


def _is_retry_record(message):
    """True for all three of retry_fetch()'s own message shapes — a
    per-attempt warning, its eventual success, and the failed-after-
    exhaustion error that can follow instead."""
    return message.startswith("Postgres ") and (
        " sync attempt " in message
        or " sync succeeded on " in message
        or " sync failed after " in message
    )


def _label_for(record, message):
    if message == "START":
        return "START"
    if message.startswith("COMPLETED"):
        return "COMPLETED"
    if message.startswith("FAILED"):
        return "FAILED"
    if message.startswith("Total:"):
        return "TOTAL"
    if message.startswith("Dashboard data as of:"):
        return "DATA"
    if _is_retry_record(message):
        if " sync failed after " in message:
            return "FAILED"
        if " sync succeeded on " in message:
            return "SUCCESS"
        return "ATTEMPT"
    return record.levelname


def _job_name_for(record, message):
    """The all-tasks-summary job's own Total line displays as "Total all
    sync" instead of its real thread name — everything else (including
    that same job's own START/COMPLETED lines) shows the real thread name,
    matching every other job. The dashboard route's own log line displays
    as "dashboard" instead of Flask's internal per-request thread name
    (e.g. "Thread-3"), which would otherwise be a different, meaningless
    value on every single page view."""
    if record.threadName == _ALL_TASKS_THREAD_NAME and message.startswith("Total:"):
        return "Total all sync"
    if record.name == _DASHBOARD_LOGGER_NAME:
        return "dashboard"
    if record.name == _REQUEST_LOGGER_NAME:
        return "request"
    return record.threadName


class _BaseTableFormatter(logging.Formatter):
    """Shared timestamp/label/job-name/message table layout. Subclasses
    just decide whether to colorize the label (console) or not (file)."""

    def _format_parts(self, record):
        message = record.getMessage()
        label = _label_for(record, message)
        job_name = _job_name_for(record, message)
        timestamp = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        return timestamp, label, job_name, message


class _PlainTableFormatter(_BaseTableFormatter):
    """Plain-text file formatter — same table shape as the console, no
    ANSI color codes."""

    def format(self, record):
        timestamp, label, job_name, message = self._format_parts(record)
        text = f"{timestamp} {label:<{_LABEL_WIDTH}} {job_name:<{_JOB_WIDTH}} {message}"
        if record.exc_info:
            text += "\n" + self.formatException(record.exc_info)
        return text


class _ConsoleFormatter(_BaseTableFormatter):
    """Console formatter: same table shape as the plain-text file logs,
    plus a color per label for a quick glance while `python run.py` is
    running."""

    def format(self, record):
        timestamp, label, job_name, message = self._format_parts(record)
        color = _LABEL_COLOR.get(label, "")
        text = (
            f"{timestamp} {color}{label:<{_LABEL_WIDTH}}{_RESET} {job_name:<{_JOB_WIDTH}} {message}"
        )
        if record.exc_info:
            text += "\n" + self.formatException(record.exc_info)
        return text


_FORMATTER = _PlainTableFormatter()
_CONSOLE_FORMATTER = _ConsoleFormatter()


def _console_stream():
    """UTF-8 with errors='replace', regardless of the console's actual
    codepage — without this, any non-ASCII character in a log message
    raises UnicodeEncodeError and crashes the app on a Windows console
    still using cp1252.

    Reconfigures colorama's already-patched sys.stdout in place (rather
    than wrapping the raw sys.stdout.buffer in a new TextIOWrapper), so
    ANSI color codes still pass through colorama's translation layer for
    legacy Windows consoles (cmd.exe) — wrapping the raw buffer instead
    would bypass that and print raw escape codes there. Falls back to the
    raw buffer only if reconfigure() isn't available (older Python, or a
    non-TextIOWrapper stdout, e.g. some IDE consoles)."""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        return sys.stdout
    except AttributeError:
        if hasattr(sys.stdout, "buffer"):
            import io

            return io.TextIOWrapper(
                sys.stdout.buffer, encoding="utf-8", errors="replace", newline="\n"
            )
        return sys.stdout


def _is_retry_record_filter(record):
    return _is_retry_record(record.getMessage())


def _dashboard_only_filter(record):
    return record.name == _DASHBOARD_LOGGER_NAME


def _telegram_only_filter(record):
    return record.name == _TELEGRAM_LOGGER_NAME


def _webhook_only_filter(record):
    return record.name == _WEBHOOK_LOGGER_NAME


def _request_only_filter(record):
    return record.name == _REQUEST_LOGGER_NAME


class _SafeRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """Rotation (rename app.log -> app.log.1) fails with PermissionError on
    Windows whenever another process still has the file open — routine
    here, since this machine's host-level process duplication (see
    leader_lock.py) means several python.exe processes often write to the
    same logs/app.log at once, and Windows refuses to rename an open file.
    Skipping a failed rollover (instead of the default traceback-on-every-
    write-past-maxBytes) lets the file grow a bit past LOG_MAX_BYTES
    during that window, a far smaller cost than spamming the console."""

    def doRollover(self):
        try:
            super().doRollover()
        except PermissionError:
            pass


def _file_handler(path, level=logging.NOTSET, record_filter=None):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    handler = _SafeRotatingFileHandler(
        path, maxBytes=_LOG_MAX_BYTES, backupCount=_LOG_BACKUP_COUNT, encoding="utf-8"
    )
    handler.setLevel(level)
    handler.setFormatter(_FORMATTER)
    if record_filter is not None:
        handler.addFilter(record_filter)
    return handler


def get_logger(name):
    logger = logging.getLogger(name)
    if not logger.handlers:
        console = logging.StreamHandler(_console_stream())
        console.setFormatter(_CONSOLE_FORMATTER)
        logger.addHandler(console)
        logger.addHandler(_file_handler(_LOG_PATH))
        logger.addHandler(_file_handler(_LOG_ERROR_PATH, level=logging.ERROR))
        logger.addHandler(_file_handler(_ATTEMPTS_LOG_PATH, record_filter=_is_retry_record_filter))
        logger.addHandler(_file_handler(_DASHBOARD_LOG_PATH, record_filter=_dashboard_only_filter))
        logger.addHandler(_file_handler(_TELEGRAM_LOG_PATH, record_filter=_telegram_only_filter))
        logger.addHandler(_file_handler(_WEBHOOK_LOG_PATH, record_filter=_webhook_only_filter))
        logger.addHandler(_file_handler(_REQUEST_LOG_PATH, record_filter=_request_only_filter))
        logger.setLevel(_LOG_LEVEL)
    return logger
