"""VM launchers must work without the development-only tests/manual folder."""
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parent.parent


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_all_telegram_launchers_use_the_deployable_runner():
    runner = load_script("send_telegram_test")
    packager = load_script("build_deploy_zip")
    included = {p.relative_to(ROOT).as_posix() for name in packager.INCLUDE_PATHS for p in packager._iter_files(ROOT / name) if p.exists()}
    assert "scripts/send_telegram_test.py" in included
    for filename, kind in [("telegram_alert_test.bat", "site-down"), ("telegram_inc_wo_alert_test.bat", "incwo-site-down"), ("telegram_inc_wo_power_alert_test.bat", "incwo-power"), ("telegram_inc_wo_general_alert_test.bat", "incwo-general")]:
        text = (ROOT / "scripts" / filename).read_text()
        assert "tests\\manual" not in text
        assert "scripts\\send_telegram_test.py " + kind in text
        assert kind in runner.ALERTS


def test_dry_run_never_sends_or_starts_schedulers(monkeypatch, capsys):
    runner = load_script("send_telegram_test")
    from types import SimpleNamespace
    def forbidden():
        raise AssertionError("dry run must not send")
    monkeypatch.setattr(runner, "import_module", lambda name: SimpleNamespace(send_site_down_alert=forbidden))
    assert runner.main(["site-down", "--dry-run"]) == 0
    assert "No alerts sent; no schedulers started" in capsys.readouterr().out
