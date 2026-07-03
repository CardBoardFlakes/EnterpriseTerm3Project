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
import webwall
import sound
import perf
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
        pat_cond = ("night" if is_night and not any(k in condition for k in ("rain", "storm"))
                    else condition)
        patterns = bool(cfg.get("wallpaper_patterns", True))
        warmth = bool(cfg.get("wallpaper_warmth", True))
        if (cfg.get("wallpaper_backend") or "png").lower() == "web":
            webwall.ensure_assets()
            webwall.write_state(webwall.build_state(
                r, g, b, brightness, pat_cond, eff.get("temperature"),
                tint, warmth, patterns))
            status["applied"].append(f"wallpaper: web/{pat_cond}")
        elif wallpaper.apply_weather_wallpaper(
                r, g, b, brightness, tint, condition=pat_cond,
                temperature=eff.get("temperature"),
                patterns=patterns, warmth=warmth):
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
ANIM_PERIOD = 6.0      # seconds for one pattern-motion cycle in animated mode


def _color_delta(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]), abs(a[2] - b[2]))


def animation_active(cfg) -> bool:
    """
    True when the *in-app* PNG animation loop should run. The web backend is
    animated by the external engine, so the in-app fps loop stays off for it.
    """
    return (bool(cfg.get("enabled", True))
            and config.feature_enabled(cfg, "wallpaper")
            and bool(cfg.get("wallpaper_animated", False))
            and (cfg.get("wallpaper_backend") or "png").lower() == "png")


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
        self._last_render = None       # cached frame inputs for animated redraws
        self._last_web = None          # last web-backend state written

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

        # Re-derive the cheap, time-dependent bit against *this* step's clock —
        # for both fresh and cached weather — so day/night stays consistent
        # with `now` (and the engine is deterministic when `now` is injected).
        w = self._weather
        if manual_t == "night":
            w["is_night"] = True
        elif manual_t == "day":
            w["is_night"] = False
        else:
            w["is_night"] = weather._is_night(w["sunrise"], w["sunset"], now)
        return w

    def _phase(self, now):
        secs = now.hour * 3600 + now.minute * 60 + now.second
        return (secs % DRIFT_PERIOD) / DRIFT_PERIOD

    # --- animated wallpaper -------------------------------------------
    def animate_frame(self, mono=0.0):
        """
        Redraw one animation frame from the cached render inputs, advancing the
        pattern motion by *mono* (a monotonic-clock reading). Cheap: no weather
        or theme recompute. Returns True if a frame was applied.
        """
        lr = self._last_render
        if not lr:
            return False
        phase = (mono % ANIM_PERIOD) / ANIM_PERIOD
        return wallpaper.apply_weather_wallpaper(
            lr["r"], lr["g"], lr["b"], lr["brightness"], lr["tint"],
            phase=phase, shift_strength=lr["shift"], condition=lr["condition"],
            temperature=lr["temperature"], patterns=lr["patterns"],
            warmth=lr["warmth"])

    # --- one cheap step -----------------------------------------------
    def step(self, cfg, store=None, now=None, animating=False):
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
            patterns = bool(cfg.get("wallpaper_patterns", True))
            warmth = bool(cfg.get("wallpaper_warmth", True))
            # Show a night sky whenever it's dark out, unless it's actively
            # raining/storming (those stay themselves even after sunset).
            pat_cond = ("night" if is_night and not any(k in condition for k in ("rain", "storm"))
                        else condition)
            # Cache what a frame needs so the animation loop can redraw cheaply
            # (varying only the phase) without recomputing weather/theme.
            self._last_render = {
                "r": r, "g": g, "b": b, "brightness": brightness, "tint": tint,
                "shift": shift, "condition": pat_cond,
                "temperature": eff.get("temperature"),
                "patterns": patterns, "warmth": warmth,
            }
            backend = (cfg.get("wallpaper_backend") or "png").lower()
            if backend == "web":
                # Hand off to an external engine: keep the HTML wallpaper in
                # place and refresh the JSON feed only when the state changes.
                try:
                    webwall.ensure_assets()
                    state = webwall.build_state(r, g, b, brightness, pat_cond,
                                                eff.get("temperature"), tint,
                                                warmth, patterns)
                    if state != self._last_web:
                        webwall.write_state(state)
                        self._last_web = state
                        status["applied"].append(f"wallpaper: web/{pat_cond}")
                except Exception as e:
                    print(f"[engine] web wallpaper failed: {e}")

            # In animated mode the governor-driven loop owns the wallpaper; the
            # static guarded path below would just fight it, so skip it.
            elif not animating:
                phase = self._phase(now)
                target = wallpaper.shifted_base(r, g, b, tint, phase, shift)
                bucket = round(brightness, 2)
                min_iv = max(5, int(cfg.get("wallpaper_min_interval_seconds", 45)))
                due = (self._last_wall_at is None
                       or (now - self._last_wall_at).total_seconds() >= min_iv)
                # A moving pattern is worth a redraw on the interval even when
                # the base colour is steady (e.g. manual rain) — that's motion.
                moving = dynamic and patterns and wallpaper.is_animated(pat_cond)
                changed = (self._last_wall_key is None
                           or self._last_wall_key[1] != bucket
                           or moving
                           or _color_delta(target, self._last_wall_key[0]) >= 2)
                if due and changed:
                    if wallpaper.apply_weather_wallpaper(
                            r, g, b, brightness, tint, phase=phase, shift_strength=shift,
                            condition=pat_cond, temperature=eff.get("temperature"),
                            patterns=patterns, warmth=warmth):
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
        self.governor = perf.AdaptiveGovernor()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self.last_status = None
        self._last_full = None      # monotonic time of the last full evaluation
        self._anim_paused = False   # governor has us on a static frame

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
            animated = animation_active(cfg)

            # Full weather/theme/sound/tasks evaluation on the normal cadence.
            if self._last_full is None or (mono - self._last_full) >= tick_iv:
                try:
                    self.last_status = self.engine.step(cfg, store, now,
                                                        animating=animated)
                    if self.on_status:
                        self.on_status(self.last_status)
                except Exception as e:
                    print(f"[engine] step failed: {e}")
                self._last_full = mono

            if animated:
                sleep = self._animate_once(cfg)
            else:
                self._anim_paused = False
                sleep = tick_iv

            self._wake.wait(timeout=max(0.05, min(sleep, tick_iv)))
            self._wake.clear()
        sound.stop_sound()

    def _animate_once(self, cfg):
        """Render one governed animation frame; return the seconds to sleep."""
        self.governor.configure(
            target_fps=int(cfg.get("wallpaper_animated_fps", 6)),
            load_ceiling=float(cfg.get("wallpaper_load_ceiling", 85)) / 100.0)
        load = perf.system_load()
        render_dt = 0.0
        if self.governor.render:
            t0 = time.monotonic()
            try:
                self.engine.animate_frame(t0)
                self._anim_paused = False
            except Exception as e:
                print(f"[engine] anim frame failed: {e}")
            render_dt = time.monotonic() - t0

        self.governor.observe(render_dt, load)

        # Just suspended: settle on one clean static frame so the desktop
        # isn't frozen mid-animation while we back off.
        if self.governor.suspended and not self._anim_paused:
            try:
                self.engine.animate_frame(0.0)
            except Exception:
                pass
            self._anim_paused = True
            print("[engine] Animation paused — system under load. Will resume "
                  "automatically.")
        return self.governor.sleep


