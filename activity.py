import sys
import time


def get_idle_time() -> float:
    """
    Return the number of seconds since the user last interacted with the system.

    Works on Windows (via ctypes/user32) and macOS (via ioreg).
    Returns 0.0 on unsupported platforms so callers always get a valid float.
    """
    if sys.platform == "win32":
        return _get_idle_windows()
    elif sys.platform == "darwin":
        return _get_idle_macos()
    else:
        print("[activity] Idle detection not supported on this platform — returning 0.")
        return 0.0


# ---------------------------------------------------------
# Windows implementation
# ---------------------------------------------------------

def _get_idle_windows() -> float:
    try:
        import ctypes

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.c_uint),
                ("dwTime", ctypes.c_uint),
            ]

        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)

        ok = ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
        if not ok:
            raise OSError("GetLastInputInfo returned FALSE")

        millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
        return millis / 1000.0

    except Exception as e:
        print(f"[activity] Windows idle detection failed: {e}")
        return 0.0


# ---------------------------------------------------------
# macOS implementation
# ---------------------------------------------------------

def _get_idle_macos() -> float:
    try:
        import subprocess
        result = subprocess.run(
            ["ioreg", "-c", "IOHIDSystem"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if "HIDIdleTime" in line:
                # value is in nanoseconds
                ns = int(line.split("=")[-1].strip())
                return ns / 1_000_000_000.0
        print("[activity] HIDIdleTime not found in ioreg output.")
        return 0.0
    except Exception as e:
        print(f"[activity] macOS idle detection failed: {e}")
        return 0.0