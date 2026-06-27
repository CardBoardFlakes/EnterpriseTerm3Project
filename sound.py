"""
Subtle ambient sound that follows the weather and the time of day.

Sound files live in sounds/. If they are missing, placeholder loops are
synthesised with the standard-library ``wave`` module so the feature works
out of the box. Playback uses pygame when available and degrades silently
when it is not.
"""

import os
import math
import random
import struct
import wave

SOUNDS_DIR = "sounds"

# Defer pygame import so an audio init failure never crashes the app.
_pygame_available = False
_mixer = None
current_sound = None
_current_path = None      # path of the sound currently playing (for dedup)
_current_volume = 0.25


def _ensure_mixer():
    """Lazily initialise pygame.mixer on first use."""
    global _pygame_available, _mixer
    if _mixer is not None:
        return _pygame_available
    try:
        import pygame
        pygame.mixer.init()
        _mixer = pygame.mixer
        _pygame_available = True
        print("[sound] pygame.mixer initialised successfully.")
    except Exception as e:
        print(f"[sound] Audio unavailable, sounds disabled: {e}")
        _pygame_available = False
        _mixer = False  # sentinel so we don't retry every call
    return _pygame_available


# ---------------------------------------------------------
# Sound selection by weather + time of day
# ---------------------------------------------------------

def select_ambient(condition: str, is_night: bool) -> str:
    """Map (condition, day/night) to an ambient sound filename."""
    cond = (condition or "").lower()
    if "storm" in cond:
        name = "thunder"
    elif "rain" in cond:
        name = "rain-soft"
    elif "cloud" in cond:
        name = "wind"
    elif "clear" in cond:
        name = "crickets" if is_night else "birds"
    elif "night" in cond:
        name = "crickets"
    else:
        name = "wind"
    # Night with otherwise-daytime ambience -> soften toward wind.
    if is_night and name == "birds":
        name = "crickets"
    return os.path.join(SOUNDS_DIR, f"{name}.wav")


# ---------------------------------------------------------
# Playback
# ---------------------------------------------------------

def set_volume(volume_pct):
    """Set ambient volume (0-100). Applies live to any playing sound."""
    global _current_volume
    _current_volume = max(0.0, min(1.0, float(volume_pct) / 100.0))
    if current_sound is not None:
        try:
            current_sound.set_volume(_current_volume)
        except Exception:
            pass


def play_sound(file: str, volume_pct=None):
    """Play a looping ambient sound, replacing any currently playing one."""
    global current_sound, _current_path
    if not _ensure_mixer():
        return

    if volume_pct is not None:
        set_volume(volume_pct)

    if not os.path.isfile(file):
        # Try to synthesise a placeholder so the feature still works.
        try:
            ensure_placeholder_sounds()
        except Exception as e:
            print(f"[sound] Could not create placeholder for {file!r}: {e}")
        if not os.path.isfile(file):
            print(f"[sound] Sound file not found, skipping: {file!r}")
            return

    # Don't restart the same file if it's already playing. (pygame's Sound
    # objects forbid custom attributes, so we track the path ourselves.)
    if current_sound is not None:
        try:
            if current_sound.get_num_channels() > 0 and _current_path == file:
                return
        except Exception:
            pass
        try:
            current_sound.stop()
        except Exception:
            pass

    try:
        snd = _mixer.Sound(file)
        snd.set_volume(_current_volume)
        snd.play(loops=-1)
        current_sound = snd
        _current_path = file
        print(f"[sound] Playing: {file} (vol={_current_volume:.2f})")
    except Exception as e:
        print(f"[sound] Failed to play {file!r}: {e}")


def play_ambient(condition: str, is_night: bool, volume_pct=None):
    """Pick and play the ambient sound for the given weather/time."""
    play_sound(select_ambient(condition, is_night), volume_pct=volume_pct)


def play_chime():
    """One-shot chime, used when a task/schedule fires."""
    if not _ensure_mixer():
        return
    path = os.path.join(SOUNDS_DIR, "chime.wav")
    if not os.path.isfile(path):
        try:
            ensure_placeholder_sounds()
        except Exception:
            return
    try:
        snd = _mixer.Sound(path)
        snd.set_volume(min(1.0, _current_volume + 0.25))
        snd.play()
    except Exception as e:
        print(f"[sound] Failed to play chime: {e}")


def stop_sound():
    """Stop whichever ambient sound is currently playing, if any."""
    global current_sound, _current_path
    if current_sound is not None:
        try:
            current_sound.stop()
        except Exception as e:
            print(f"[sound] Error stopping sound: {e}")
        current_sound = None
        _current_path = None


# ---------------------------------------------------------
# Placeholder sound synthesis (stdlib only)
# ---------------------------------------------------------

_RATE = 22050


def _write_wav(path, samples):
    """Write a list of float samples in [-1, 1] to a 16-bit mono WAV."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(_RATE)
        frames = b"".join(struct.pack("<h", int(max(-1.0, min(1.0, s)) * 32000))
                          for s in samples)
        w.writeframes(frames)


def _noise(n, lp=0.0):
    """White noise, optionally low-pass filtered (lp 0..1, higher=darker)."""
    out = []
    prev = 0.0
    for _ in range(n):
        x = random.uniform(-1, 1)
        if lp:
            prev = prev * lp + x * (1 - lp)
            x = prev
        out.append(x)
    return out


def _synth(name, seconds=2.0):
    n = int(_RATE * seconds)
    if name == "rain-soft":
        return [s * 0.5 for s in _noise(n, lp=0.6)]
    if name == "wind":
        base = _noise(n, lp=0.92)
        return [base[i] * (0.35 + 0.25 * math.sin(2 * math.pi * i / n)) for i in range(n)]
    if name == "thunder":
        rumble = _noise(n, lp=0.97)
        return [rumble[i] * (1.0 - i / n) * 0.8 for i in range(n)]
    if name == "birds":
        out = []
        for i in range(n):
            t = i / _RATE
            chirp = math.sin(2 * math.pi * (1800 + 400 * math.sin(t * 30)) * t)
            env = 0.3 * (1 if (i // (_RATE // 4)) % 2 == 0 else 0)
            out.append(chirp * env)
        return out
    if name == "crickets":
        out = []
        for i in range(n):
            t = i / _RATE
            pulse = 1 if (int(t * 12) % 2 == 0) else 0
            out.append(math.sin(2 * math.pi * 4500 * t) * 0.18 * pulse)
        return out
    if name == "chime":
        out = []
        for i in range(int(_RATE * 0.8)):
            t = i / _RATE
            env = math.exp(-3 * t)
            out.append((math.sin(2 * math.pi * 880 * t)
                        + 0.5 * math.sin(2 * math.pi * 1320 * t)) * 0.3 * env)
        return out
    return _noise(n, lp=0.9)


def ensure_placeholder_sounds(directory=SOUNDS_DIR):
    """Create any missing ambient sound files. Returns the list created."""
    random.seed(42)  # deterministic placeholders
    created = []
    for name in ["rain-soft", "wind", "thunder", "birds", "crickets", "chime"]:
        path = os.path.join(directory, f"{name}.wav")
        if not os.path.isfile(path):
            _write_wav(path, _synth(name))
            created.append(path)
    return created
