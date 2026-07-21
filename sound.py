"""
Subtle ambient sound that follows the weather and the time of day.

Sound files live in sounds/. If they are missing, placeholder loops are
synthesised with the standard-library ``wave`` module so the feature works
out of the box. Playback uses pygame when available and degrades silently
when it is not.
"""

import os
import hashlib
import math
import random
import struct
import threading
import tempfile
import time
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
_mixer_retry_at = 0.0
current_sound = None
_current_channel = None
_current_path = None      # path of the sound currently playing (for dedup)
_current_volume = 0.25
_music_prev_vol = None     # music-stream volume saved while a chime ducks it
_ambient_lock_file = None
_ambient_lock_path = os.path.join(
    tempfile.gettempdir(),
    f"flow-ambient-{hashlib.sha256(SOUNDS_DIR.encode()).hexdigest()[:16]}.lock")


def _claim_ambient_lock():
    """Allow one GUI/background process to own ambient playback."""
    global _ambient_lock_file
    if _ambient_lock_file is not None:
        return True
    lock_file = None
    try:
        lock_file = open(_ambient_lock_path, "a+b")
        lock_file.seek(0, os.SEEK_END)
        if lock_file.tell() == 0:
            lock_file.write(b"\0")
            lock_file.flush()
        lock_file.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, IOError):
        if lock_file is not None:
            lock_file.close()
        return False
    _ambient_lock_file = lock_file
    return True


def _release_ambient_lock():
    global _ambient_lock_file
    lock_file = _ambient_lock_file
    if lock_file is None:
        return
    try:
        lock_file.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    except (OSError, IOError):
        pass
    lock_file.close()
    _ambient_lock_file = None


def _ensure_mixer():
    """Lazily initialise pygame.mixer, retrying after transient device errors."""
    global _pygame_available, _mixer, _mixer_retry_at
    if _mixer not in (None, False):
        return _pygame_available
    now = time.monotonic()
    if _mixer is False and now < _mixer_retry_at:
        return False
    try:
        import pygame
        pygame.mixer.init(frequency=_RATE, buffer=1024)
        _mixer = pygame.mixer
        _pygame_available = True
        _mixer_retry_at = 0.0
        print("[sound] pygame.mixer initialised successfully.")
    except Exception as e:
        print(f"[sound] Audio unavailable, sounds disabled: {e}")
        _pygame_available = False
        _mixer = False
        _mixer_retry_at = now + 5.0
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


def ambient_is_playing():
    """Whether the ambient loop still owns an active mixer channel."""
    if current_sound is None:
        return False
    try:
        if _current_channel is not None:
            return bool(_current_channel.get_busy())
        return current_sound.get_num_channels() > 0
    except Exception:
        return False


def play_sound(file: str, volume_pct=None, loop=True):
    """
    Play an ambient sound, replacing any currently playing one. *loop*=True
    repeats it continuously; *loop*=False plays it once.
    """
    global current_sound, _current_channel, _current_path
    try:
        ensure_placeholder_sounds()
    except Exception as e:
        print(f"[sound] Could not prepare built-in sounds: {e}")
    if not _ensure_mixer():
        return False

    if volume_pct is not None:
        set_volume(volume_pct)

    if not os.path.isfile(file):
        # Try to synthesise a placeholder so the feature still works.
        try:
            ensure_placeholder_sounds(os.path.dirname(file))
        except Exception as e:
            print(f"[sound] Could not create placeholder for {file!r}: {e}")
        if not os.path.isfile(file):
            print(f"[sound] Sound file not found, skipping: {file!r}")
            return False

    if loop and not _claim_ambient_lock():
        return False

    # For a looping sound, don't restart the same file if it's already playing.
    # (pygame's Sound objects forbid custom attributes, so we track the path
    # ourselves.) One-shot plays always fire — that's the point.
    if current_sound is not None:
        try:
            if loop and ambient_is_playing() and _current_path == file:
                return True
        except Exception:
            pass
        try:
            current_sound.stop()
        except Exception:
            pass
        current_sound = None
        _current_channel = None
        _current_path = None

    try:
        snd = _mixer.Sound(file)
        snd.set_volume(_current_volume)
        channel = snd.play(loops=-1 if loop else 0)
        if channel is None:
            print(f"[sound] No mixer channel available for {file!r}")
            if loop:
                _release_ambient_lock()
            return False
        current_sound = snd
        _current_channel = channel
        _current_path = file
        print(f"[sound] Playing: {file} (loop={loop}, vol={_current_volume:.2f})")
        return True
    except Exception as e:
        print(f"[sound] Failed to play {file!r}: {e}")
        if loop:
            _release_ambient_lock()
        return False