def run_forever(config_path=config.CONFIG_FILE, tasks_path=tasks_mod.TASKS_FILE):
    """Headless loop used by ``main.py --background``."""
    print("[engine] Background mode started.")
    eng = Engine()
    gov = perf.AdaptiveGovernor()
    last_full = None
    paused = False
    try:
        while True:
            cfg = config.load_config(config_path)
            store = tasks_mod.TaskStore(tasks_path)
            mono = time.monotonic()
            tick_iv = max(5, int(cfg.get("tick_interval_seconds", 30)))
            animated = animation_active(cfg)

            if last_full is None or (mono - last_full) >= tick_iv:
                try:
                    eng.step(cfg, store, animating=animated)
                except Exception as e:
                    print(f"[engine] step failed: {e}")
                last_full = mono

            if animated:
                gov.configure(
                    target_fps=int(cfg.get("wallpaper_animated_fps", 6)),
                    load_ceiling=float(cfg.get("wallpaper_load_ceiling", 85)) / 100.0)
                load = perf.system_load()
                render_dt = 0.0
                if gov.render:
                    t0 = time.monotonic()
                    try:
                        eng.animate_frame(t0)
                        paused = False
                    except Exception as e:
                        print(f"[engine] anim frame failed: {e}")
                    render_dt = time.monotonic() - t0
                gov.observe(render_dt, load)
                if gov.suspended and not paused:
                    try:
                        eng.animate_frame(0.0)
                    except Exception:
                        pass
                    paused = True
                    print("[engine] Animation paused — system under load.")
                sleep = min(gov.sleep, tick_iv)
            else:
                paused = False
                sleep = tick_iv

            time.sleep(max(0.05, sleep))
    except KeyboardInterrupt:
        sound.stop_sound()
        print("[engine] Background mode stopped.")
