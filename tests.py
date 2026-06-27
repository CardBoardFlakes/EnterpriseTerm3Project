"""
Headless test suite for the Environment Theme Controller.

Covers config, weather override, theme computation, wallpaper PNG
generation, sound selection/synthesis, task scheduling, autostart command
generation, and a full engine tick. All system-mutating calls (accent,
wallpaper, audio playback, launchctl/registry) are stubbed so running the
tests never changes your machine.
"""

import os
import struct
import tempfile
import datetime
import wave

import config
import weather
import theme
import wallpaper
import sound
import tasks as tasks_mod
import autostart
import engine

_passed = 0
_failed = 0


def check(name, cond):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  PASS  {name}")
    else:
        _failed += 1
        print(f"  FAIL  {name}")


def section(t):
    print(f"\n=== {t} ===")


# ---------------------------------------------------------
# config
# ---------------------------------------------------------
def test_config():
    section("config")
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "config.json")
        cfg = config.load_config(p)
        check("defaults present", cfg["enabled"] is True and "features" in cfg)
        cfg["enabled"] = False
        cfg["features"]["wallpaper"] = False
        check("save ok", config.save_config(cfg, p))
        cfg2 = config.load_config(p)
        check("roundtrip enabled", cfg2["enabled"] is False)
        check("roundtrip nested feature", cfg2["features"]["wallpaper"] is False)
        check("missing key filled from defaults",
              cfg2["poll_interval_seconds"] == 300)
        check("feature gated by master switch",
              config.feature_enabled(cfg2, "dynamic_theme") is False)
        cfg2["enabled"] = True
        check("feature on when master on",
              config.feature_enabled(cfg2, "dynamic_theme") is True)


# ---------------------------------------------------------
# weather
# ---------------------------------------------------------
def test_weather():
    section("weather")
    cfg = config.default_config()
    cfg["manual_weather"] = "rain"
    w = weather.get_effective_weather(cfg)
    check("manual weather honoured", w["condition"] == "rain")
    check("manual source tagged", w["source"] == "manual")
    check("is_night present", "is_night" in w)

    cfg["manual_time"] = "night"
    w = weather.get_effective_weather(cfg)
    check("manual time night", w["is_night"] is True)
    cfg["manual_time"] = "day"
    w = weather.get_effective_weather(cfg)
    check("manual time day", w["is_night"] is False)

    # Offline fallback: force live fetch to fail.
    orig = weather.get_weather
    weather.get_weather = lambda *a, **k: (_ for _ in ()).throw(ConnectionError("no net"))
    try:
        cfg2 = config.default_config()  # manual_weather=auto
        w = weather.get_effective_weather(cfg2)
        check("offline fallback works", w["source"] == "fallback"
              and w["condition"] in weather.CONDITIONS)
    finally:
        weather.get_weather = orig


# ---------------------------------------------------------
# theme
# ---------------------------------------------------------
def test_theme():
    section("theme")
    sr = datetime.datetime.combine(datetime.date.today(), datetime.time(6, 0))
    ss = datetime.datetime.combine(datetime.date.today(), datetime.time(20, 0))
    (r, g, b), bright_day = theme.compute_theme_color("clear", sr, ss, is_night_override=False)
    (r2, g2, b2), bright_night = theme.compute_theme_color("clear", sr, ss, is_night_override=True)
    check("day brighter than night", bright_day > bright_night)
    check("night dims colour", (r2 + g2 + b2) < (r + g + b))
    check("nearest accent blue", theme._nearest_macos_accent(0, 120, 250)[0] == "Blue")
    check("nearest accent red", theme._nearest_macos_accent(250, 70, 70)[0] == "Red")

    # apply (stub the OS setters)
    o1, o2 = theme.set_macos_theme, theme.set_windows_accent
    theme.set_macos_theme = lambda *a, **k: None
    theme.set_windows_accent = lambda *a, **k: None
    try:
        desc = theme.apply_theme_color(40, 80, 180, 0.2)
        check("apply returns description", isinstance(desc, str) and len(desc) > 0)
    finally:
        theme.set_macos_theme, theme.set_windows_accent = o1, o2