def play_ambient(condition: str, is_night: bool, volume_pct=None,
                 path=None, loop=True):
    """
    Play the ambient sound for the given weather/time. *path* lets the caller
    supply an already-chosen variant; otherwise the canonical file is used.
    """
    return play_sound(path or select_ambient(condition, is_night),
                      volume_pct=volume_pct, loop=loop)


def _duck_for_chime():
    """Lower ambient + music so a chime is clearly heard (chime > music > ambient)."""
    global _music_prev_vol
    # Ambient loop: drop to a whisper (restored after the chime).
    if current_sound is not None:
        try:
            current_sound.set_volume(_current_volume * 0.15)
        except Exception:
            pass
    # Music stream: remember its level once, then duck it.
    try:
        if _mixer and _music_prev_vol is None and _mixer.music.get_busy():
            _music_prev_vol = _mixer.music.get_volume()
            _mixer.music.set_volume(_music_prev_vol * 0.2)
    except Exception:
        _music_prev_vol = None


def _restore_after_chime():
    """Put ambient + music back to their normal volumes once the chime ends."""
    global _music_prev_vol
    if current_sound is not None:
        try:
            current_sound.set_volume(_current_volume)
        except Exception:
            pass
    if _music_prev_vol is not None:
        try:
            _mixer.music.set_volume(_music_prev_vol)
        except Exception:
            pass
        _music_prev_vol = None


def play_chime():
    """One-shot chime for a task/schedule. It takes audio priority: the music
    player and ambience briefly duck so the chime is heard clearly, then their
    volumes are restored (chime > music > ambient)."""
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
        _duck_for_chime()
        snd.set_volume(min(1.0, _current_volume + 0.35))
        snd.play()
        dur = snd.get_length() or 0.8
    except Exception as e:
        print(f"[sound] Failed to play chime: {e}")
        _restore_after_chime()
        return
    # Restore the ducked audio shortly after the chime finishes.
    threading.Thread(target=lambda: (time.sleep(dur + 0.2), _restore_after_chime()),
                     daemon=True).start()


def stop_sound():
    """Stop whichever ambient sound is currently playing, if any."""
    global current_sound, _current_channel, _current_path
    if current_sound is not None:
        try:
            current_sound.stop()
        except Exception as e:
            print(f"[sound] Error stopping sound: {e}")
    current_sound = None
    _current_channel = None
    _current_path = None
    _release_ambient_lock()


# ---------------------------------------------------------
# Placeholder sound synthesis (stdlib only)
# ---------------------------------------------------------

_RATE = 22050

_GENERATED_SOUND_HASHES = {
    "clearday": {
        "a4ff4603cc28054a74de17056c75a409ed8dd4eb4a13c96e9f81b2241958fbb7",
        "bfed5cde79d2706cf37da0b64cc0423bfb76c6ddbf0fa0e4d445905a651addd8",
    },
    "clearnight": {
        "7cf6dada57dbad55da60efb012e7fb45b4924390e2ac717aabe98a239945efb0",
        "7ac6590c882d53b342cfc3c3b4cad229856010535f2467996513607a2602dda9",
    },
    "cloud": {
        "d214f8218ebf83813acc841b8ef147fd5686504f90d439daa424985769f5bd79",
        "4000669f12ffebabfd236f867fce53a59e0e7bc5a430a5f77141c782ae3bc36a",
    },
    "rain": {
        "3cf84b8667b2fd285b02de6bc58f015b052882f05f01e15c512c54fac0f944fb",
        "abed2495fa053a3c67453523bf66d53672255c872e04bace941779085d4acaab",
    },
    "storm": {
        "6b4c3e9c01d51068c59621daadfc67529005f9a458613e5350ef5afd75208137",
        "789efc1353994805d42785139d12d08b5792ca96acfc1a67ea92d066cebac0a1",
    },
}

_AMBIENT_SECONDS = {
    "rain": 12.0,
    "cloud": 14.0,
    "storm": 18.0,
    "clearday": 16.0,
    "clearnight": 16.0,
    "chime": 0.8,
}


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


def _noise(n, lp=0.0, rng=None):
    """White noise, optionally low-pass filtered (lp 0..1, higher=darker)."""
    out = []
    prev = 0.0
    for _ in range(n):
        x = (rng or random).uniform(-1, 1)
        if lp:
            prev = prev * lp + x * (1 - lp)
            x = prev
        out.append(x)
    return out


