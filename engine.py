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
# Background runners
# ---------------------------------------------------------

class EngineThread(threading.Thread):
    """
    Runs :func:`tick` on a timer. Reloads config + tasks from disk each
    cycle so changes saved by the GUI take effect without a restart.
    """

    def __init__(self, config_path=config.CONFIG_FILE,
                 tasks_path=tasks_mod.TASKS_FILE, on_status=None):
        super().__init__(daemon=True)
        self.config_path = config_path
        self.tasks_path = tasks_path
        self.on_status = on_status
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
                self.last_status = tick(cfg, store)
                if self.on_status:
                    self.on_status(self.last_status)
            except Exception as e:
                print(f"[engine] tick failed: {e}")
            interval = max(5, int(cfg.get("poll_interval_seconds", 300)))
            self._wake.wait(timeout=interval)
            self._wake.clear()
        sound.stop_sound()


def run_forever(config_path=config.CONFIG_FILE, tasks_path=tasks_mod.TASKS_FILE):
    """Headless loop used by ``main.py --background``."""
    print("[engine] Background mode started.")
    try:
        while True:
            cfg = config.load_config(config_path)
            store = tasks_mod.TaskStore(tasks_path)
            try:
                tick(cfg, store)
            except Exception as e:
                print(f"[engine] tick failed: {e}")
            time.sleep(max(5, int(cfg.get("poll_interval_seconds", 300))))
    except KeyboardInterrupt:
        sound.stop_sound()
        print("[engine] Background mode stopped.")
