"""
The engine ties everything together.

One ``tick`` resolves the effective weather, then applies the theme,
wallpaper and ambient sound (each gated by its feature flag) and fires any
due tasks. ``EngineThread`` runs that on a timer in the background for the
GUI; ``run_forever`` does the same for the headless ``--background`` mode.
"""

import os
import sys
import time
import random
import threading
import subprocess
import datetime

import config
import weather
import theme
import wallpaper
import sound
import music
import profiles
import audiocheck
import tasks as tasks_mod


# ---------------------------------------------------------
# System notification (for task actions)
# ---------------------------------------------------------

def notify(title: str, message: str):
    """Show a desktop pop-up for a fired reminder.

    Launched non-blocking (Popen) so a fired reminder never stalls the engine
    tick. On macOS we use ``display dialog`` rather than ``display
    notification`` — the latter is silently swallowed when the running process
    has no notification permission, which is why reminders never appeared; a
    dialog always pops up and auto-dismisses via ``giving up after``.
    """
    try:
        if sys.platform == "darwin":
            safe_msg = message.replace("\\", "").replace('"', "'")
            safe_title = title.replace("\\", "").replace('"', "'")
            script = (f'display dialog "{safe_msg}" with title "{safe_title}" '
                      f'buttons {{"OK"}} default button "OK" giving up after 20')
            subprocess.Popen(["osascript", "-e", script],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif sys.platform == "win32":
            ps = (f'[void][System.Reflection.Assembly]::LoadWithPartialName('
                  f'"System.Windows.Forms");'
                  f'[System.Windows.Forms.MessageBox]::Show("{message}","{title}")')
            subprocess.Popen(["powershell", "-NoProfile", "-Command", ps],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            print(f"[notify] {title}: {message}")
    except Exception as e:
        print(f"[notify] Failed: {e}")


# ---------------------------------------------------------
# Task actions
# ---------------------------------------------------------

def _run_task_action(task: dict, cfg: dict):
    """Run a task's action — either pop up a notification or play a chime."""
    action = task.get("action", "notify")
    title = task.get("title", "Task")

    if action == "chime":
        sound.play_chime()
    else:  # "notify" (and any legacy action) shows a pop-up
        notify("Flow", title)


# ---------------------------------------------------------
# One tick
# ---------------------------------------------------------

def tick(cfg: dict, store: "tasks_mod.TaskStore" = None,
         now: datetime.datetime = None) -> dict:
    """Run one full evaluation cycle. Returns a status dict for display."""
    now = now or datetime.datetime.now()
    status = {
        "time": now.isoformat(timespec="seconds"),
        "enabled": bool(cfg.get("enabled", True)),
        "applied": [],
        "fired_tasks": [],
    }

    if not cfg.get("enabled", True):
        sound.stop_sound()
        status["note"] = "master switch off"
        return status

    cfg = profiles.overlay_config(cfg, cfg.get("active_profile"))
    status["profile"] = (cfg.get("active_profile") or "none")

    eff = weather.get_effective_weather(cfg)
    condition = eff["condition"]
    is_night = eff["is_night"]
    status.update({
        "condition": condition,
        "is_night": is_night,
        "source": eff.get("source"),
        "condition_source": eff.get("condition_source"),
    })
    status.update({k: eff.get(k) for k in weather.MEASUREMENT_KEYS})

    # --- Resolve theme colour -----------------------------------------
    manual_time = (cfg.get("manual_time") or "auto").lower()
    phase = theme.normalize_phase(manual_time) if manual_time != "auto" else None
    night_override = None if manual_time == "auto" else is_night
    season = _season_now(cfg, now)
    hc = (cfg.get("accessibility_mode") or "none").lower() == "high_contrast"
    status["season"] = season

    manual_color = cfg.get("manual_theme_color")
    if manual_color and len(manual_color) == 3:
        r, g, b = manual_color
        brightness = theme.phase_light(phase)[0] if phase else (
            theme.NIGHT_BRIGHTNESS if is_night else 1.0)
        if hc:
            r, g, b = theme.high_contrast((r, g, b))
        status["color_source"] = "manual"
    else:
        (r, g, b), brightness = theme.compute_theme_color(
            condition, eff["sunrise"], eff["sunset"],
            is_night_override=night_override, phase=phase, now=now, season=season
        )
        r, g, b = _style_color((r, g, b), cfg)
        status["color_source"] = "computed"
    status["color"] = [r, g, b]
    status["phase"] = phase or theme.compute_day_phase(eff["sunrise"], eff["sunset"], now)
    status["brightness"] = round(brightness, 3)
    # Sky-body position: sun by day, moon by night (both arc east -> west).
    sun = theme.celestial_fraction(phase, eff["sunrise"], eff["sunset"], now)

    tint = 1.0 if hc else cfg.get("weather_tint_strength", 40) / 100.0

    # --- Apply theme ---------------------------------------------------
    if config.feature_enabled(cfg, "dynamic_theme"):
        desc = theme.apply_theme_color(r, g, b, brightness,
                                       cfg.get("appearance_mode", "auto"))
        status["applied"].append(f"theme: {desc}")

    # --- Apply wallpaper ----------------------------------------------
    if config.feature_enabled(cfg, "wallpaper"):
        pat_cond = _pattern_condition(condition, is_night)
        patterns = bool(cfg.get("wallpaper_patterns", True))
        warmth = bool(cfg.get("wallpaper_warmth", True))
        if wallpaper.apply_weather_wallpaper(
                r, g, b, brightness, tint, condition=pat_cond,
                temperature=eff.get("temperature"),
                patterns=patterns, warmth=warmth, sun=sun,
                multi=bool(cfg.get("multi_monitor", True))):
            status["applied"].append("wallpaper")
    elif wallpaper.is_showing_ours():
        # Feature off but a weather wallpaper is still showing — put the user's
        # real desktop back so it isn't left themed.
        if wallpaper.restore_original(multi=bool(cfg.get("multi_monitor", True))):
            status["applied"].append("wallpaper restored")

    # --- Ambient sound -------------------------------------------------
    if config.feature_enabled(cfg, "ambient_sound") and other_audio_playing(cfg):
        sound.stop_sound()
        status["note"] = "ambient paused — other audio playing"
    elif config.feature_enabled(cfg, "ambient_sound"):
        loop = (cfg.get("sound_mode") or "loop").lower() != "random"
        base = sound.ambient_base(condition, is_night, eff.get("wind_speed") or 0)
        path = sound.pick_base(base)
        sound.play_ambient(condition, is_night, cfg.get("sound_volume", 25),
                           path=path, loop=loop)
        status["applied"].append(f"sound: {os.path.basename(path)}")
    else:
        sound.stop_sound()

    # --- Tasks & schedules --------------------------------------------
    if config.feature_enabled(cfg, "tasks") and store is not None:
        for task in store.due_tasks(now):
            _run_task_action(task, cfg)
            store.mark_fired(task, now)
            status["fired_tasks"].append(task.get("title", task.get("id")))

    return status


# ---------------------------------------------------------
# Stateful engine  (optimised — cheap steps, work only on change)
# ---------------------------------------------------------

DRIFT_PERIOD = 600.0   # seconds for one full subtle wallpaper colour cycle


def _color_delta(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]), abs(a[2] - b[2]))


