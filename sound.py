import os

# Defer pygame import so an audio initialisation failure doesn't crash the
# entire application at import time.
_pygame_available = False
_mixer = None

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

    return _pygame_available


current_sound = None


def play_sound(file: str):
    """Play a looping ambient sound, stopping any previously playing sound."""
    global current_sound

    if not _ensure_mixer():
        return  # audio not available — silently skip

    if not os.path.isfile(file):
        print(f"[sound] Sound file not found, skipping: {file!r}")
        return

    # Don't restart the same file if it's already playing
    if current_sound is not None:
        try:
            if current_sound.get_num_channels() > 0:
                # Check if the same file is queued — pygame Sound doesn't
                # expose the filename, so we track it ourselves.
                if getattr(current_sound, "_source_path", None) == file:
                    return
        except Exception:
            pass
        try:
            current_sound.stop()
        except Exception:
            pass

    try:
        snd = _mixer.Sound(file)
        snd._source_path = file   # store for dedup check above
        snd.play(loops=-1)
        current_sound = snd
        print(f"[sound] Playing: {file}")
    except Exception as e:
        print(f"[sound] Failed to play {file!r}: {e}")


def stop_sound():
    """Stop whichever ambient sound is currently playing, if any."""
    global current_sound
    if current_sound is not None:
        try:
            current_sound.stop()
        except Exception as e:
            print(f"[sound] Error stopping sound: {e}")
        current_sound = None