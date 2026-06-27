"""
Run the application automatically at login.

  * macOS   -> a LaunchAgent plist in ~/Library/LaunchAgents
  * Windows -> a value under HKCU\\...\\CurrentVersion\\Run

Both launch ``main.py --background`` (the headless engine loop).
"""

import os
import sys
import subprocess

LABEL = "com.environmenttheme.controller"
RUN_VALUE_NAME = "EnvironmentThemeController"

# Absolute path to this project's entry point.
APP_DIR = os.path.dirname(os.path.abspath(__file__))
APP_MAIN = os.path.join(APP_DIR, "main.py")


def _python_exe() -> str:
    """Preferred interpreter to relaunch with (windowless on Windows)."""
    exe = sys.executable or "python3"
    if sys.platform == "win32":
        cand = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.isfile(cand):
            return cand
    return exe


# ---------------------------------------------------------
# macOS (LaunchAgent)
# ---------------------------------------------------------

def _macos_plist_path() -> str:
    return os.path.join(os.path.expanduser("~"), "Library", "LaunchAgents",
                        f"{LABEL}.plist")


def _macos_plist_contents() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        '<dict>\n'
        f'    <key>Label</key>\n    <string>{LABEL}</string>\n'
        '    <key>ProgramArguments</key>\n'
        '    <array>\n'
        f'        <string>{_python_exe()}</string>\n'
        f'        <string>{APP_MAIN}</string>\n'
        '        <string>--background</string>\n'
        '    </array>\n'
        f'    <key>WorkingDirectory</key>\n    <string>{APP_DIR}</string>\n'
        '    <key>RunAtLoad</key>\n    <true/>\n'
        '</dict>\n'
        '</plist>\n'
    )


def _macos_enable() -> bool:
    path = _macos_plist_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(_macos_plist_contents())
    try:
        subprocess.run(["launchctl", "unload", path],
                       capture_output=True, text=True)  # ignore if not loaded
        subprocess.run(["launchctl", "load", "-w", path],
                       check=True, capture_output=True, text=True)
    except Exception as e:
        print(f"[autostart] launchctl load failed (plist still written): {e}")
    print(f"[autostart] Enabled via LaunchAgent {path}")
    return True


def _macos_disable() -> bool:
    path = _macos_plist_path()
    if os.path.exists(path):
        try:
            subprocess.run(["launchctl", "unload", path],
                           capture_output=True, text=True)
        except Exception:
            pass
        try:
            os.remove(path)
        except OSError as e:
            print(f"[autostart] Could not remove {path}: {e}")
            return False
    print("[autostart] Disabled (LaunchAgent removed).")
    return True


def _macos_is_enabled() -> bool:
    return os.path.exists(_macos_plist_path())


# ---------------------------------------------------------
# Windows (Run registry key)
# ---------------------------------------------------------

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _windows_command() -> str:
    return f'"{_python_exe()}" "{APP_MAIN}" --background'


def _windows_enable() -> bool:
    import winreg
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0,
                             winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, RUN_VALUE_NAME, 0, winreg.REG_SZ, _windows_command())
        winreg.CloseKey(key)
        print("[autostart] Enabled via HKCU Run key.")
        return True
    except OSError as e:
        print(f"[autostart] Failed to set Run key: {e}")
        return False


def _windows_disable() -> bool:
    import winreg
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0,
                             winreg.KEY_SET_VALUE)
        try:
            winreg.DeleteValue(key, RUN_VALUE_NAME)
        except FileNotFoundError:
            pass
        winreg.CloseKey(key)
        print("[autostart] Disabled (Run key removed).")
        return True
    except OSError as e:
        print(f"[autostart] Failed to remove Run key: {e}")
        return False


def _windows_is_enabled() -> bool:
    import winreg
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0,
                             winreg.KEY_READ)
        try:
            winreg.QueryValueEx(key, RUN_VALUE_NAME)
            return True
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except OSError:
        return False


# ---------------------------------------------------------
# Public API
# ---------------------------------------------------------

def set_autostart(enabled: bool) -> bool:
    """Enable or disable run-at-login for the current platform."""
    if sys.platform == "darwin":
        return _macos_enable() if enabled else _macos_disable()
    elif sys.platform == "win32":
        return _windows_enable() if enabled else _windows_disable()
    else:
        print(f"[autostart] Not supported on {sys.platform!r}.")
        return False


def is_autostart_enabled() -> bool:
    if sys.platform == "darwin":
        return _macos_is_enabled()
    elif sys.platform == "win32":
        return _windows_is_enabled()
    return False


def preview_command() -> str:
    """Human-readable description of what will run at login (for tests/UI)."""
    if sys.platform == "darwin":
        return f"{_python_exe()} {APP_MAIN} --background  (LaunchAgent {LABEL})"
    elif sys.platform == "win32":
        return _windows_command()
    return "unsupported"
