"""
The engine ties everything together.

One ``tick`` resolves the effective weather, then applies the theme,
wallpaper and ambient sound (each gated by its feature flag) and fires any
due tasks. ``EngineThread`` runs that on a timer in the background for the
GUI; ``run_forever`` does the same for the headless ``--background`` mode.
"""

import sys
import time
import threading
import subprocess
import datetime

import config
import weather
import theme
import wallpaper
import sound
import tasks as tasks_mod


# ---------------------------------------------------------
# System notification (for task actions)
# ---------------------------------------------------------

def notify(title: str, message: str):
    try:
        if sys.platform == "darwin":
            subprocess.run(
                ["osascript", "-e",
                 f'display notification "{message}" with title "{title}"'],
                capture_output=True, text=True, timeout=5,
            )
        elif sys.platform == "win32":
            ps = (f'[void][System.Reflection.Assembly]::LoadWithPartialName('
                  f'"System.Windows.Forms");'
                  f'[System.Windows.Forms.MessageBox]::Show("{message}","{title}")')
            subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, timeout=10)
        else:
            print(f"[notify] {title}: {message}")
    except Exception as e:
        print(f"[notify] Failed: {e}")


# ---------------------------------------------------------
# Task actions
# ---------------------------------------------------------

def _run_task_action(task: dict, cfg: dict):
    action = task.get("action", "notify")
    value = task.get("action_value", "")
    title = task.get("title", "Task")

    if action == "notify":
        notify("Environment Theme Controller", title)
    elif action == "chime":
        sound.play_chime()
    elif action == "set_weather":
        if value in weather.CONDITIONS or value == "auto":
            cfg["manual_weather"] = value
            config.save_config(cfg)
            print(f"[engine] Task {title!r} set manual_weather={value}")
    elif action == "set_theme":
        try:
            rgb = [int(x) for x in str(value).split(",")]
            if len(rgb) == 3:
                cfg["manual_theme_color"] = rgb
                config.save_config(cfg)
                print(f"[engine] Task {title!r} set manual_theme_color={rgb}")
        except ValueError:
            print(f"[engine] Task {title!r} bad set_theme value: {value!r}")


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

    eff = weather.get_effective_weather(cfg)
    condition = eff["condition"]
    is_night = eff["is_night"]
    status.update({
        "condition": condition,
        "is_night": is_night,
        "source": eff.get("source"),
    })

    # --- Resolve theme colour -----------------------------------------
    manual_time = (cfg.get("manual_time") or "auto").lower()
    night_override = None if manual_time == "auto" else is_night

    manual_color = cfg.get("manual_theme_color")
    if manual_color and len(manual_color) == 3:
        r, g, b = manual_color
        brightness = theme.NIGHT_BRIGHTNESS if is_night else 1.0
        status["color_source"] = "manual"
    else:
        (r, g, b), brightness = theme.compute_theme_color(
            condition, eff["sunrise"], eff["sunset"], is_night_override=night_override
        )
        status["color_source"] = "computed"
    status["color"] = [r, g, b]
    status["brightness"] = round(brightness, 3)

    tint = cfg.get("weather_tint_strength", 40) / 100.0

    # --- Apply theme ---------------------------------------------------
    if config.feature_enabled(cfg, "dynamic_theme"):
        desc = theme.apply_theme_color(r, g, b, brightness)
        status["applied"].append(f"theme: {desc}")

    # --- Apply wallpaper ----------------------------------------------
    if config.feature_enabled(cfg, "wallpaper"):
        if wallpaper.apply_weather_wallpaper(r, g, b, brightness, tint):
            status["applied"].append("wallpaper")

    # --- Ambient sound -------------------------------------------------
    if config.feature_enabled(cfg, "ambient_sound"):
        sound.play_ambient(condition, is_night, cfg.get("sound_volume", 25))
        status["applied"].append(f"sound: {sound.select_ambient(condition, is_night)}")
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
        self._weather_at = None
        self._last_theme = None        # theme signature last applied
        self._last_sound = None        # ambient path last played
        self._sound_on = False
        self._last_wall_key = None     # (drifted_rgb, brightness_bucket) last drawn
        self._last_wall_at = None

    # --- weather (cached) ---------------------------------------------
    def _effective(self, cfg, now):
        manual_w = (cfg.get("manual_weather") or "auto").lower()
        manual_t = (cfg.get("manual_time") or "auto").lower()

        # Manual weather needs no network — always cheap to recompute.
        if manual_w != "auto":
            self._weather = weather.get_effective_weather(cfg)
            self._weather_at = now
            return self._weather

        refresh = max(30, int(cfg.get("weather_refresh_seconds", 600)))
        stale = (self._weather is None or self._weather_at is None
                 or self._weather.get("source") == "fallback"
                 or (now - self._weather_at).total_seconds() >= refresh)
        if stale:
            self._weather = weather.get_effective_weather(cfg)
            self._weather_at = now
        else:
            # Re-evaluate only the cheap, time-dependent bits each step.
            w = self._weather
            if manual_t == "night":
                w["is_night"] = True
            elif manual_t == "day":
                w["is_night"] = False
            else:
                w["is_night"] = weather._is_night(w["sunrise"], w["sunset"], now)
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

        eff = self._effective(cfg, now)
        condition, is_night = eff["condition"], eff["is_night"]
        status.update({"condition": condition, "is_night": is_night,
                       "source": eff.get("source")})

        manual_time = (cfg.get("manual_time") or "auto").lower()
        night_override = None if manual_time == "auto" else is_night
        manual_color = cfg.get("manual_theme_color")
        if manual_color and len(manual_color) == 3:
            r, g, b = manual_color
            brightness = theme.NIGHT_BRIGHTNESS if is_night else 1.0
            status["color_source"] = "manual"
        else:
            (r, g, b), brightness = theme.compute_theme_color(
                condition, eff["sunrise"], eff["sunset"], is_night_override=night_override)
            status["color_source"] = "computed"
        status["color"] = [r, g, b]
        status["brightness"] = round(brightness, 3)
        tint = cfg.get("weather_tint_strength", 40) / 100.0

        # --- theme: apply only when the visible signature changes ------
        if config.feature_enabled(cfg, "dynamic_theme"):
            sig = theme.theme_signature(r, g, b, brightness)
            if sig != self._last_theme:
                desc = theme.apply_theme_color(r, g, b, brightness)
                self._last_theme = sig
                status["applied"].append(f"theme: {desc}")

        # --- wallpaper: subtle drift, guarded by delta + interval ------
        if config.feature_enabled(cfg, "wallpaper"):
            dynamic = bool(cfg.get("wallpaper_dynamic", True))
            shift = (cfg.get("wallpaper_shift_strength", 35) / 100.0) if dynamic else 0.0
            phase = self._phase(now)
            target = wallpaper.shifted_base(r, g, b, tint, phase, shift)
            bucket = round(brightness, 2)
            min_iv = max(5, int(cfg.get("wallpaper_min_interval_seconds", 45)))
            due = (self._last_wall_at is None
                   or (now - self._last_wall_at).total_seconds() >= min_iv)
            changed = (self._last_wall_key is None
                       or self._last_wall_key[1] != bucket
                       or _color_delta(target, self._last_wall_key[0]) >= 2)
            if due and changed:
                if wallpaper.apply_weather_wallpaper(r, g, b, brightness, tint,
                                                     phase=phase, shift_strength=shift):
                    self._last_wall_key = (target, bucket)
                    self._last_wall_at = now
                    status["applied"].append("wallpaper")

        # --- sound: (re)start only when the chosen file changes --------
        if config.feature_enabled(cfg, "ambient_sound"):
            path = sound.select_ambient(condition, is_night)
            if path != self._last_sound or not self._sound_on:
                sound.play_ambient(condition, is_night, cfg.get("sound_volume", 25))
                self._last_sound = path
                self._sound_on = True
                status["applied"].append(f"sound: {path}")
            else:
                sound.set_volume(cfg.get("sound_volume", 25))
        elif self._sound_on:
            sound.stop_sound()
            self._sound_on = False

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

    def stop(self):
        self._stop.set()
        self._wake.set()

    def wake(self):
        """Force an immediate re-evaluation (e.g. after Apply Now)."""
        self._wake.set()

    def run(self):
        while not self._stop.is_set():
            cfg = config.load_config(self.config_path)
            store = tasks_mod.TaskStore(self.tasks_path)
            try:
                self.last_status = self.engine.step(cfg, store)
                if self.on_status:
                    self.on_status(self.last_status)
            except Exception as e:
                print(f"[engine] step failed: {e}")
            interval = max(5, int(cfg.get("tick_interval_seconds", 30)))
            self._wake.wait(timeout=interval)
            self._wake.clear()
        sound.stop_sound()


def run_forever(config_path=config.CONFIG_FILE, tasks_path=tasks_mod.TASKS_FILE):
    """Headless loop used by ``main.py --background``."""
    print("[engine] Background mode started.")
    eng = Engine()
    try:
        while True:
            cfg = config.load_config(config_path)
            store = tasks_mod.TaskStore(tasks_path)
            try:
                eng.step(cfg, store)
            except Exception as e:
                print(f"[engine] step failed: {e}")
            time.sleep(max(5, int(cfg.get("tick_interval_seconds", 30))))
    except KeyboardInterrupt:
        sound.stop_sound()
        print("[engine] Background mode stopped.")
