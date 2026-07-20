"""Centralized application logger configuration.

Every module gets its logger via get_logger(__name__). Each logger writes
to three places:
  - stdout                      — for `python run.py` / console viewing
  - LOG_PATH   (logs/app.log)   — every record at LOG_LEVEL or above
  - LOG_ERROR_PATH (logs/error.log) — ERROR/CRITICAL only, so failures are
    easy to find without grepping the full app log

Reads LOG_LEVEL/LOG_PATH/LOG_ERROR_PATH straight from the environment
(matching app/config.py's defaults) rather than Flask's app.config, since
loggers are created as module-level singletons at import time, often
before any Flask app exists.
"""
import io
import logging
import os
import sys

import colorama

# Enables ANSI color codes on legacy Windows consoles (cmd.exe); a no-op on
# terminals that already support ANSI (Windows Terminal, VS Code, Linux/Mac).
colorama.init()

_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
_LOG_PATH = os.environ.get("LOG_PATH", "logs/app.log")
_LOG_ERROR_PATH = os.environ.get("LOG_ERROR_PATH", "logs/error.log")

_FORMATTER = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

_RESET = colorama.Style.RESET_ALL

# (icon, ANSI color) per level — used only by the console handler below.
_LEVEL_STYLE = {
    "DEBUG": ("•", colorama.Fore.CYAN),
    "INFO": ("✔", colorama.Fore.GREEN),
    "WARNING": ("⚠", colorama.Fore.YELLOW),
    "ERROR": ("✖", colorama.Fore.RED),
    "CRITICAL": ("‼", colorama.Style.BRIGHT + colorama.Fore.RED),
}


class _ConsoleFormatter(logging.Formatter):
    """Console-only formatter: icon + colored level + message, no
    timestamp/logger name — those stay in the full plain-text file logs
    (LOG_PATH/LOG_ERROR_PATH), this is just for a quick glance while
    `python run.py` is running."""

    def format(self, record):
        icon, color = _LEVEL_STYLE.get(record.levelname, ("", ""))
        text = f"{icon} {color}{record.levelname:<9}{_RESET}{record.getMessage()}"
        if record.exc_info:
            text += "\n" + self.formatException(record.exc_info)
        return text


_CONSOLE_FORMATTER = _ConsoleFormatter()


def _console_stream():
    """UTF-8 with errors='replace', regardless of the console's actual
    codepage — without this, the icons above raise UnicodeEncodeError and
    crash the app on a Windows console still using cp1252 (the Windows
    default outside UTF-8-aware terminals like Windows Terminal/VS Code)."""
    if hasattr(sys.stdout, "buffer"):
        return io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", newline="\n")
    return sys.stdout


def _file_handler(path, level=logging.NOTSET):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setLevel(level)
    handler.setFormatter(_FORMATTER)
    return handler


def get_logger(name):
    logger = logging.getLogger(name)
    if not logger.handlers:
        console = logging.StreamHandler(_console_stream())
        console.setFormatter(_CONSOLE_FORMATTER)
        logger.addHandler(console)
        logger.addHandler(_file_handler(_LOG_PATH))
        logger.addHandler(_file_handler(_LOG_ERROR_PATH, level=logging.ERROR))
        logger.setLevel(_LOG_LEVEL)
    return logger