def _ease_rgb(cur, tgt, dt, duration):
    """Exponentially move *cur* toward *tgt*; converges in ~*duration* seconds."""
    tgt = tuple(int(c) for c in tgt)
    if cur is None or duration <= 0:
        return tgt
    a = 1.0 - 0.5 ** (dt / max(0.05, duration / 3.0))
    a = max(0.0, min(1.0, a))
    return tuple(cur[i] + (tgt[i] - cur[i]) * a for i in range(3))


def _season_now(cfg, now):
    """Season name for the configured hemisphere, or None when disabled."""
    if not cfg.get("seasonal_themes", True):
        return None
    lat = (cfg.get("location") or {}).get("lat")
    hemi = theme.hemisphere_for(lat, cfg.get("hemisphere", "auto"))
    return theme.season_for(now.date(), hemi)


def _style_color(rgb, cfg):
    """Apply the active profile's mood + the accessibility mode to a colour."""
    rgb = profiles.adjust_color(rgb, cfg.get("active_profile"))
    if (cfg.get("accessibility_mode") or "none").lower() == "high_contrast":
        rgb = theme.high_contrast(rgb)
    return tuple(int(c) for c in rgb)


def other_audio_playing(cfg):
    """
    True if the app should hold its ambient sound because higher-priority audio
    is playing. Priority is: scheduled chime > selected music > ambient — so our
    own music player ALWAYS pauses the ambience (they never play at once). Other
    apps (Spotify, etc.) only pause it when ``pause_when_other_audio`` is on.
    """
    try:
        if music.is_playing():          # our music always wins over ambience
            return True
    except Exception:
        pass
    if cfg.get("pause_when_other_audio", False):
        return bool(audiocheck.external_audio_active())
    return False


