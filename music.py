"""
Simple background music player for your own downloaded songs.

Plays audio files (mp3 / ogg / wav / flac) from the ``music/`` folder using
pygame's streaming music channel — independent of, and mixable with, the
weather ambience. Degrades silently when pygame/audio is unavailable.
"""

import os

import sound  # reuse the shared pygame.mixer initialisation

MUSIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "music")
AUDIO_EXTS = (".mp3", ".ogg", ".wav", ".flac", ".m4a")

_playlist = []      # list of file paths currently queued
_index = -1         # index into _playlist of the current track
_paused = False


def ensure_dir():
    os.makedirs(MUSIC_DIR, exist_ok=True)


def list_tracks(directory=MUSIC_DIR):
    """Audio files in *directory*, sorted by name."""
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
    try:
        pg.mixer.music.load(path)
        if volume is not None:
            pg.mixer.music.set_volume(max(0.0, min(1.0, volume / 100.0)))
        pg.mixer.music.play()
        _paused = False
        print(f"[music] Playing: {os.path.basename(path)}")
        return True
    except Exception as e:
        print(f"[music] Could not play {os.path.basename(path)}: {e}")
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
    pg = _pg()
    if not pg:
        return
    global _paused
    if _paused:
        pg.mixer.music.unpause()
        _paused = False
    else:
        pg.mixer.music.pause()
        _paused = True


def stop():
    global _playlist, _index, _paused
    pg = _pg()
    if pg:
        try:
            pg.mixer.music.stop()
        except Exception:
            pass
    _playlist, _index, _paused = [], -1, False


def set_volume(volume):
    pg = _pg()
    if pg:
        try:
            pg.mixer.music.set_volume(max(0.0, min(1.0, volume / 100.0)))
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
    pg = _pg()
    if not pg:
        return False
    try:
        return bool(pg.mixer.music.get_busy()) and not _paused
    except Exception:
        return False


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
