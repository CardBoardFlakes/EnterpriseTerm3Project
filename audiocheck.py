"""
Best-effort detection of audio playing from *other* sources on the computer,
so the app can duck its own ambient sound out of the way.

Returns from :func:`external_audio_active`:
  * True  — another app is playing audio,
  * False — nothing else seems to be playing,
  * None  — can't tell on this platform / with what's installed.

Coverage is inherently platform-limited (there's no clean cross-platform API):
  * macOS  — checks the player state of common media apps (Spotify, Apple
             Music) that are already running. Browser/YouTube audio isn't
             detectable this way.
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
