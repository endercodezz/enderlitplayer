"""Import every module of the package and validate the built wheel's contents.

Usage:
  python scripts/check_package.py imports
  python scripts/check_package.py wheel dist/enderlitplayer-2.0.0-py3-none-any.whl
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
import zipfile
from pathlib import Path

REQUIRED_IN_WHEEL = (
    "enderlitplayer/__init__.py",
    "enderlitplayer/__main__.py",
    "enderlitplayer/app.py",
    "enderlitplayer/ui/main_window.py",
    "enderlitplayer/ui/styles/stylesheet.py",
    "enderlitplayer/i18n/translations.py",
)


def check_imports() -> int:
    import enderlitplayer

    names = [m.name for m in pkgutil.walk_packages(enderlitplayer.__path__, "enderlitplayer.")]
    for name in names:
        importlib.import_module(name)
    print(f"Imported {len(names)} modules from enderlitplayer {enderlitplayer.__version__}")
    return 0


def check_wheel(path: str) -> int:
    from enderlitplayer import __version__

    wheel = Path(path)
    if f"-{__version__}-" not in wheel.name:
        print(f"Wheel {wheel.name} does not carry version {__version__}")
        return 1
    with zipfile.ZipFile(wheel) as zf:
        names = set(zf.namelist())
    missing = [item for item in REQUIRED_IN_WHEEL if item not in names]
    stray = [n for n in names if n.startswith(("tests/", ".tmp/")) or "__pycache__" in n]
    if missing or stray:
        print("Missing:", missing, "Unexpected:", stray)
        return 1
    print(f"{wheel.name}: {len(names)} files OK")
    return 0


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "imports"
    if command == "wheel":
        raise SystemExit(check_wheel(sys.argv[2]))
    raise SystemExit(check_imports())
