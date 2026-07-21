"""
Simple background music player with generated samples and your own songs.

Plays audio files (mp3 / ogg / wav / flac) from the ``music/`` folder using
pygame's streaming music channel. Music takes priority over weather ambience.
Degrades silently when pygame/audio is unavailable.
"""

import math
import os
import struct
import threading
import time
import wave

import sound  # reuse the shared pygame.mixer initialisation
import processlock

MUSIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "music")
AUDIO_EXTS = (".mp3", ".ogg", ".wav", ".flac", ".m4a")
SAMPLE_TRACKS = (
    "Flow Sample - Morning Focus.wav",
    "Flow Sample - Evening Calm.wav",
)

_playlist = []      # list of file paths currently queued
_index = -1         # index into _playlist of the current track
_paused = False
_watch_generation = 0
_music_lock = processlock.ProcessFileLock(
    processlock.path("music", MUSIC_DIR))


def _start_end_watcher():
    global _watch_generation
    _watch_generation += 1
    generation = _watch_generation

    def watch():
        while generation == _watch_generation:
            time.sleep(0.5)
            mixer = sound._mixer
            try:
                busy = mixer not in (None, False) and mixer.music.get_busy()
            except Exception:
                busy = False
            if not busy:
                if generation == _watch_generation:
                    _music_lock.release()
                return

    threading.Thread(target=watch, daemon=True).start()


def _stop_end_watcher():
    global _watch_generation
    _watch_generation += 1


def ensure_dir():
    os.makedirs(MUSIC_DIR, exist_ok=True)


