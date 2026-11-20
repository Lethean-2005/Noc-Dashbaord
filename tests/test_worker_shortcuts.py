"""Validate shortcut targets in a temporary folder, never the user's desktop."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows shortcuts')
def test_worker_shortcut_targets_current_project(tmp_path):
    root = Path(__file__).resolve().parents[1]
    source = (root / 'scripts' / 'create_shortcuts.bat').read_text(encoding='utf-8')
    command = next(line for line in source.splitlines() if line.startswith('powershell -NoProfile -Command '))
    script = command.split('-Command "', 1)[1][:-1]
    desktop = tmp_path / 'test desktop'
    desktop.mkdir()
    script = script.replace("[Environment]::GetFolderPath('Desktop')", "'" + str(desktop).replace("'", "''") + "'")
    script += "; Get-ChildItem -LiteralPath $desktop -Filter '*.lnk' | ForEach-Object { $link=$shell.CreateShortcut($_.FullName); [pscustomobject]@{Name=$_.BaseName;Target=$link.TargetPath;WorkingDirectory=$link.WorkingDirectory} } | ConvertTo-Json -Compress"
    result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', script],
                            env=dict(os.environ, NOC_SHORTCUT_ROOT=str(root)),
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    links = {item['Name']: item for item in json.loads(result.stdout)}
    assert set(links) == {'Noc Dashboard', 'Dashboard Settings', 'NOC_Worker'}
    assert Path(links['NOC_Worker']['Target']) == root / 'scripts' / 'open_worker.bat'
    assert Path(links['NOC_Worker']['WorkingDirectory']) == root
    assert len(list(desktop.glob('*.lnk'))) == 3
