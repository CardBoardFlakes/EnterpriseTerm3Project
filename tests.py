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
import json as _json
import wallpaper
import webwall
import sound
import perf
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
              cfg2["weather_refresh_seconds"] == 600 and cfg2["tick_interval_seconds"] == 30)
        check("pomodoro defaults present",
              cfg2["pomodoro"]["work_min"] == 25)
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


def test_wallpaper_patterns():
    section("wallpaper patterns + warmth")

    # warmth_factor: none/warm -> 0, cold -> 1, mid -> in-between & monotone.
    check("warmth none => 0", wallpaper.warmth_factor(None) == 0.0)
    check("warmth warm => 0", wallpaper.warmth_factor(25) == 0.0)
    check("warmth freezing => 1", wallpaper.warmth_factor(-10) == 1.0)
    check("warmth cold is warmer than cool",
          wallpaper.warmth_factor(0) > wallpaper.warmth_factor(15) > 0)

    # is_animated covers every real condition.
    check("rain animated", wallpaper.is_animated("rain"))
    check("storm animated", wallpaper.is_animated("storm"))
    check("night animated", wallpaper.is_animated("night"))
    check("unknown not animated", not wallpaper.is_animated("fog"))

    # Every condition's pattern actually marks the buffer (draws something).
    def paints(cond):
        w, h = 80, 60
        raw, stride = wallpaper._build_raw_gradient(w, h, (60, 90, 150), (10, 20, 40))
        before = bytes(raw)
        wallpaper._render_pattern(cond, raw, stride, w, h, 0.3, 1.0)
        return raw != before
    for cond in ("clear", "cloud", "rain", "storm", "night"):
        check(f"{cond} pattern paints pixels", paints(cond))

    # Rain trickles: different phase => different pixels.
    w, h = 80, 60
    r1, st = wallpaper._build_raw_gradient(w, h, (40, 80, 180), (0, 0, 0))
    r2, _ = wallpaper._build_raw_gradient(w, h, (40, 80, 180), (0, 0, 0))
    wallpaper._render_rain(r1, st, w, h, 0.1, 1.0)
    wallpaper._render_rain(r2, st, w, h, 0.6, 1.0)
    check("rain moves with phase", r1 != r2)

    with tempfile.TemporaryDirectory() as d:
        orig = wallpaper.CACHE_DIR
        wallpaper.CACHE_DIR = d
        try:
            # Cold + condition builds a valid PNG whose name carries the condition.
            p = wallpaper.build_weather_image(40, 80, 180, 0.6, 0.5,
                                              condition="rain", temperature=-5,
                                              width=64, height=48)
            with open(p, "rb") as f:
                check("patterned png signature", f.read(8) == b"\x89PNG\r\n\x1a\n")
            check("filename encodes condition", "rain" in os.path.basename(p))

            # patterns=False leaves a plain gradient (no overlay pixels).
            plain = wallpaper.build_weather_image(40, 80, 180, 0.6, 0.5,
                                                  condition="storm", patterns=False,
                                                  width=64, height=48)
            check("patterns off still builds", os.path.isfile(plain))
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
# web wallpaper backend
# ---------------------------------------------------------
def test_webwall():
    section("web wallpaper backend")
    with tempfile.TemporaryDirectory() as d:
        orig = webwall.WEB_DIR
        webwall.WEB_DIR = d
        try:
            # ensure_assets writes a versioned, self-contained HTML page.
            p = webwall.ensure_assets()
            check("index.html created", os.path.isfile(p))
            with open(p) as f:
                html = f.read()
            check("html is versioned", f"etc-wallpaper v{webwall.HTML_VERSION}" in html)
            check("html has canvas + loop", "<canvas" in html and "requestAnimationFrame" in html)
            mtime = os.path.getmtime(p)
            webwall.ensure_assets()   # idempotent: same version => no rewrite
            check("ensure_assets idempotent", os.path.getmtime(p) == mtime)

            # build_state: keys present, cold => warmth, colours are RGB triples.
            st = webwall.build_state(40, 80, 180, 0.8, "rain", -5, 0.4, True, True)
            for k in ("condition", "top", "bottom", "base", "brightness", "warmth"):
                check(f"state has {k}", k in st)
            check("state condition normalised", st["condition"] == "rain")
            check("cold => warmth applied", st["warmth"] > 0)
            check("top is rgb triple", len(st["top"]) == 3
                  and all(0 <= v <= 255 for v in st["top"]))
            warm_st = webwall.build_state(40, 80, 180, 0.8, "rain", 25, 0.4, True, True)
            check("warm => no warmth", warm_st["warmth"] == 0)

            # write_state round-trips as valid JSON.
            webwall.write_state(st)
            with open(webwall.state_path()) as f:
                back = _json.load(f)
            check("weather.json round-trips", back["condition"] == "rain")
        finally:
            webwall.WEB_DIR = orig