# ---------------------------------------------------------
# wallpaper
# ---------------------------------------------------------
def test_wallpaper():
    section("wallpaper")
    with tempfile.TemporaryDirectory() as d:
        orig = wallpaper.CACHE_DIR
        wallpaper.CACHE_DIR = d
        try:
            path = wallpaper.build_weather_image(40, 80, 180, 0.6, 0.5,
                                                 width=64, height=48)
            check("image file created", os.path.isfile(path))
            with open(path, "rb") as f:
                head = f.read(24)
            check("png signature", head[:8] == b"\x89PNG\r\n\x1a\n")
            w_, h_ = struct.unpack(">II", head[16:24])
            check("png dimensions", (w_, h_) == (64, 48))
            # building a second image cleans up the first
            path2 = wallpaper.build_weather_image(10, 20, 30, 0.3, 0.5,
                                                  width=64, height=48)
            pngs = [f for f in os.listdir(d) if f.endswith(".png")]
            check("old wallpaper cleaned", len(pngs) == 1 and os.path.basename(path2) in pngs)
        finally:
            wallpaper.CACHE_DIR = orig


# ---------------------------------------------------------
# sound
# ---------------------------------------------------------
def test_sound():
    section("sound")
    check("rain->rain-soft", sound.select_ambient("rain", False).endswith("rain-soft.wav"))
    check("storm->thunder", sound.select_ambient("storm", False).endswith("thunder.wav"))
    check("clear day->birds", sound.select_ambient("clear", False).endswith("birds.wav"))
    check("clear night->crickets", sound.select_ambient("clear", True).endswith("crickets.wav"))
    check("cloud->wind", sound.select_ambient("cloud", False).endswith("wind.wav"))

    with tempfile.TemporaryDirectory() as d:
        created = sound.ensure_placeholder_sounds(directory=d)
        check("placeholders created", len(created) == 6)
        sample = os.path.join(d, "rain-soft.wav")
        with wave.open(sample, "rb") as wf:
            check("wav mono 16-bit", wf.getnchannels() == 1 and wf.getsampwidth() == 2)
            check("wav has frames", wf.getnframes() > 1000)
        # second call creates nothing new
        again = sound.ensure_placeholder_sounds(directory=d)
        check("placeholders idempotent", again == [])


# ---------------------------------------------------------
# tasks
# ---------------------------------------------------------
def test_tasks():
    section("tasks")
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "tasks.json")
        store = tasks_mod.TaskStore(p)
        t = store.add_task("Morning", type="daily", time="07:00", action="chime")
        check("task added with id", t["id"] == "t1")
        check("persisted", os.path.isfile(p))
        check("list has one", len(store.list_tasks()) == 1)

        now = datetime.datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)
        due = store.due_tasks(now)
        check("daily due after time", len(due) == 1)
        store.mark_fired(t, now)
        check("not due again same day", len(store.due_tasks(now)) == 0)

        early = now.replace(hour=6, minute=0)
        t2 = store.add_task("Evening", type="daily", time="22:00")
        check("daily not due before time", t2 not in store.due_tasks(early))

        # once task
        past = (datetime.datetime.now() - datetime.timedelta(hours=1)).isoformat()
        t3 = store.add_task("OneShot", type="once", datetime_str=past)
        check("once due when past", t3 in store.due_tasks())
        store.mark_fired(t3)
        check("once not due after fired", t3 not in store.due_tasks())

        # disabled
        store.update_task("t1", enabled=False)
        store.update_task("t1", last_fired=None)
        check("disabled never due", store.due_tasks(now) == [] or
              all(x["id"] != "t1" for x in store.due_tasks(now)))

        check("remove works", store.remove_task("t1") and len(store.list_tasks()) == 2)

        # reload from disk
        store2 = tasks_mod.TaskStore(p)
        check("reload persists", len(store2.list_tasks()) == 2)


# ---------------------------------------------------------
# autostart
# ---------------------------------------------------------
def test_autostart():
    section("autostart (no system mutation)")
    cmd = autostart.preview_command()
    check("preview command non-empty", isinstance(cmd, str) and "main.py" in cmd)
    check("is_enabled returns bool", isinstance(autostart.is_autostart_enabled(), bool))
    if hasattr(autostart, "_macos_plist_contents"):
        plist = autostart._macos_plist_contents()
        check("plist mentions --background", "--background" in plist)
        check("plist has RunAtLoad", "RunAtLoad" in plist)


