"""Centralized application logger configuration.

Every module gets its logger via get_logger(__name__). Each logger writes
to the console and the following files, all the same timestamp/label/
job-name/message table shape (console adds a color per label on top):
  - stdout                      — for `python run.py` / console viewing
  - LOG_PATH   (logs/app.log)   — every record at LOG_LEVEL or above
  - LOG_ERROR_PATH (logs/error.log) — ERROR/CRITICAL only, so failures are
    easy to find without grepping the full app log
  - ATTEMPTS_LOG_PATH (logs/attempts.log) — only postgres_sync_utils.py's
    retry_fetch() records (ATTEMPT warnings + the FAILED-after-exhaustion
    that follows), so a retry storm on any job (e.g. ape_alarm's "conflict
    with recovery") is readable on its own, without needing to grep it out
    of every other job's noise in app.log
  - DASHBOARD_LOG_PATH (logs/dashboard.log) — only app/routes/dashboard.py's
    own logger, showing the last_synced_at of every table the homepage
    reads on each view (see dashboard.py's index()), so "how current was
    the data a user actually saw" is answered directly instead of having
    to cross-reference sync_meta against request timing by hand
  - TELEGRAM_LOG_PATH (logs/telegram.log) — only
    app/services/telegram/telegram_alert.py's own logger, so the Site Down
    Telegram alert's history (sent/skipped/failed) is readable on its own
    instead of buried in app.log's general noise
  - WEBHOOK_LOG_PATH (logs/webhook.log) — only webhook/__init__.py's own
    logger, same reasoning as TELEGRAM_LOG_PATH but for the Teams webhook
    alerts (webhook/ package)

Both live output (console, for whoever's watching `python run.py` run) and
persisted output (the files, the actual source of truth once the terminal
closes or nobody was watching) — keeping only one of the two is a real
tradeoff either way, not a strictly "more correct" choice, so this keeps
both rather than picking one.

Reads LOG_LEVEL/LOG_PATH/LOG_ERROR_PATH/ATTEMPTS_LOG_PATH/DASHBOARD_LOG_PATH
straight from the environment (matching app/config.py's defaults) rather
than Flask's app.config, since loggers are created as module-level
singletons at import time, often before any Flask app exists.

Each file rotates at LOG_MAX_BYTES (default 10MB), keeping LOG_BACKUP_COUNT
(default 5) old copies (app.log.1, app.log.2, ...) — without this, these
files grow without bound.

Under pytest, all paths redirect into a temp directory instead of logs/ —
retry_fetch() is exercised directly by tests using a fake label ("test"),
and without this redirect every test run permanently wrote that noise into
the real logs/app.log/attempts.log on this machine. Detected via "pytest"
in sys.modules rather than the PYTEST_CURRENT_TEST env var:
PYTEST_CURRENT_TEST is only set while a test is actually executing, but
this module (like most) gets imported once at collection time, before any
test has started — by then PYTEST_CURRENT_TEST wouldn't be set yet, and
this is a one-time check, so it would never fall back to the redirect.
"pytest" is already imported by the time collection starts, so it's set
for this whole process's lifetime instead.
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
else:
    _LOG_PATH = os.environ.get("LOG_PATH", "logs/app.log")
    _LOG_ERROR_PATH = os.environ.get("LOG_ERROR_PATH", "logs/error.log")
    _ATTEMPTS_LOG_PATH = os.environ.get("ATTEMPTS_LOG_PATH", "logs/attempts.log")
    _DASHBOARD_LOG_PATH = os.environ.get("DASHBOARD_LOG_PATH", "logs/dashboard.log")
    _TELEGRAM_LOG_PATH = os.environ.get("TELEGRAM_LOG_PATH", "logs/telegram.log")
    _WEBHOOK_LOG_PATH = os.environ.get("WEBHOOK_LOG_PATH", "logs/webhook.log")

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
    still using cp1252 (the Windows default outside UTF-8-aware terminals
    like Windows Terminal/VS Code).

    Reconfigures colorama's already-patched sys.stdout in place (rather
    than wrapping the raw sys.stdout.buffer in a new TextIOWrapper), so
    ANSI color codes still pass through colorama's translation layer for
    legacy Windows consoles (cmd.exe) — wrapping the raw buffer instead
    would bypass that wrapper entirely and print raw escape codes there.
    Falls back to the raw buffer only if reconfigure() isn't available
    (older Python, or a stdout that isn't a real TextIOWrapper, e.g. some
    IDE consoles)."""
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


class _SafeRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """Rotation (rename app.log -> app.log.1) fails with PermissionError on
    Windows whenever another process still has the file open — which is
    routine here, since this machine's host-level process duplication
    (see leader_lock.py's own docstring) means several python.exe
    processes are often writing to the same logs/app.log at once. Renaming
    an open file is fine on Unix but Windows refuses it outright, so
    rollover just isn't reliably possible while that's happening. Skipping
    a failed rollover (instead of the default behavior of printing a full
    traceback to stderr on every write once the file's past maxBytes)
    means the file keeps growing a bit past LOG_MAX_BYTES during that
    window, but that's a far smaller cost than a traceback spamming the
    console on every single log call."""

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
        logger.setLevel(_LOG_LEVEL)
    return logger