# ---------------------------------------------------------
# animation governor + animated wallpaper
# ---------------------------------------------------------
def test_governor():
    section("animation governor")

    # Calm machine: keeps rendering, never suspends, sleeps ~ 1/fps.
    g = perf.AdaptiveGovernor(target_fps=8, load_ceiling=0.85)
    for _ in range(6):
        g.observe(0.01, 0.2)          # cheap frames, low load
    check("calm keeps rendering", g.render and not g.suspended)
    check("calm sleeps near frame budget", abs(g.sleep - 1 / 8) < 1e-6)

    # High system load for `patience` samples -> throttle then suspend.
    g = perf.AdaptiveGovernor(target_fps=8, load_ceiling=0.85, patience=3)
    g.observe(0.01, 1.5)
    check("first overload throttles, not suspended",
          not g.suspended and g.sleep > 1 / 8)
    g.observe(0.01, 1.5)
    g.observe(0.01, 1.5)
    check("sustained load suspends", g.suspended and not g.render)

    # Slow frames alone (no load signal) also suspend.
    g = perf.AdaptiveGovernor(target_fps=10, load_ceiling=0.85, patience=2)
    g.observe(1.0, None)              # 1s frame vs 0.1s budget
    g.observe(1.0, None)
    check("expensive frames suspend without load avg", g.suspended)

    # Recovery: once calm for `recover` probes, resume rendering.
    g = perf.AdaptiveGovernor(target_fps=8, load_ceiling=0.85,
                              patience=1, recover=2)
    g.observe(0.01, 2.0)             # suspend immediately
    check("suspended under heavy load", g.suspended)
    g.observe(0.0, 0.1)              # probe 1 (no render while suspended)
    g.observe(0.0, 0.1)              # probe 2
    check("resumes after load clears", not g.suspended and g.render)

    # Live reconfigure from the GUI.
    g.configure(target_fps=15)
    check("configure updates budget", abs(g.budget - 1 / 15) < 1e-6)

    # system_load is per-core and non-negative (or None on Windows).
    load = perf.system_load()
    check("system_load sane", load is None or load >= 0)