def _pattern_condition(condition, is_night):
    """
    The condition the *wallpaper* should draw. At night we show a night sky
    (unless it's actively raining/storming, which keep their own look), and a
    cloudy night gets its own moon-behind-clouds look so it differs from clear.
    """
    c = (condition or "").lower()
    if is_night and not any(k in c for k in ("rain", "storm")):
        return "cloudnight" if "cloud" in c else "night"
    return condition


class Engine:
    """
    Holds state between steps so each step is cheap:
      * live weather is refetched only every ``weather_refresh_seconds``;
      * theme / sound are re-applied only when the visible result changes;
      * the wallpaper redraws only when its colour drifts past a threshold
        and no more often than ``wallpaper_min_interval_seconds``.
    The dynamic colour drift is a smooth function of the clock, so it keeps
    moving without any busy loop.
    """

    def __init__(self):
        self._weather = None
        self._live = None              # last live measurements (unaffected by overrides)
        self._weather_at = None
        self._live_loc = None          # (lat, lon) the cached live weather is for
        self._last_theme = None        # theme signature last applied
        self._last_sound = None        # ambient path last played
        self._sound_on = False
        self._sound_base = None        # ambient base currently selected
        self._next_sound_at = None     # random mode: when to play next
        self._last_wall_key = None     # (drifted_rgb, brightness_bucket) last drawn
        self._last_wall_at = None
        self._last_sun = None          # sun/moon fraction last drawn (for tracking)
        self._wall_active = False       # we've been setting the weather wallpaper
        self._wall_off_handled = False  # restored the original since the feature went off
        self._eased_rgb = None         # displayed colour, eased toward target
        self._eased_at = None          # when the eased colour was last updated
        self.transitioning = False     # True while a colour cross-fade is in progress

    # --- weather (cached) ---------------------------------------------
    def _effective(self, cfg, now):
        """
        Live measurements are fetched only every ``weather_refresh_seconds``
        and cached — *regardless* of manual overrides, so the real data keeps
        flowing while the user forces a look. The manual condition/time
        overrides are re-applied cheaply on top every step.
        """
        refresh = max(30, int(cfg.get("weather_refresh_seconds", 600)))
        loc = weather.location_coords(cfg)
        stale = (self._live is None or self._weather_at is None
                 or self._live.get("source") == "fallback"
                 or loc != self._live_loc            # city changed -> refetch now
                 or (now - self._weather_at).total_seconds() >= refresh)
        if stale:
            self._live = weather.get_live_weather(cfg)
            self._weather_at = now
            self._live_loc = loc
        self._weather = weather.apply_overrides(self._live, cfg, now)
        return self._weather

    def _phase(self, now):
        secs = now.hour * 3600 + now.minute * 60 + now.second
        return (secs % DRIFT_PERIOD) / DRIFT_PERIOD

    # --- one cheap step -----------------------------------------------
    def step(self, cfg, store=None, now=None):
        now = now or datetime.datetime.now()
        status = {
            "time": now.isoformat(timespec="seconds"),
            "enabled": bool(cfg.get("enabled", True)),
            "applied": [],
            "fired_tasks": [],
        }

        if not cfg.get("enabled", True):
            if self._sound_on:
                sound.stop_sound()
                self._sound_on = False
            status["note"] = "master switch off"
            return status

        # Active mood profile overlays sound volume + motion.
        cfg = profiles.overlay_config(cfg, cfg.get("active_profile"))
        status["profile"] = (cfg.get("active_profile") or "none")

        eff = self._effective(cfg, now)
        condition, is_night = eff["condition"], eff["is_night"]
        status.update({"condition": condition, "is_night": is_night,
                       "source": eff.get("source"),
                       "condition_source": eff.get("condition_source")})
        status.update({k: eff.get(k) for k in weather.MEASUREMENT_KEYS})

        manual_time = (cfg.get("manual_time") or "auto").lower()
        phase = theme.normalize_phase(manual_time) if manual_time != "auto" else None
        night_override = None if manual_time == "auto" else is_night
        season = _season_now(cfg, now)
        hc = (cfg.get("accessibility_mode") or "none").lower() == "high_contrast"
        status["season"] = season
        manual_color = cfg.get("manual_theme_color")
        is_manual = bool(manual_color and len(manual_color) == 3)
        if is_manual:
            tr, tg, tb = manual_color
            brightness = theme.phase_light(phase)[0] if phase else (
                theme.NIGHT_BRIGHTNESS if is_night else 1.0)
            if hc:                                  # accessibility still applies
                tr, tg, tb = theme.high_contrast((tr, tg, tb))
            status["color_source"] = "manual"
        else:
            (tr, tg, tb), brightness = theme.compute_theme_color(
                condition, eff["sunrise"], eff["sunset"],
                is_night_override=night_override, phase=phase, now=now, season=season)
            tr, tg, tb = _style_color((tr, tg, tb), cfg)   # profile mood + a11y
            status["color_source"] = "computed"

        # Gradual transitions: ease the *displayed* colour toward the target so
        # weather/time changes cross-fade instead of snapping. A manually picked
        # colour is a deliberate choice, so it snaps to full strength at once
        # (no cross-fade) — otherwise the picker looks like it does nothing.
        smooth = bool(cfg.get("smooth_transitions", True)) and not is_manual
        dur = max(0, int(cfg.get("theme_transition_seconds", 8)))
        if smooth and dur > 0:
            dt = (now - self._eased_at).total_seconds() if self._eased_at else dur
            self._eased_rgb = _ease_rgb(self._eased_rgb, (tr, tg, tb), dt, dur)
        else:
            self._eased_rgb = (float(tr), float(tg), float(tb))
        self._eased_at = now
        r, g, b = (int(round(c)) for c in self._eased_rgb)
        self.transitioning = smooth and _color_delta((r, g, b), (tr, tg, tb)) >= 2

        status["color"] = [r, g, b]
        status["target_color"] = [tr, tg, tb]
        status["phase"] = phase or theme.compute_day_phase(eff["sunrise"], eff["sunset"], now)
        status["brightness"] = round(brightness, 3)
        # Sky-body position: sun by day, moon by night (both arc east -> west).
        sun = theme.celestial_fraction(phase, eff["sunrise"], eff["sunset"], now)
        tint = 1.0 if hc else cfg.get("weather_tint_strength", 40) / 100.0

        # --- theme: apply only when the visible signature changes ------
        if config.feature_enabled(cfg, "dynamic_theme"):
            appearance = cfg.get("appearance_mode", "auto")
            sig = theme.theme_signature(r, g, b, brightness, appearance)
            if sig != self._last_theme:
                desc = theme.apply_theme_color(r, g, b, brightness, appearance)
                self._last_theme = sig
                status["applied"].append(f"theme: {desc}")

        # --- wallpaper: subtle drift, guarded by delta + interval ------
        if config.feature_enabled(cfg, "wallpaper"):
            self._wall_active = True
            self._wall_off_handled = False
            dynamic = bool(cfg.get("wallpaper_dynamic", True))
            shift = (cfg.get("wallpaper_shift_strength", 35) / 100.0) if dynamic else 0.0
            patterns = bool(cfg.get("wallpaper_patterns", True))
            warmth = bool(cfg.get("wallpaper_warmth", True))
            pat_cond = _pattern_condition(condition, is_night)
            phase = self._phase(now)
            target = wallpaper.shifted_base(r, g, b, tint, phase, shift)
            bucket = round(brightness, 2)
            min_iv = max(5, int(cfg.get("wallpaper_min_interval_seconds", 45)))
            elapsed = (None if self._last_wall_at is None
                       else (now - self._last_wall_at).total_seconds())
            due = elapsed is None or elapsed >= min_iv
            # A moving pattern is worth a redraw on the interval even when the
            # base colour is steady (e.g. manual rain) — the raindrops shift.
            moving = dynamic and patterns and wallpaper.is_animated(pat_cond)
            # Redraw as the sun/moon creeps across the sky, so it tracks the
            # real sky instead of jumping — small threshold => gentle steps.
            sun_moved = (patterns and sun is not None
                         and (self._last_sun is None
                              or abs(sun - self._last_sun) >= 0.006))
            changed = (self._last_wall_key is None
                       or self._last_wall_key[1] != bucket
                       or moving
                       or sun_moved
                       or _color_delta(target, self._last_wall_key[0]) >= 2)
            # Periodically re-apply even when nothing changed. macOS only
            # sets the *current* Space's wallpaper, so a set made while a
            # fullscreen app is focused never reaches the normal desktop —
            # this forces the visible Space to catch up after you return.
            refresh = int(cfg.get("wallpaper_refresh_seconds", 90))
            force = (refresh > 0 and elapsed is not None
                     and elapsed >= max(min_iv, refresh))
            if (due and changed) or force:
                if wallpaper.apply_weather_wallpaper(
                        r, g, b, brightness, tint, phase=phase, shift_strength=shift,
                        condition=pat_cond, temperature=eff.get("temperature"),
                        patterns=patterns, warmth=warmth, sun=sun,
                        multi=bool(cfg.get("multi_monitor", True))):
                    self._last_wall_key = (target, bucket)
                    self._last_wall_at = now
                    self._last_sun = sun
                    status["applied"].append("wallpaper")
        else:
            # Weather wallpaper turned off: put the user's real desktop back so
            # it doesn't stay themed. Do it once per off-period — including when
            # a weather wallpaper is left over from a previous run — and never
            # fight a wallpaper the user sets themselves afterwards.
            if not self._wall_off_handled:
                if self._wall_active or wallpaper.is_showing_ours():
                    if wallpaper.restore_original(
                            multi=bool(cfg.get("multi_monitor", True))):
                        status["applied"].append("wallpaper restored")
                    self._last_wall_key = None
                    self._last_wall_at = None
                self._wall_active = False
                self._wall_off_handled = True

        # --- sound: loop continuously, or play a random clip now and then --
        if config.feature_enabled(cfg, "ambient_sound") and other_audio_playing(cfg):
            # Something else is playing — get out of the way, resume later.
            if self._sound_on:
                sound.stop_sound()
                self._sound_on = False
            self._sound_base = None
            status["note"] = "ambient paused — other audio playing"
        elif config.feature_enabled(cfg, "ambient_sound"):
            wind = eff.get("wind_speed") or 0
            base = sound.ambient_base(condition, is_night, wind)
            vol = cfg.get("sound_volume", 25)
            mode = (cfg.get("sound_mode") or "loop").lower()
            base_changed = base != self._sound_base

            if mode == "random":
                # No continuous loop — stop any looping ambience first.
                if self._sound_on:
                    sound.stop_sound()
                    self._sound_on = False
                due = self._next_sound_at is None or now >= self._next_sound_at
                if due or base_changed:
                    path = sound.pick_base(base)
                    sound.play_ambient(condition, is_night, vol, path=path, loop=False)
                    self._sound_base = base
                    self._last_sound = path
                    iv = max(1, int(cfg.get("sound_interval_minutes", 5)))
                    # Jitter the gap (±30%) so it never feels metronomic.
                    gap = iv * 60 * (0.7 + 0.6 * random.random())
                    self._next_sound_at = now + datetime.timedelta(seconds=gap)
                    status["applied"].append(f"sound(once): {os.path.basename(path)}")
            else:  # loop
                self._next_sound_at = None
                if base_changed or not self._sound_on:
                    path = sound.pick_base(base)
                    sound.play_ambient(condition, is_night, vol, path=path, loop=True)
                    self._sound_base = base
                    self._sound_on = True
                    self._last_sound = path
                    status["applied"].append(f"sound: {os.path.basename(path)}")
                else:
                    sound.set_volume(vol)
        elif self._sound_on:
            sound.stop_sound()
            self._sound_on = False
            self._sound_base = None

        # --- tasks ------------------------------------------------------
        if config.feature_enabled(cfg, "tasks") and store is not None:
            for task in store.due_tasks(now):
                _run_task_action(task, cfg)
                store.mark_fired(task, now)
                status["fired_tasks"].append(task.get("title", task.get("id")))

        return status


