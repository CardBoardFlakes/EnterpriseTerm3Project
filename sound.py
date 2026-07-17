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

# Absolute so the app always finds your files regardless of the working
# directory (Finder launch, run-at-login, `--once` from elsewhere, …).
SOUNDS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sounds")

# Wind at/above this speed (km/h) plays the "cloud" (windy) ambience even on an
# otherwise clear sky.
WIND_AMBIENCE_KMH = 25

# (display label, base filename) for each weather the app has ambience for.
# The chime is separate (task/schedule feedback), not weather ambience.
SOUND_CONDITIONS = [
    ("Clear day",   "clearday"),
    ("Clear night", "clearnight"),
    ("Cloudy",      "cloud"),
    ("Rain",        "rain"),
    ("Storm",       "storm"),
]

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

def ambient_base(condition: str, is_night: bool, wind_speed: float = 0) -> str:
    """
    Map (condition, day/night, wind) to a base sound name. Names are generic
    and condition-based, so dropping your own file in sounds/ is obvious:
      storm  rain  cloud  clearday  clearnight
    Strong wind on an otherwise clear sky uses the "cloud" (windy) ambience.
    """
    cond = (condition or "").lower()
    if "storm" in cond:
        name = "storm"
    elif "rain" in cond:
        name = "rain"
    elif "cloud" in cond:
        name = "cloud"
    elif "clear" in cond:
        name = "clearnight" if is_night else "clearday"
    elif "night" in cond:
        name = "clearnight"
    else:
        name = "cloud"
    # A clear-but-windy sky still gets the windy (cloud) soundscape.
    if name in ("clearday", "clearnight") and wind_speed and wind_speed >= WIND_AMBIENCE_KMH:
        name = "cloud"
    return name


def select_ambient(condition: str, is_night: bool) -> str:
    """Canonical file path (``base.wav``) for the weather/time — deterministic."""
    return os.path.join(SOUNDS_DIR, f"{ambient_base(condition, is_night)}.wav")


def list_variants(base: str, directory=SOUNDS_DIR):
    """
    All files that count as the *base* sound: ``base.wav`` plus any variant
    like ``base2.wav``, ``base-forest.wav``, ``base_1.wav``. Lets users add
    several clips per condition so the ambience doesn't get repetitive.
    """
    try:
        files = os.listdir(directory)
    except OSError:
        return []
    base = base.lower()
    out = []
    for f in files:
        low = f.lower()
        if not low.endswith(".wav") or not low.startswith(base):
            continue
        rest = low[len(base):-4]           # between the base and ".wav"
        # Accept an exact match or a variant marked by a digit/-/_/space,
        # so "clearday" never swallows a different base sharing its prefix.
        if rest == "" or rest[0] in "-_ 0123456789":
            out.append(os.path.join(directory, f))
    return sorted(out)


def pick_base(base: str, directory=SOUNDS_DIR, rng=None):
    """A randomly chosen variant path for a base name (falls back to base.wav)."""
    variants = list_variants(base, directory)
    if not variants:
        return os.path.join(directory, f"{base}.wav")
    return (rng or random).choice(variants)


def pick_variant(condition: str, is_night: bool, directory=SOUNDS_DIR,
                 rng=None, wind_speed: float = 0):
    """A randomly chosen variant path for the weather/time (falls back to base)."""
    return pick_base(ambient_base(condition, is_night, wind_speed), directory, rng)


def open_folder(directory=SOUNDS_DIR):
    """Reveal the sounds folder in the OS file manager. Returns True on success."""
    import sys
    import subprocess
    os.makedirs(directory, exist_ok=True)
    path = os.path.abspath(directory)
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", path], timeout=5)
        elif sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.run(["xdg-open", path], timeout=5)
        return True
    except Exception as e:
        print(f"[sound] Could not open folder: {e}")
        return False


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


def play_sound(file: str, volume_pct=None, loop=True):
    """
    Play an ambient sound, replacing any currently playing one. *loop*=True
    repeats it continuously; *loop*=False plays it once (used by the
    occasional/random mode).
    """
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

    # For a looping sound, don't restart the same file if it's already playing.
    # (pygame's Sound objects forbid custom attributes, so we track the path
    # ourselves.) One-shot plays always fire — that's the point.
    if current_sound is not None:
        try:
            if loop and current_sound.get_num_channels() > 0 and _current_path == file:
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
        snd.play(loops=-1 if loop else 0)
        current_sound = snd
        _current_path = file
        print(f"[sound] Playing: {file} (loop={loop}, vol={_current_volume:.2f})")
    except Exception as e:
        print(f"[sound] Failed to play {file!r}: {e}")


def play_ambient(condition: str, is_night: bool, volume_pct=None,
                 path=None, loop=True):
    """
    Play the ambient sound for the given weather/time. *path* lets the caller
    supply an already-chosen variant; otherwise the canonical file is used.
    """
    play_sound(path or select_ambient(condition, is_night),
               volume_pct=volume_pct, loop=loop)


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
    if name == "rain":
        return [s * 0.5 for s in _noise(n, lp=0.6)]
    if name == "cloud":
        base = _noise(n, lp=0.92)
        return [base[i] * (0.35 + 0.25 * math.sin(2 * math.pi * i / n)) for i in range(n)]
    if name == "storm":
        rumble = _noise(n, lp=0.97)
        return [rumble[i] * (1.0 - i / n) * 0.8 for i in range(n)]
    if name == "clearday":
        out = []
        for i in range(n):
            t = i / _RATE
            chirp = math.sin(2 * math.pi * (1800 + 400 * math.sin(t * 30)) * t)
            env = 0.3 * (1 if (i // (_RATE // 4)) % 2 == 0 else 0)
            out.append(chirp * env)
        return out
    if name == "clearnight":
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
    for name in ["rain", "cloud", "storm", "clearday", "clearnight", "chime"]:
        path = os.path.join(directory, f"{name}.wav")
        if not os.path.isfile(path):
            _write_wav(path, _synth(name))
            created.append(path)
    return created