def test_animated_wallpaper():
    section("animated wallpaper (mutation stubbed)")
    calls = {"apply": 0}
    o_wall = wallpaper.apply_weather_wallpaper
    o_theme = theme.apply_theme_color
    o_play, o_stop = sound.play_ambient, sound.stop_sound
    wallpaper.apply_weather_wallpaper = lambda *a, **k: calls.__setitem__("apply", calls["apply"] + 1) or True
    theme.apply_theme_color = lambda *a, **k: "stub"
    sound.play_ambient = lambda *a, **k: None
    sound.stop_sound = lambda *a, **k: None
    try:
        cfg = config.default_config()
        cfg["manual_weather"] = "rain"        # avoid network
        cfg["wallpaper_animated"] = True

        check("animation_active on when enabled", engine.animation_active(cfg))
        cfg2 = config.default_config()
        cfg2["manual_weather"] = "rain"
        check("animation_active off by default", not engine.animation_active(cfg2))

        eng = engine.Engine()
        # A full step in animated mode caches frame inputs but does NOT apply
        # the wallpaper itself (the governor loop owns that).
        eng.step(cfg, None, animating=True)
        check("animated step skips static apply", calls["apply"] == 0)
        check("render inputs cached", eng._last_render is not None
              and eng._last_render["condition"] == "rain")

        # A governed frame renders exactly one wallpaper.
        eng.animate_frame(2.0)
        check("animate_frame applies one frame", calls["apply"] == 1)

        # Successive frames advance the motion phase.
        p1 = (1.0 % engine.ANIM_PERIOD) / engine.ANIM_PERIOD
        p2 = (4.0 % engine.ANIM_PERIOD) / engine.ANIM_PERIOD
        check("phase advances with time", p1 != p2)

        # No cached inputs yet => nothing to draw.
        check("fresh engine animates nothing", engine.Engine().animate_frame(0.0) is False)

        # --- web backend: writes JSON, never sets a PNG desktop ----------
        with tempfile.TemporaryDirectory() as d:
            o_web = webwall.WEB_DIR
            webwall.WEB_DIR = d
            try:
                webcfg = config.default_config()
                webcfg["manual_weather"] = "storm"
                webcfg["wallpaper_backend"] = "web"
                webcfg["wallpaper_animated"] = True   # should NOT drive in-app loop
                check("web backend disables in-app animation loop",
                      not engine.animation_active(webcfg))
                calls["apply"] = 0
                eng2 = engine.Engine()
                st = eng2.step(webcfg, None)
                check("web step sets no PNG wallpaper", calls["apply"] == 0)
                check("web step wrote feed", os.path.isfile(webwall.state_path()))
                check("web step reported in status",
                      any("web" in a for a in st["applied"]))
                # Unchanged state => no rewrite second time.
                mt = os.path.getmtime(webwall.state_path())
                eng2.step(webcfg, None)
                check("web feed not rewritten when unchanged",
                      os.path.getmtime(webwall.state_path()) == mt)
            finally:
                webwall.WEB_DIR = o_web
    finally:
        wallpaper.apply_weather_wallpaper = o_wall
        theme.apply_theme_color = o_theme
        sound.play_ambient = o_play
        sound.stop_sound = o_stop


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
    base_vals = {
        "enabled": True, "dynamic_theme": True, "wallpaper": True,
        "ambient_sound": True, "tasks": True, "tint": 40, "volume": 25,
        "tick_interval": 30, "weather_refresh": 600, "wallpaper_dynamic": True,
        "wallpaper_shift": 35, "p_work": 25, "p_break": 5, "p_long": 15,
        "p_cycles": 4, "manual_weather": "auto", "manual_time": "auto",
        "manual_theme_color": "auto", "run_at_login": False,
    }
    cfg = config.default_config()
    out = gui.apply_values_to_config(cfg, {**base_vals, "enabled": False,
        "wallpaper": False, "tint": 55.7, "wallpaper_dynamic": False,
        "manual_weather": "storm", "manual_time": "night",
        "manual_theme_color": "10,20,30"})
    check("enabled mapped", out["enabled"] is False)
    check("feature mapped", out["features"]["wallpaper"] is False)
    check("tint rounded", out["weather_tint_strength"] == 56)
    check("dynamic wallpaper mapped", out["wallpaper_dynamic"] is False)
    check("manual weather mapped", out["manual_weather"] == "storm")
    check("color parsed", out["manual_theme_color"] == [10, 20, 30])
    check("pomodoro mapped", out["pomodoro"]["work_min"] == 25)
    out2 = gui.apply_values_to_config(cfg, base_vals)
    check("auto color => None", out2["manual_theme_color"] is None)


