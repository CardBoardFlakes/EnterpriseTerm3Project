"""
Build a double-clickable Flow app for the current OS.

  pip install -r requirements.txt -r packaging/requirements-build.txt
  python packaging/build.py

Output (in dist/):
  macOS   -> Flow.app  and  Flow-macOS-<arch>.dmg   (drag Flow into Applications)
  Windows -> Flow.exe  and  Flow-Windows-<arch>.exe (copy of Flow.exe for release)

Set FLOW_VERSION (e.g. v1.2.0) to stamp the macOS bundle version.
"""

import os
import platform
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DIST = os.path.join(ROOT, "dist")
WORK = os.path.join(HERE, "build", "pyinstaller")

sys.path.insert(0, HERE)
import make_icon  # noqa: E402


def _arch():
    """arm64 / x86_64 on macOS; x64 / arm64 on Windows."""
    machine = platform.machine().lower()
    if sys.platform == "win32":
        return {"amd64": "x64", "x86_64": "x64"}.get(machine, machine)
    return machine


def run_pyinstaller():
    import PyInstaller.__main__
    PyInstaller.__main__.run([
        os.path.join(HERE, "flow.spec"),
        "--noconfirm", "--clean",
        "--distpath", DIST,
        "--workpath", WORK,
    ])


def package_macos():
    app = os.path.join(DIST, "Flow.app")
    dmg = os.path.join(DIST, f"Flow-macOS-{_arch()}.dmg")
    with tempfile.TemporaryDirectory() as stage:
        # Flow.app next to an Applications shortcut: the usual drag-to-install DMG.
        subprocess.run(["ditto", app, os.path.join(stage, "Flow.app")], check=True)
        os.symlink("/Applications", os.path.join(stage, "Applications"))
        if os.path.exists(dmg):
            os.remove(dmg)
        subprocess.run(["hdiutil", "create", "-volname", "Flow", "-srcfolder", stage,
                        "-ov", "-format", "UDZO", dmg], check=True)
    return dmg


def package_windows():
    exe = os.path.join(DIST, "Flow.exe")
    out = os.path.join(DIST, f"Flow-Windows-{_arch()}.exe")
    shutil.copyfile(exe, out)
    return out


def main():
    make_icon.main()
    run_pyinstaller()
    if sys.platform == "darwin":
        out = package_macos()
    elif sys.platform == "win32":
        out = package_windows()
    else:
        out = os.path.join(DIST, "Flow")
    print(f"[build] done -> {out}")


if __name__ == "__main__":
    main()
