"""Build the portable Windows distribution.

Steps: render the icon, write Windows version metadata, run PyInstaller in
``onedir`` mode, verify the bundle (Qt multimedia plugin present, frozen app
passes ``--smoke-test``), then create the versioned ZIP and SHA256SUMS.txt.

Usage:  python scripts/build_windows.py [--skip-smoke-test]
Output: dist/EnderlitPlayer-<version>-Windows-Portable.zip and dist/SHA256SUMS.txt
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from enderlitplayer import APP_AUTHOR, APP_NAME, __version__  # noqa: E402

BUILD = ROOT / "build"
DIST = ROOT / "dist"
NAME = "EnderlitPlayer"
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def render_icon(target: Path) -> Path:
    """Write a multi-resolution .ico (PNG-compressed entries) from the painted logo."""
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    from PySide6.QtGui import QGuiApplication

    from enderlitplayer.ui.assets.artwork import build_icon_image

    _app = QGuiApplication.instance() or QGuiApplication(["icon"])
    images = []
    for size in ICON_SIZES:
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        build_icon_image(size).save(buffer, "PNG")
        buffer.close()
        images.append((size, bytes(data.data())))
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for size, png in images:
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset + len(blobs))
        blobs += png
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(header + entries + blobs)
    return target


def write_version_file(target: Path) -> Path:
    parts = [int(p) for p in __version__.split(".")[:3]] + [0]
    numbers = tuple(parts[:4])
    target.write_text(
        f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={numbers}, prodvers={numbers}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', '{APP_AUTHOR}'),
      StringStruct('FileDescription', '{APP_NAME}'),
      StringStruct('FileVersion', '{__version__}'),
      StringStruct('InternalName', '{NAME}'),
      StringStruct('OriginalFilename', '{NAME}.exe'),
      StringStruct('ProductName', '{APP_NAME}'),
      StringStruct('ProductVersion', '{__version__}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""",
        encoding="utf-8",
    )
    return target


def run_pyinstaller(icon: Path, version_file: Path) -> Path:
    shutil.rmtree(DIST / NAME, ignore_errors=True)
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",
        "--name",
        NAME,
        "--icon",
        str(icon),
        "--version-file",
        str(version_file),
        "--paths",
        str(ROOT / "src"),
        "--distpath",
        str(DIST),
        "--workpath",
        str(BUILD / "pyinstaller"),
        "--specpath",
        str(BUILD),
        "--collect-submodules",
        "enderlitplayer",
        # Modules PyInstaller may pull in transitively but the player never uses.
        "--exclude-module",
        "tkinter",
        "--exclude-module",
        "PySide6.QtWebEngineCore",
        "--exclude-module",
        "PySide6.QtQml",
        "--exclude-module",
        "PySide6.QtQuick",
        "--exclude-module",
        "PySide6.Qt3DCore",
        str(ROOT / "src" / "enderlitplayer" / "__main__.py"),
    ]
    print("+", " ".join(command), flush=True)
    subprocess.run(command, check=True, cwd=ROOT)
    return DIST / NAME


def verify_bundle(bundle: Path, smoke_test: bool) -> None:
    exe = bundle / f"{NAME}.exe"
    if not exe.is_file():
        raise SystemExit(f"Missing executable: {exe}")
    plugins = list(bundle.rglob("ffmpegmediaplugin*.dll")) + list(bundle.rglob("windowsmediaplugin*.dll"))
    if not plugins:
        raise SystemExit("Qt multimedia backend plugin was not bundled")
    if not list(bundle.rglob("qwindows*.dll")):
        raise SystemExit("Qt platform plugin (qwindows) was not bundled")
    print("Bundled multimedia plugins:", ", ".join(p.name for p in plugins), flush=True)
    if smoke_test:
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
        result = subprocess.run([str(exe), "--smoke-test"], env=env, timeout=120, check=False)
        if result.returncode != 0:
            raise SystemExit(f"Frozen smoke test failed with exit code {result.returncode}")
        print("Frozen smoke test passed", flush=True)


def package(bundle: Path) -> tuple[Path, Path]:
    archive = DIST / f"{NAME}-{__version__}-Windows-Portable.zip"
    archive.unlink(missing_ok=True)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(bundle.rglob("*")):
            if path.is_file():
                zf.write(path, Path(NAME) / path.relative_to(bundle))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    sums = DIST / "SHA256SUMS.txt"
    sums.write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    print(f"{archive.name}: {archive.stat().st_size / 1_048_576:.1f} MiB, sha256 {digest}", flush=True)
    return archive, sums


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--skip-smoke-test", action="store_true", help="do not launch the frozen executable")
    args = parser.parse_args()
    if sys.platform != "win32":
        raise SystemExit("The portable build must be produced on Windows")
    icon = render_icon(BUILD / "icon.ico")
    version_file = write_version_file(BUILD / "version_info.txt")
    bundle = run_pyinstaller(icon, version_file)
    verify_bundle(bundle, smoke_test=not args.skip_smoke_test)
    package(bundle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
