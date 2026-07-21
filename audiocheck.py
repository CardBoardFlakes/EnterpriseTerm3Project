"""
Best-effort detection of audio playing from *other* sources on the computer,
so the app can duck its own ambient sound out of the way.

Returns from :func:`external_audio_active`:
  * True  — another app is playing audio,
  * False — nothing else seems to be playing,
  * None  — can't tell on this platform / with what's installed.

Coverage is platform-specific:
  * macOS  — reads CoreAudio's per-process output state, with a Spotify / Apple
             Music player-state fallback on older systems.
  * Windows — uses per-app audio meters via ``pycaw`` when it's installed;
             catches essentially any app.
  * else   — unknown (None).
"""

import os
import sys

_MACOS_MEDIA_APPS = ("Spotify", "Music")


def external_audio_active():
    try:
        if sys.platform == "darwin":
            return _macos_playing()
        if sys.platform == "win32":
            return _windows_playing()
    except Exception as e:
        print(f"[audiocheck] detection failed: {e}")
        return None
    return None


def _macos_playing():
    processes = _macos_coreaudio_processes()
    if processes is not None:
        own = os.getpid()
        return any(pid != own and running for pid, running in processes)
    return _macos_media_app_playing()


def _fourcc(value):
    return int.from_bytes(value.encode("ascii"), "big")


def _macos_coreaudio_processes():
    """Return ``(pid, has_active_output)`` pairs, or None when unavailable."""
    import ctypes
    import ctypes.util

    class Address(ctypes.Structure):
        _fields_ = [
            ("selector", ctypes.c_uint32),
            ("scope", ctypes.c_uint32),
            ("element", ctypes.c_uint32),
        ]

    try:
        path = ctypes.util.find_library("CoreAudio")
        if not path:
            return None
        core = ctypes.CDLL(path)
        get_size = core.AudioObjectGetPropertyDataSize
        get_size.argtypes = [
            ctypes.c_uint32, ctypes.POINTER(Address), ctypes.c_uint32,
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32),
        ]
        get_size.restype = ctypes.c_int32
        get_data = core.AudioObjectGetPropertyData
        get_data.argtypes = [
            ctypes.c_uint32, ctypes.POINTER(Address), ctypes.c_uint32,
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32), ctypes.c_void_p,
        ]
        get_data.restype = ctypes.c_int32

        address = Address(_fourcc("prs#"), _fourcc("glob"), 0)
        size = ctypes.c_uint32()
        if get_size(1, ctypes.byref(address), 0, None, ctypes.byref(size)) != 0:
            return None
        objects = (ctypes.c_uint32 * (size.value // 4))()
        if size.value and get_data(
                1, ctypes.byref(address), 0, None,
                ctypes.byref(size), objects) != 0:
            return None

        def scalar(object_id, selector, ctype):
            prop = Address(_fourcc(selector), _fourcc("glob"), 0)
            prop_size = ctypes.c_uint32(ctypes.sizeof(ctype))
            value = ctype()
            status = get_data(
                object_id, ctypes.byref(prop), 0, None,
                ctypes.byref(prop_size), ctypes.byref(value))
            return None if status else value.value

        result = []
        for object_id in objects:
            pid = scalar(object_id, "ppid", ctypes.c_int32)
            running = scalar(object_id, "piro", ctypes.c_uint32)
            if pid is not None and running is not None:
                result.append((pid, bool(running)))
        return result
    except Exception:
        return None


def _macos_media_app_playing():
    import subprocess
    for app in _MACOS_MEDIA_APPS:
        try:
            # Only query apps that are already running (querying launches them).
            running = subprocess.run(
                ["osascript", "-e",
                 f'tell application "System Events" to (name of processes) contains "{app}"'],
                capture_output=True, text=True, timeout=3)
            if running.stdout.strip().lower() != "true":
                continue
            state = subprocess.run(
                ["osascript", "-e", f'tell application "{app}" to player state'],
                capture_output=True, text=True, timeout=3)
            if "playing" in state.stdout.strip().lower():
                return True
        except Exception:
            continue
    return False


def _windows_playing():
    try:
        from pycaw.pycaw import AudioUtilities, IAudioMeterInformation
    except Exception:
        return None            # pycaw not installed -> can't tell
    own = os.getpid()
    try:
        sessions = AudioUtilities.GetAllSessions()
    except Exception:
        return None
    for s in sessions:
        try:
            proc = s.Process
            if not proc or proc.pid == own:
                continue
            meter = s._ctl.QueryInterface(IAudioMeterInformation)
            if meter.GetPeakValue() > 0.01:   # actually emitting sound
                return True
        except Exception:
            continue
    return False