# ---------------------------------------------------------
# engine
# ---------------------------------------------------------
def test_engine():
    section("engine tick (system mutation stubbed)")
    applied = {"theme": 0, "wallpaper": 0, "sound": 0, "chime": 0, "stop": 0}
    o_theme = theme.apply_theme_color
    o_wall = wallpaper.apply_weather_wallpaper
    o_play = sound.play_ambient
    o_chime = sound.play_chime
    o_stop = sound.stop_sound
    theme.apply_theme_color = lambda *a, **k: applied.__setitem__("theme", applied["theme"] + 1) or "stub"
    wallpaper.apply_weather_wallpaper = lambda *a, **k: applied.__setitem__("wallpaper", applied["wallpaper"] + 1) or True
    sound.play_ambient = lambda *a, **k: applied.__setitem__("sound", applied["sound"] + 1)
    sound.play_chime = lambda *a, **k: applied.__setitem__("chime", applied["chime"] + 1)
    sound.stop_sound = lambda *a, **k: applied.__setitem__("stop", applied["stop"] + 1)
    try:
        with tempfile.TemporaryDirectory() as d:
            cfg = config.default_config()
            cfg["manual_weather"] = "rain"   # avoid network
            store = tasks_mod.TaskStore(os.path.join(d, "tasks.json"))

            st = engine.tick(cfg, store)
            check("tick condition rain", st["condition"] == "rain")
            check("theme applied", applied["theme"] == 1)
            check("wallpaper applied", applied["wallpaper"] == 1)
            check("sound applied", applied["sound"] == 1)
            check("applied list populated", len(st["applied"]) >= 3)

            # disable wallpaper + sound
            cfg["features"]["wallpaper"] = False
            cfg["features"]["ambient_sound"] = False
            applied.update({"wallpaper": 0, "sound": 0})
            st = engine.tick(cfg, store)
            check("wallpaper skipped when off", applied["wallpaper"] == 0)
            check("sound stopped when off", applied["stop"] >= 1)

            # master off
            cfg["enabled"] = False
            st = engine.tick(cfg, store)
            check("master off => not enabled", st["enabled"] is False)

            # task firing
            cfg["enabled"] = True
            cfg["features"]["wallpaper"] = True
            cfg["features"]["ambient_sound"] = True
            past_min = (datetime.datetime.now() - datetime.timedelta(minutes=1)).strftime("%H:%M")
            store.add_task("Chime me", type="daily", time=past_min, action="chime")
            st = engine.tick(cfg, store)
            check("task fired", "Chime me" in st["fired_tasks"])
            check("chime action ran", applied["chime"] == 1)
    finally:
        theme.apply_theme_color = o_theme
        wallpaper.apply_weather_wallpaper = o_wall
        sound.play_ambient = o_play
        sound.play_chime = o_chime
        sound.stop_sound = o_stop


# ---------------------------------------------------------
# gui (pure helper only — no window)
# ---------------------------------------------------------
def test_gui_helper():
    section("gui config-mapping helper")
    try:
        import gui
    except Exception as e:
        check(f"gui import (skipped: {e})", True)
        return
    cfg = config.default_config()
    out = gui.apply_values_to_config(cfg, {
        "enabled": False, "dynamic_theme": True, "wallpaper": False,
        "ambient_sound": True, "tasks": True, "tint": 55.7, "volume": 30.2,
        "poll_interval": 120, "manual_weather": "storm", "manual_time": "night",
        "manual_theme_color": "10,20,30", "run_at_login": False,
    })
    check("enabled mapped", out["enabled"] is False)
    check("feature mapped", out["features"]["wallpaper"] is False)
    check("tint rounded", out["weather_tint_strength"] == 56)
    check("manual weather mapped", out["manual_weather"] == "storm")
    check("color parsed", out["manual_theme_color"] == [10, 20, 30])
    out2 = gui.apply_values_to_config(cfg, {**{
        "enabled": True, "dynamic_theme": True, "wallpaper": True,
        "ambient_sound": True, "tasks": True, "tint": 40, "volume": 25,
        "poll_interval": 300, "manual_weather": "auto", "manual_time": "auto",
        "run_at_login": False}, "manual_theme_color": "auto"})
    check("auto color => None", out2["manual_theme_color"] is None)


def main():
    test_config()
    test_weather()
    test_theme()
    test_wallpaper()
    test_sound()
    test_tasks()
    test_autostart()
    test_engine()
    test_gui_helper()
    print(f"\n{'='*40}\nRESULT: {_passed} passed, {_failed} failed")
    return 1 if _failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