def _write_sample_track(path, chords, melody):
    """Create a short, original ambient music sample using stdlib only."""
    rate = 22050
    duration = 12
    chord_seconds = 3.0
    frames = bytearray()
    total = rate * duration
    for i in range(total):
        t = i / rate
        chord_index = min(len(chords) - 1, int(t / chord_seconds))
        chord_t = t % chord_seconds
        chord_fade = min(1.0, chord_t * 3.0, (chord_seconds - chord_t) * 3.0)
        chord = chords[chord_index]
        pad = sum(math.sin(2 * math.pi * freq * t) for freq in chord) / len(chord)

        note_seconds = 0.75
        note_index = int(t / note_seconds) % len(melody)
        note_t = t % note_seconds
        note_env = math.sin(math.pi * note_t / note_seconds) ** 2
        bell = math.sin(2 * math.pi * melody[note_index] * t)
        bell += 0.25 * math.sin(4 * math.pi * melody[note_index] * t)

        edge = min(1.0, t / 0.25, (duration - t) / 0.25)
        sample = edge * (0.16 * chord_fade * pad + 0.075 * note_env * bell)
        frames.extend(struct.pack("<h", int(max(-1.0, min(1.0, sample)) * 32767)))

    tmp = path + ".tmp"
    with wave.open(tmp, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(frames)
    os.replace(tmp, path)


def ensure_sample_tracks(directory=MUSIC_DIR):
    """Seed an empty music folder with two original, copyright-free samples."""
    os.makedirs(directory, exist_ok=True)
    try:
        if any(name.lower().endswith(AUDIO_EXTS) for name in os.listdir(directory)):
            return []
    except OSError:
        return []

    arrangements = (
        (
            ((130.81, 164.81, 196.00, 246.94),
             (110.00, 130.81, 164.81, 196.00),
             (87.31, 130.81, 174.61, 220.00),
             (98.00, 146.83, 196.00, 246.94)),
            (523.25, 659.25, 783.99, 659.25, 587.33, 659.25, 523.25, 493.88),
        ),
        (
            ((146.83, 174.61, 220.00, 261.63),
             (116.54, 146.83, 174.61, 220.00),
             (87.31, 130.81, 174.61, 220.00),
             (130.81, 164.81, 196.00, 246.94)),
            (440.00, 523.25, 587.33, 523.25, 392.00, 440.00, 349.23, 392.00),
        ),
    )
    created = []
    for name, (chords, melody) in zip(SAMPLE_TRACKS, arrangements):
        path = os.path.join(directory, name)
        _write_sample_track(path, chords, melody)
        created.append(path)
    return created


def list_tracks(directory=MUSIC_DIR):
    """Audio files in *directory*, sorted by name."""
    if os.path.abspath(directory) == os.path.abspath(MUSIC_DIR):
        ensure_sample_tracks(directory)
    try:
        names = sorted(os.listdir(directory))
    except OSError:
        return []
    return [os.path.join(directory, n) for n in names
            if n.lower().endswith(AUDIO_EXTS)]


def _pg():
    """pygame module with the mixer initialised, or None if unavailable."""
    if not sound._ensure_mixer():
        return None
    try:
        import pygame
        return pygame
    except Exception:
        return None


def play(path, volume=None):
    """Load and play a single file. Returns True on success."""
    global _paused
    pg = _pg()
    if not pg:
        return False
    if not os.path.isfile(path):
        print(f"[music] File not found: {path}")
        return False
    if not _music_lock.acquire():
        return False
    try:
        pg.mixer.music.load(path)
        if volume is not None:
            pg.mixer.music.set_volume(max(0.0, min(1.0, volume / 100.0)))
        pg.mixer.music.play()
        _paused = False
        _start_end_watcher()
        print(f"[music] Playing: {os.path.basename(path)}")
        return True
    except Exception as e:
        print(f"[music] Could not play {os.path.basename(path)}: {e}")
        _music_lock.release()
        return False


def play_list(tracks, index=0, volume=None):
    """Set the playlist and start at *index*."""
    global _playlist, _index
    _playlist = list(tracks)
    if not _playlist:
        return False
    _index = max(0, min(index, len(_playlist) - 1))
    return play(_playlist[_index], volume)


def toggle_pause():
    mixer = sound._mixer
    if mixer in (None, False):
        return
    global _paused
    if _paused:
        if not _music_lock.acquire():
            return
        mixer.music.unpause()
        _paused = False
        _start_end_watcher()
    else:
        mixer.music.pause()
        _paused = True
        _stop_end_watcher()
        _music_lock.release()


def stop():
    global _playlist, _index, _paused
    mixer = sound._mixer
    if mixer not in (None, False):
        try:
            mixer.music.stop()
        except Exception:
            pass
    _playlist, _index, _paused = [], -1, False
    _stop_end_watcher()
    _music_lock.release()


def set_volume(volume):
    mixer = sound._mixer
    if mixer not in (None, False):
        try:
            mixer.music.set_volume(max(0.0, min(1.0, volume / 100.0)))
        except Exception:
            pass


def next_track(volume=None):
    global _index
    if not _playlist:
        return False
    _index = (_index + 1) % len(_playlist)
    return play(_playlist[_index], volume)


def prev_track(volume=None):
    global _index
    if not _playlist:
        return False
    _index = (_index - 1) % len(_playlist)
    return play(_playlist[_index], volume)


def current():
    return _playlist[_index] if 0 <= _index < len(_playlist) else None


def has_playlist():
    return bool(_playlist)


def is_paused():
    return _paused


def is_playing():
    mixer = sound._mixer
    if mixer in (None, False):
        return False
    try:
        playing = bool(mixer.music.get_busy()) and not _paused
        if not playing and _music_lock.owned:
            _music_lock.release()
        return playing
    except Exception:
        if _music_lock.owned:
            _music_lock.release()
        return False


def is_playing_anywhere():
    """Whether Flow music is active in this or another app process."""
    return is_playing() or _music_lock.held_elsewhere()


def open_folder(directory=MUSIC_DIR):
    """Reveal the music folder in the OS file manager."""
    import sys
    import subprocess
    ensure_dir()
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
        print(f"[music] Could not open folder: {e}")
        return False