# ---------------------------------------------------------
# Background runners
# ---------------------------------------------------------

class EngineThread(threading.Thread):
    """
    Drives :class:`Engine` on a short cadence. Reloads config + tasks from
    disk each cycle so GUI edits take effect without a restart.
    """

    def __init__(self, config_path=config.CONFIG_FILE,
                 tasks_path=tasks_mod.TASKS_FILE, on_status=None):
        super().__init__(daemon=True)
        self.config_path = config_path
        self.tasks_path = tasks_path
        self.on_status = on_status
        self.engine = Engine()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self.last_status = None
        self._last_full = None      # monotonic time of the last full evaluation

    def stop(self):
        self._stop.set()
        self._wake.set()

    def wake(self):
        """Force an immediate re-evaluation (e.g. after Apply Now)."""
        self._last_full = None
        self._wake.set()

    def run(self):
        while not self._stop.is_set():
            cfg = config.load_config(self.config_path)
            store = tasks_mod.TaskStore(self.tasks_path)
            now = datetime.datetime.now()
            mono = time.monotonic()
            tick_iv = max(5, int(cfg.get("tick_interval_seconds", 30)))

            # Step often while a colour cross-fade is in progress so the
            # transition is smooth; otherwise on the normal cadence.
            full_iv = 0.5 if self.engine.transitioning else tick_iv
            if self._last_full is None or (mono - self._last_full) >= full_iv:
                try:
                    self.last_status = self.engine.step(cfg, store, now)
                    if self.on_status:
                        self.on_status(self.last_status)
                except Exception as e:
                    print(f"[engine] step failed: {e}")
                self._last_full = mono

            sleep = 0.5 if self.engine.transitioning else tick_iv
            self._wake.wait(timeout=max(0.05, sleep))
            self._wake.clear()
        sound.stop_sound()


def run_forever(config_path=config.CONFIG_FILE, tasks_path=tasks_mod.TASKS_FILE):
    """Headless loop used by ``main.py --background``."""
    print("[engine] Background mode started.")
    eng = Engine()
    last_full = None
    try:
        while True:
            cfg = config.load_config(config_path)
            store = tasks_mod.TaskStore(tasks_path)
            mono = time.monotonic()
            tick_iv = max(5, int(cfg.get("tick_interval_seconds", 30)))

            full_iv = 0.5 if eng.transitioning else tick_iv
            if last_full is None or (mono - last_full) >= full_iv:
                try:
                    eng.step(cfg, store)
                except Exception as e:
                    print(f"[engine] step failed: {e}")
                last_full = mono

            sleep = 0.5 if eng.transitioning else tick_iv
            time.sleep(max(0.05, sleep))
    except KeyboardInterrupt:
        sound.stop_sound()
        print("[engine] Background mode stopped.")