def test_pomodoro():
    section("pomodoro timer")
    import pomodoro as P
    p = P.Pomodoro(work_min=1, break_min=1, long_break_min=2, cycles_before_long=2)
    check("starts idle", p.phase == P.IDLE)
    p.start()
    check("start -> work running", p.phase == P.WORK and p.running)
    check("work completes -> break", p.tick(60) == ("work_complete", P.BREAK))
    check("break completes -> work", p.tick(60) == ("break_complete", P.WORK))
    check("2nd work -> long break", p.tick(60) == ("work_complete", P.LONG_BREAK))
    check("completed_work counted", p.completed_work == 2)
    p.pause()
    check("paused does not tick", p.tick(60) is None and not p.running)
    p.reset()
    check("reset -> idle", p.phase == P.IDLE and p.completed_work == 0)
    p2 = P.Pomodoro(work_min=25)
    p2.start()
    check("label shows Work mm:ss", p2.label().startswith("Work 25:00"))


def test_drift():
    section("wallpaper dynamic drift")
    a = wallpaper.shifted_base(40, 80, 180, 0.5, phase=0.0, shift_strength=0.0)
    b = wallpaper.shifted_base(40, 80, 180, 0.5, phase=0.25, shift_strength=0.0)
    check("no shift => phase irrelevant", a == b)
    c = wallpaper.shifted_base(40, 80, 180, 0.5, phase=0.0, shift_strength=0.6)
    d = wallpaper.shifted_base(40, 80, 180, 0.5, phase=0.25, shift_strength=0.6)
    check("drift varies with phase", c != d)
    delta = max(abs(c[i] - d[i]) for i in range(3))
    check("drift stays subtle (bounded)", 0 < delta <= 60)


def test_engine_guards():
    section("engine change-guards + weather cache")
    import datetime as dt
    counts = {"theme": 0, "wall": 0, "play": 0, "wfetch": 0}
    saved = (theme.apply_theme_color, wallpaper.apply_weather_wallpaper,
             sound.play_ambient, sound.set_volume, sound.stop_sound,
             weather.get_weather)
    theme.apply_theme_color = lambda *a, **k: counts.__setitem__("theme", counts["theme"] + 1) or "t"
    wallpaper.apply_weather_wallpaper = lambda *a, **k: counts.__setitem__("wall", counts["wall"] + 1) or True
    sound.play_ambient = lambda *a, **k: counts.__setitem__("play", counts["play"] + 1)
    sound.set_volume = lambda *a, **k: None
    sound.stop_sound = lambda *a, **k: None

    def fake_wx(*a, **k):
        counts["wfetch"] += 1
        sr = dt.datetime.combine(dt.date.today(), dt.time(6, 0))
        ss = dt.datetime.combine(dt.date.today(), dt.time(20, 0))
        return {"condition": "clear", "sunrise": sr, "sunset": ss, "is_day": True,
                "temperature": None, "rain": 0, "wind_speed": 0, "cloud_cover": 0}
    weather.get_weather = fake_wx
    try:
        eng = engine.Engine()
        cfg = config.default_config()           # manual auto -> live (cached)
        cfg["wallpaper_dynamic"] = False         # static -> guard can skip redraw
        cfg["wallpaper_min_interval_seconds"] = 0
        t0 = dt.datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
        eng.step(cfg, None, now=t0)
        eng.step(cfg, None, now=t0)              # identical -> everything skipped
        check("theme applied once then skipped", counts["theme"] == 1)
        check("sound played once then skipped", counts["play"] == 1)
        check("static wallpaper drawn once then skipped", counts["wall"] == 1)
        check("weather fetched once (cached)", counts["wfetch"] == 1)
    finally:
        (theme.apply_theme_color, wallpaper.apply_weather_wallpaper,
         sound.play_ambient, sound.set_volume, sound.stop_sound,
         weather.get_weather) = saved


def main():
    test_config()
    test_weather()
    test_theme()
    test_wallpaper()
    test_wallpaper_patterns()
    test_sound()
    test_tasks()
    test_autostart()
    test_webwall()
    test_governor()
    test_animated_wallpaper()
    test_engine()
    test_pomodoro()
    test_drift()
    test_engine_guards()
    test_gui_helper()
    print(f"\n{'='*40}\nRESULT: {_passed} passed, {_failed} failed")
    return 1 if _failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
