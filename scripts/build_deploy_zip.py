"""Builds a lean deploy_zips/Noc_Dashboard-<date>_V<n>.zip containing only
what's needed to run the app — no caches, logs, secrets, docs, or scratch
files. Run from the repo root: python scripts/build_deploy_zip.py
"""

import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEPLOY_DIR = ROOT / "deploy_zips"
ZIP_ROOT_NAME = "Noc-Dashboard"

# Only these top-level paths are included — everything else at the repo
# root (docs/, NOC DATA/, tests/, .github/, .vscode/, logs/, instance/,
# .venv/, loose scratch files, log files, etc.) isn't needed to run the
# app, so it's left out rather than copied in and excluded after.
INCLUDE_PATHS = [
    "app",
    "postgres",
    "scripts",
    "webhook",
    "configurator.py",
    "run.py",
    "requirements.txt",
    "pyproject.toml",
    "README.md",
    ".env.example",
    ".gitignore",
]

# Still skipped even inside an included path — generated/local-only, never
# something to ship (cache dirs, .env with real secrets, DB files, IDE/lint
# caches, and instance/ if it ever ends up nested under an included path).
EXCLUDE_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "instance",
    ".env",
}
EXCLUDE_SUFFIXES = {".pyc", ".db"}


def _iter_files(path: Path):
    if path.is_file():
        yield path
        return
    for p in path.rglob("*"):
        if p.is_dir():
            continue
        if any(part in EXCLUDE_NAMES for part in p.relative_to(ROOT).parts):
            continue
        if p.suffix in EXCLUDE_SUFFIXES:
            continue
        yield p


def _next_version(existing):
    versions = []
    for f in existing:
        stem = f.stem
        if "_V" in stem:
            try:
                versions.append(int(stem.rsplit("_V", 1)[1]))
            except ValueError:
                pass
    return max(versions, default=0) + 1


def main():
    DEPLOY_DIR.mkdir(exist_ok=True)
    version = _next_version(DEPLOY_DIR.glob("Noc_Dashboard-*_V*.zip"))
    out_path = DEPLOY_DIR / f"Noc_Dashboard-{date.today().isoformat()}_V{version}.zip"

    count = 0
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in INCLUDE_PATHS:
            src = ROOT / rel
            if not src.exists():
                print(f"skip (missing): {rel}")
                continue
            for f in _iter_files(src):
                arcname = f"{ZIP_ROOT_NAME}/{f.relative_to(ROOT).as_posix()}"
                zf.write(f, arcname)
                count += 1

    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"Wrote {out_path} ({count} files, {size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
