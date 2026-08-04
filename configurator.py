"""
configurator.py — Noc Dashboard settings window (PySide6).

A small desktop window to edit which dashboard cards are shown and the
background sync/alert intervals. Everything is stored in the project's
`.env` file. Saving only rewrites the keys shown here — secrets it does not
manage (DB_PASSWORD, MSSQL_PASSWORD, SECRET_KEY, ...) are never touched.

Run it with:  scripts/configure.bat      (or)   pythonw configurator.py

Every setting here (including card toggles) applies after you restart the
dashboard — app/config.py reads .env once, at process startup.
"""
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QSpinBox,
    QTabWidget, QVBoxLayout, QWidget,
)

ENV_PATH = Path(__file__).resolve().parent / ".env"

# The dashboard card on/off toggles: (.env key, label) — one per card on
# dashboard/index.html and reports/index.html (see app/config.py).
CARD_TOGGLES = [
    ("FEATURE_VVIP_SITE", "VVIP Site"),
    ("FEATURE_MENTOR_SITE", "Mentor Site"),
    ("FEATURE_ISP_POP", "ISP POP / EZE"),
    ("FEATURE_TCT_PORT", "IP Telcotech/Cellcard"),
    ("FEATURE_RAN_STATUS", "RAN Status"),
    ("FEATURE_INCIDENT_INCWO_STATUS", "Incident / INC-WO by Status"),
    ("FEATURE_INCIDENT_SITEDOWN", "Incident Site Down"),
    ("FEATURE_ALARM_SITE_DOWN", "Alarm Site Down"),
    ("FEATURE_ALARM_COMPLETELY_SITE_DOWN", "Alarm Completely Site Down"),
    ("FEATURE_ALARM_MAIN_FAILURE", "Alarm Main Failure"),
    ("FEATURE_INCWO_SITE_DOWN", "INC-WO Site Down"),
    ("FEATURE_ALARM_DG_ON", "Alarm DG On"),
    ("FEATURE_INCWO_RESOLVED", "INC-WO Resolved"),
    ("FEATURE_IT_NODE", "IT NODE"),
]


# ── .env read / write (preserves everything it does not manage) ──────

def read_env() -> dict:
    """Return the .env as a {key: value} dict (values unquoted)."""
    values = {}
    if not ENV_PATH.exists():
        return values
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            values[key.strip()] = val.strip().strip("\"'")
    return values


def write_env(updates: dict) -> None:
    """Rewrite .env, changing only the managed keys in `updates`.

    Existing lines (including comments and unmanaged secrets) are kept in
    place; a managed key already present is updated where it sits; any
    managed key not yet in the file is appended at the end.
    """
    original = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    written = set()
    out = []
    for line in original:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.partition("=")[0].strip()
            if key in updates:
                out.append(f"{key}={updates[key]}")
                written.add(key)
                continue
        out.append(line)

    missing = [k for k in updates if k not in written]
    if missing:
        out.append("")
        out.append("# --- Added by configurator ---")
        out.extend(f"{k}={updates[k]}" for k in missing)

    ENV_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")


def _is_true(value: str) -> bool:
    return str(value).strip().lower() == "true"


# ── The window ───────────────────────────────────────────────────────

class ConfiguratorWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Noc Dashboard — Configuration")
        self.resize(640, 560)

        self.fields = {}   # .env key -> widget

        tabs = QTabWidget()
        tabs.addTab(self._cards_tab(), "Dashboard Cards")
        tabs.addTab(self._general_tab(), "General")

        reload_btn = QPushButton("Reload")
        reload_btn.clicked.connect(self.load_values)
        save_btn = QPushButton("Save to .env")
        save_btn.clicked.connect(self.save_values)

        buttons = QHBoxLayout()
        buttons.addWidget(reload_btn)
        buttons.addStretch()
        buttons.addWidget(save_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        note = QLabel("Restart the dashboard (scripts/start_dashboard.bat) "
                       "after saving for changes to take effect.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #666;")
        layout.addWidget(note)
        layout.addLayout(buttons)

        self.load_values()

    # -- tab builders -------------------------------------------------

    def _cards_tab(self) -> QWidget:
        grid = QGridLayout()
        for i, (key, label) in enumerate(CARD_TOGGLES):
            box = QCheckBox(label)
            self.fields[key] = box
            grid.addWidget(box, i // 2, i % 2)
        wrapper = QVBoxLayout()
        wrapper.addWidget(QLabel("Show or hide each dashboard card:"))
        wrapper.addLayout(grid)
        wrapper.addStretch()
        return self._scrollable(wrapper)

    def _general_tab(self) -> QWidget:
        sync = QFormLayout()
        sync.addRow("Site sync interval (sec):", self._spin("SITE_SYNC_INTERVAL_SECONDS", 10, 3600))
        sync.addRow("Incident sync interval (sec):", self._spin("INCIDENT_SYNC_INTERVAL_SECONDS", 10, 3600))
        sync.addRow("MSSQL alarm sync interval (sec):", self._spin("MSSQL_SYNC_INTERVAL_SECONDS", 5, 3600))
        sync_box = QGroupBox("Sync / Refresh Intervals")
        sync_box.setLayout(sync)

        alert = QFormLayout()
        alert.addRow("Bot token:", self._line("TELEGRAM_BOT_TOKEN", password=True))
        alert.addRow("Chat IDs (comma-separated):", self._line("TELEGRAM_CHAT_IDS"))
        alert.addRow("Outage threshold (min):", self._spin("ALERT_THRESHOLD_MIN", 1, 1440))
        alert.addRow("Alert interval (sec):", self._spin("ALERT_INTERVAL_SECONDS", 60, 86400))
        alert_box = QGroupBox("Telegram Site Down Alert")
        alert_box.setLayout(alert)

        layout_reset = QFormLayout()
        layout_reset.addRow("Reset version:", self._spin("CARD_LAYOUT_RESET_VERSION", 1, 999))
        layout_reset_box = QGroupBox("Card Layout")
        layout_reset_box.setLayout(layout_reset)
        layout_reset_box.setToolTip(
            "Bump this number and Save to reset every user's Card Layout "
            "(card order + hidden cards) back to default the next time "
            "they open the dashboard. Their old choices aren't deleted, "
            "just no longer read."
        )

        wrapper = QVBoxLayout()
        wrapper.addWidget(sync_box)
        wrapper.addWidget(alert_box)
        wrapper.addWidget(layout_reset_box)
        wrapper.addStretch()
        return self._scrollable(wrapper)

    # -- small widget helpers -----------------------------------------

    def _line(self, key: str, password: bool = False) -> QLineEdit:
        widget = QLineEdit()
        if password:
            widget.setEchoMode(QLineEdit.Password)
        self.fields[key] = widget
        return widget

    def _spin(self, key: str, minimum: int, maximum: int) -> QSpinBox:
        widget = QSpinBox()
        widget.setRange(minimum, maximum)
        self.fields[key] = widget
        return widget

    def _scrollable(self, layout) -> QWidget:
        inner = QWidget()
        inner.setLayout(layout)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        return scroll

    # -- load / save --------------------------------------------------

    def load_values(self) -> None:
        env = read_env()

        for key, _ in CARD_TOGGLES:
            self.fields[key].setChecked(_is_true(env.get(key, "true")))

        self.fields["SITE_SYNC_INTERVAL_SECONDS"].setValue(int(env.get("SITE_SYNC_INTERVAL_SECONDS", "300") or 300))
        self.fields["INCIDENT_SYNC_INTERVAL_SECONDS"].setValue(int(env.get("INCIDENT_SYNC_INTERVAL_SECONDS", "300") or 300))
        self.fields["MSSQL_SYNC_INTERVAL_SECONDS"].setValue(int(env.get("MSSQL_SYNC_INTERVAL_SECONDS", "10") or 10))

        self.fields["TELEGRAM_BOT_TOKEN"].setText(env.get("TELEGRAM_BOT_TOKEN", ""))
        self.fields["TELEGRAM_CHAT_IDS"].setText(env.get("TELEGRAM_CHAT_IDS", ""))
        self.fields["ALERT_THRESHOLD_MIN"].setValue(int(env.get("ALERT_THRESHOLD_MIN", "240") or 240))
        self.fields["ALERT_INTERVAL_SECONDS"].setValue(int(env.get("ALERT_INTERVAL_SECONDS", "14400") or 14400))
        self.fields["CARD_LAYOUT_RESET_VERSION"].setValue(int(env.get("CARD_LAYOUT_RESET_VERSION", "1") or 1))

    def save_values(self) -> None:
        updates = {}

        for key, _ in CARD_TOGGLES:
            updates[key] = "True" if self.fields[key].isChecked() else "False"

        for key in ("SITE_SYNC_INTERVAL_SECONDS", "INCIDENT_SYNC_INTERVAL_SECONDS",
                    "MSSQL_SYNC_INTERVAL_SECONDS",
                    "ALERT_THRESHOLD_MIN", "ALERT_INTERVAL_SECONDS",
                    "CARD_LAYOUT_RESET_VERSION"):
            updates[key] = str(self.fields[key].value())

        updates["TELEGRAM_BOT_TOKEN"] = self.fields["TELEGRAM_BOT_TOKEN"].text().strip()
        updates["TELEGRAM_CHAT_IDS"] = self.fields["TELEGRAM_CHAT_IDS"].text().strip()

        try:
            write_env(updates)
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", f"Could not write .env:\n{exc}")
            return
        QMessageBox.information(
            self, "Saved",
            "Settings saved to .env.\n\nRestart the dashboard for these changes to take effect.")


def main() -> int:
    app = QApplication(sys.argv)
    window = ConfiguratorWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