def _loop_noise(n, lp, rng):
    """Filtered repeating noise whose filter state settles before capture."""
    source = [rng.uniform(-1, 1) for _ in range(n)]
    out = []
    prev = 0.0
    for i in range(n * 3):
        prev = prev * lp + source[i % n] * (1.0 - lp)
        if i >= n * 2:
            out.append(prev)
    return out


def _add_call(samples, start, duration, low_hz, high_hz, amplitude):
    """Add one soft, tapered bird/cricket-like call."""
    first = max(0, int(start * _RATE))
    count = min(int(duration * _RATE), len(samples) - first)
    phase = 0.0
    for i in range(count):
        progress = i / max(1, count - 1)
        freq = low_hz + (high_hz - low_hz) * progress
        phase += 2 * math.pi * freq / _RATE
        envelope = math.sin(math.pi * progress) ** 2
        samples[first + i] += math.sin(phase) * amplitude * envelope


def _finish_loop(samples):
    """Fade loop edges to silence so pygame repetition cannot click."""
    fade = min(int(_RATE * 0.1), len(samples) // 4)
    for i in range(fade):
        gain = math.sin((math.pi / 2) * i / max(1, fade - 1)) ** 2
        samples[i] *= gain
        samples[-i - 1] *= gain
    return samples


def _synth(name, seconds=None):
    seconds = float(seconds or _AMBIENT_SECONDS.get(name, 12.0))
    n = int(_RATE * seconds)
    rng = random.Random(f"flow-relaxing-v2:{name}")
    if name == "rain":
        soft = _loop_noise(n, 0.72, rng)
        deep = _loop_noise(n, 0.96, rng)
        return _finish_loop([(soft[i] * 0.2 + deep[i] * 0.16)
                            * (0.88 + 0.12 * math.sin(2 * math.pi * i / n))
                            for i in range(n)])
    if name == "cloud":
        breeze = _loop_noise(n, 0.985, rng)
        air = _loop_noise(n, 0.94, rng)
        return _finish_loop([(breeze[i] * 0.75 + air[i] * 0.09)
                            * (0.7 + 0.3 * math.sin(2 * math.pi * i / n) ** 2)
                            for i in range(n)])
    if name == "storm":
        rain = _loop_noise(n, 0.8, rng)
        rumble = _loop_noise(n, 0.995, rng)
        out = [rain[i] * 0.1 + rumble[i] * 0.55 for i in range(n)]
        for start, duration in ((4.0, 3.0), (11.5, 4.0)):
            first = int(start * _RATE)
            count = min(int(duration * _RATE), n - first)
            for i in range(count):
                p = i / max(1, count - 1)
                env = math.sin(math.pi * p) ** 2
                t = i / _RATE
                out[first + i] += math.sin(2 * math.pi * 58 * t) * 0.09 * env
        return _finish_loop(out)
    if name == "clearday":
        breeze = _loop_noise(n, 0.98, rng)
        out = [s * 0.3 for s in breeze]
        for start, low, high in ((2.6, 1450, 2050), (7.8, 1750, 2250), (12.4, 1350, 1900)):
            _add_call(out, start, 0.32, low, high, 0.08)
            _add_call(out, start + 0.42, 0.24, high, low * 1.05, 0.06)
        return _finish_loop(out)
    if name == "clearnight":
        night_air = _loop_noise(n, 0.985, rng)
        out = [s * 0.28 for s in night_air]
        for group, freq in ((2.0, 2350), (7.2, 2550), (12.1, 2250)):
            for pulse in range(5):
                _add_call(out, group + pulse * 0.13, 0.075,
                          freq, freq * 1.04, 0.075)
        return _finish_loop(out)
    if name == "chime":
        out = []
        for i in range(int(_RATE * 0.8)):
            t = i / _RATE
            env = math.exp(-3 * t)
            out.append((math.sin(2 * math.pi * 880 * t)
                        + 0.5 * math.sin(2 * math.pi * 1320 * t)) * 0.3 * env)
        return out
    return _loop_noise(n, 0.9, rng)


def ensure_placeholder_sounds(directory=SOUNDS_DIR):
    """Create relaxing built-ins and migrate only known legacy generated WAVs."""
    created = []
    for name in ["rain", "cloud", "storm", "clearday", "clearnight", "chime"]:
        path = os.path.join(directory, f"{name}.wav")
        replace = not os.path.isfile(path)
        if not replace:
            try:
                with open(path, "rb") as f:
                    generated_hashes = _GENERATED_SOUND_HASHES.get(name, set())
                    replace = bool(
                        hashlib.sha256(f.read()).hexdigest() in generated_hashes)
            except OSError:
                replace = False
        if replace:
            _write_wav(path, _synth(name))
            created.append(path)
    return created
