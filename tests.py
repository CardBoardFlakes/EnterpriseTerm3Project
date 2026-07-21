"""
Headless test suite for the Flow.

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
              cfg2["weather_refresh_seconds"] == 600 and cfg2["tick_interval_seconds"] == 30)
        check("pomodoro defaults present",
              cfg2["pomodoro"]["work_min"] == 25)
        check("feature gated by master switch",
              config.feature_enabled(cfg2, "dynamic_theme") is False)
        cfg2["enabled"] = True
        check("feature on when master on",
              config.feature_enabled(cfg2, "dynamic_theme") is True)
        # Retired keys are stripped from old config files on load.
        import json as _json
        with open(p, "w") as f:
            _json.dump({"enabled": True, "location_precision": 2}, f)
        cfg3 = config.load_config(p)
        check("retired location_precision dropped", "location_precision" not in cfg3)


# ---------------------------------------------------------
# weather
# ---------------------------------------------------------
def test_weather():
    section("weather")

    # Stub live data so we can assert manual overrides don't clobber it.
    orig = weather.get_weather
    import datetime as _dt
    sr = _dt.datetime.combine(_dt.date.today(), _dt.time(6, 0))
    ss = _dt.datetime.combine(_dt.date.today(), _dt.time(20, 0))
    weather.get_weather = lambda *a, **k: {
        "condition": "clear", "sunrise": sr, "sunset": ss, "is_day": True,
        "temperature": 20.0, "feels_like": 19.0, "humidity": 55, "uv_index": 4,
        "uv_index_max": 6, "pressure": 1013, "rain": 0, "precip_chance": 10,
        "wind_speed": 12, "wind_gust": 20, "wind_dir": 180, "cloud_cover": 10,
    }
    try:
        cfg = config.default_config()
        cfg["manual_weather"] = "rain"
        w = weather.get_effective_weather(cfg)
        check("manual weather honoured", w["condition"] == "rain")
        check("condition_source is manual", w["condition_source"] == "manual")
        check("live source preserved (not manual)", w["source"] == "live")
        # The key fix: live measurements survive the manual override.
        check("live temperature preserved", w["temperature"] == 20.0)
        check("live humidity preserved", w["humidity"] == 55)
        check("live uv preserved", w["uv_index"] == 4)
        check("is_night present", "is_night" in w)

        cfg["manual_time"] = "night"
        check("manual time night", weather.get_effective_weather(cfg)["is_night"] is True)
        cfg["manual_time"] = "day"
        check("manual time day", weather.get_effective_weather(cfg)["is_night"] is False)
    finally:
        weather.get_weather = orig

    # Extra live fields flow through get_weather (stubbed request layer).
    check("MEASUREMENT_KEYS covers uv+humidity",
          "uv_index" in weather.MEASUREMENT_KEYS and "humidity" in weather.MEASUREMENT_KEYS)

    # Location: the chosen city's coordinates are used as-is (city-level).
    cfg = config.default_config()
    cfg["location"] = {"lat": -33.8688, "lon": 151.2093, "name": "Sydney"}
    check("location_coords reads config", weather.location_coords(cfg) == (-33.8688, 151.2093))
    check("location_coords falls back on bad data",
          weather.location_coords({"location": {"lat": "x"}}) == (weather.LAT, weather.LON))
    # get_live_weather sends the city coordinates.
    seen = {}
    weather.get_weather = lambda lat, lon: (seen.update(lat=lat, lon=lon) or {
        "condition": "clear", "sunrise": None, "sunset": None, "is_day": True})
    weather.get_live_weather(cfg)
    check("live fetch uses city coords", seen == {"lat": -33.8688, "lon": 151.2093})

    # Offline fallback: force live fetch to fail.
    weather.get_weather = lambda *a, **k: (_ for _ in ()).throw(ConnectionError("no net"))
    try:
        cfg2 = config.default_config()  # manual_weather=auto
        w = weather.get_effective_weather(cfg2)
        check("offline fallback works", w["source"] == "fallback"
              and w["condition"] in weather.CONDITIONS)
        check("fallback has measurement keys (None)",
              all(k in w for k in weather.MEASUREMENT_KEYS))
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


def test_day_phase():
    section("time-of-day phases")
    import datetime as dt
    sr = dt.datetime.combine(dt.date.today(), dt.time(6, 0))
    ss = dt.datetime.combine(dt.date.today(), dt.time(20, 0))

    def at(h, m=0):
        return dt.datetime.combine(dt.date.today(), dt.time(h, m))

    expected = {3: "night", 6: "sunrise", 8: "morning", 13: "midday",
                17: "afternoon", 20: "sunset", 21: "night", 23: "night"}
    for h, want in expected.items():
        check(f"{h:02d}:00 -> {want}", theme.compute_day_phase(sr, ss, at(h)) == want)
    # Night arrives soon after sunset: sunset(20:00) -> dusk ~20:30 -> night ~20:45.
    check("20:30 -> dusk", theme.compute_day_phase(sr, ss, at(20, 30)) == "dusk")
    check("20:50 -> night (soon after sunset)",
          theme.compute_day_phase(sr, ss, at(20, 50)) == "night")

    # Brightness ordering across phases.
    check("midday is brightest", theme.phase_light("midday")[0] == 1.0)
    check("night is darkest phase", theme.phase_light("night")[0] < 0.2)
    check("sunset dimmer than midday",
          theme.phase_light("sunset")[0] < theme.phase_light("midday")[0])

    # Sunrise/sunset tints are warmer (red-vs-blue) than midday's neutral light.
    blue = (80, 160, 255)
    warmth = lambda p: (lambda c: c[0] - c[2])(theme.apply_phase_tint(blue, p))
    check("sunset warmer than midday", warmth("sunset") > warmth("midday"))
    check("sunrise warmer than midday", warmth("sunrise") > warmth("midday"))

    # normalize + manual mapping.
    check("day normalizes to midday", theme.normalize_phase("day") == "midday")
    check("unknown phase -> None", theme.normalize_phase("teatime") is None)
    check("all TIME_CHOICES phases valid",
          all(theme.normalize_phase(p) for p in config.TIME_CHOICES if p != "auto"))

    # Manual phase flows through compute_theme_color with its own brightness.
    (_c, b_mid) = theme.compute_theme_color("clear", sr, ss, phase="midday")
    (_c2, b_night) = theme.compute_theme_color("clear", sr, ss, phase="night")
    check("phase midday full brightness", b_mid == 1.0)
    check("phase night dim", b_night < 0.2)

    # Sun tracks east -> west across the day, and is down at night/dusk.
    check("sun rises in the east (low frac)", theme.phase_sun_fraction("sunrise") < 0.25)
    check("sun sets in the west (high frac)", theme.phase_sun_fraction("sunset") > 0.75)
    check("sunrise east of sunset",
          theme.phase_sun_fraction("sunrise") < theme.phase_sun_fraction("sunset"))
    check("no sun at night", theme.phase_sun_fraction("night") is None)
    check("day_fraction ~0.5 at solar noon",
          abs(theme.day_fraction(sr, ss, at(13)) - 0.5) < 0.01)
    check("day_fraction None before sunrise", theme.day_fraction(sr, ss, at(3)) is None)

    # Moon arcs across the night: 0 just after sunset -> 1 near sunrise.
    check("night_fraction None during day", theme.night_fraction(sr, ss, at(13)) is None)
    just_after = theme.night_fraction(sr, ss, at(20, 30))
    pre_dawn = theme.night_fraction(sr, ss, at(5, 30))
    check("moon low just after sunset", just_after is not None and just_after < 0.2)
    check("moon high near sunrise", pre_dawn is not None and pre_dawn > 0.8)
    check("moon travels through the night", just_after < pre_dawn)
    # celestial_fraction: sun by day, moon by night, never None.
    check("celestial uses sun by day",
          abs(theme.celestial_fraction(None, sr, ss, at(13)) - 0.5) < 0.01)
    check("celestial uses moon by night",
          theme.celestial_fraction(None, sr, ss, at(23)) is not None)

    # Vivid, distinct accents (not grey): dawn/dusk warm, noon blue.
    csr = theme.compute_theme_color("clear", sr, ss, phase="sunset")[0]
    cmd = theme.compute_theme_color("clear", sr, ss, phase="midday")[0]
    check("sunset accent is Orange", theme._nearest_macos_accent(*csr)[0] == "Orange")
    check("midday accent is Blue", theme._nearest_macos_accent(*cmd)[0] == "Blue")
    check("sunset is warm (r > b)", csr[0] > csr[2])

    # is_night mapping used by the rest of the app.
    check("night phase is night", theme.phase_is_night("night"))
    check("sunset phase is not night", not theme.phase_is_night("sunset"))
    for mt, night in [("sunset", False), ("midday", False), ("night", True)]:
        cfg = config.default_config()
        cfg["manual_time"] = mt
        w = weather.get_effective_weather(cfg)
        check(f"manual '{mt}' is_night={night}", w["is_night"] is night)

    # Appearance lock: auto follows brightness, dark/light force it.
    check("auto dark when dim", theme.resolve_appearance(0.2, "auto") == "dark")
    check("auto light when bright", theme.resolve_appearance(0.9, "auto") == "light")
    check("locked dark ignores brightness", theme.resolve_appearance(0.9, "dark") == "dark")
    check("locked light ignores brightness", theme.resolve_appearance(0.1, "light") == "light")
    # A locked appearance changes the theme signature (so it re-applies).
    check("appearance in signature",
          theme.theme_signature(40, 80, 180, 0.9, "dark")[0] == "dark")
    check("signature auto vs lock differ",
          theme.theme_signature(40, 80, 180, 0.9, "auto") !=
          theme.theme_signature(40, 80, 180, 0.9, "dark"))

    # apply (stub the OS setters)
    o1, o2 = theme.set_macos_theme, theme.set_windows_accent
    theme.set_macos_theme = lambda *a, **k: None
    theme.set_windows_accent = lambda *a, **k: None
    try:
        desc = theme.apply_theme_color(40, 80, 180, 0.2)
        check("apply returns description", isinstance(desc, str) and len(desc) > 0)
        # A locked-dark apply reports dark (or the platform is unsupported).
        desc2 = theme.apply_theme_color(40, 80, 180, 0.9, "dark")
        check("locked-dark apply reports dark",
              "dark" in desc2.lower() or desc2 == "unsupported platform")
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
            # Cleanup keeps the cache small but never deletes the just-built
            # file (nor the recent ones) — building many leaves a bounded set
            # that always includes the latest.
            last = path
            for i in range(8):
                last = wallpaper.build_weather_image(10 + i, 20, 30, 0.3, 0.5,
                                                     width=64, height=48)
            pngs = [f for f in os.listdir(d) if f.endswith(".png")]
            check("cache stays small", len(pngs) <= 5)
            check("latest wallpaper kept", os.path.basename(last) in pngs)
        finally:
            wallpaper.CACHE_DIR = orig


def _chroma(rgb):
    return max(rgb) - min(rgb)


def test_profiles():
    section("mood profiles")
    import profiles
    check("names present", profiles.PROFILE_NAMES == ["focus", "creativity", "relax"])
    check("none => unchanged colour", profiles.adjust_color((60, 120, 200), "none") == (60, 120, 200))
    check("focus desaturates", _chroma(profiles.adjust_color((60, 120, 200), "focus")) <
          _chroma((60, 120, 200)))
    check("creativity saturates", _chroma(profiles.adjust_color((120, 140, 160), "creativity")) >
          _chroma((120, 140, 160)))
    warm = profiles.adjust_color((90, 120, 170), "relax")
    check("relax warms (r-b rises)", (warm[0] - warm[2]) > (90 - 170))

    # Profiles SCALE the user's chosen volume (so the slider always matters),
    # they never replace it with a fixed number.
    base = {"sound_volume": 40}
    check("none overlay is identity", profiles.overlay_config(base, "none") is base)
    foc = profiles.overlay_config(base, "focus")
    check("focus quiets the slider volume", foc["sound_volume"] == 20)   # 40 * 0.5
    rel = profiles.overlay_config(base, "relax")
    check("relax lifts the slider volume", rel["sound_volume"] == 56)    # 40 * 1.4
    # A different slider level scales differently — the slider is respected.
    louder = profiles.overlay_config({"sound_volume": 80}, "focus")
    check("higher slider => higher profile volume", louder["sound_volume"] == 40)
    check("overlay is non-destructive", base["sound_volume"] == 40)


def test_seasons():
    section("seasons")
    import datetime as dt
    check("north july = summer", theme.season_for(dt.date(2026, 7, 15), "north") == "summer")
    check("south july = winter", theme.season_for(dt.date(2026, 7, 15), "south") == "winter")
    check("north dec = winter", theme.season_for(dt.date(2026, 12, 15), "north") == "winter")
    check("hemisphere from -lat = south", theme.hemisphere_for(-33.8, "auto") == "south")
    check("hemisphere from +lat = north", theme.hemisphere_for(51.5, "auto") == "north")
    check("explicit hemisphere wins", theme.hemisphere_for(-33.8, "north") == "north")
    sr = dt.datetime(2026, 7, 15, 6, 0)
    ss = dt.datetime(2026, 7, 15, 20, 0)
    plain = theme.compute_theme_color("clear", sr, ss, phase="midday")[0]
    autumn = theme.compute_theme_color("clear", sr, ss, phase="midday", season="autumn")[0]
    check("season changes the colour", autumn != plain)
    check("autumn is warmer (more red)", autumn[0] > plain[0])


def test_transitions():
    section("gradual transitions")
    # Easing moves partway, converges, and is a no-op when instant.
    step1 = engine._ease_rgb((0, 0, 0), (100, 0, 0), 1.0, 9.0)
    check("ease moves toward target", 0 < step1[0] < 100)
    cur = (0, 0, 0)
    for _ in range(60):
        cur = engine._ease_rgb(cur, (100, 0, 0), 1.0, 9.0)
    check("ease converges", abs(cur[0] - 100) < 2)
    check("ease from None snaps to target", engine._ease_rgb(None, (50, 60, 70), 1, 9) == (50, 60, 70))
    check("ease duration 0 snaps", engine._ease_rgb((0, 0, 0), (100, 0, 0), 1, 0) == (100, 0, 0))

    # Continuous sky light: a 2-minute step produces only a tiny colour change
    # (no sudden phase jump).
    import datetime as dt
    sr = dt.datetime(2026, 6, 1, 6, 0)
    ss = dt.datetime(2026, 6, 1, 20, 0)
    def at(h, m):
        return dt.datetime(2026, 6, 1, h, m)
    near_sunset_a = theme.compute_theme_color("clear", sr, ss, now=at(19, 58))[0]
    near_sunset_b = theme.compute_theme_color("clear", sr, ss, now=at(20, 0))[0]
    delta = max(abs(near_sunset_a[i] - near_sunset_b[i]) for i in range(3))
    check("time transition is gradual (small step)", delta < 12)


def test_high_contrast():
    section("accessibility — high contrast")
    hc = theme.high_contrast((90, 120, 170))
    check("high contrast maximises saturation", _chroma(hc) > _chroma((90, 120, 170)))
    check("high contrast keeps it a strong colour", max(hc) >= 200)
    grey = theme.high_contrast((128, 128, 128))
    check("grey becomes a bold colour", grey in [(255, 255, 0), (10, 10, 10)])

    # Config helper maps the new keys.
    import gui
    cfg = gui.apply_values_to_config(config.default_config(), {
        "enabled": True, "dynamic_theme": True, "wallpaper": True, "ambient_sound": True,
        "tasks": True, "tint": 40, "volume": 25, "tick_interval": 30, "weather_refresh": 600,
        "wallpaper_dynamic": True, "wallpaper_shift": 35, "p_work": 25, "p_break": 5,
        "p_long": 15, "p_cycles": 4, "manual_weather": "auto", "manual_time": "auto",
        "manual_theme_color": "auto", "run_at_login": False,
        "active_profile": "relax", "accessibility_mode": "high_contrast",
        "hemisphere": "south", "seasonal_themes": False, "multi_monitor": False,
        "smooth_transitions": False,
    })
    check("profile mapped", cfg["active_profile"] == "relax")
    check("accessibility mapped", cfg["accessibility_mode"] == "high_contrast")
    check("hemisphere mapped", cfg["hemisphere"] == "south")
    check("seasonal toggle mapped", cfg["seasonal_themes"] is False)
    check("multi-monitor mapped", cfg["multi_monitor"] is False)
    check("smooth toggle mapped", cfg["smooth_transitions"] is False)
    check("bad profile falls back to none",
          gui.apply_values_to_config(config.default_config(),
                                     {**_gui_min_values(), "active_profile": "banana"}
                                     )["active_profile"] == "none")


def _gui_min_values():
    return {"enabled": True, "dynamic_theme": True, "wallpaper": True, "ambient_sound": True,
            "tasks": True, "tint": 40, "volume": 25, "tick_interval": 30, "weather_refresh": 600,
            "wallpaper_dynamic": True, "wallpaper_shift": 35, "p_work": 25, "p_break": 5,
            "p_long": 15, "p_cycles": 4, "manual_weather": "auto", "manual_time": "auto",
            "manual_theme_color": "auto", "run_at_login": False}



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
    for cond in ("clear", "cloud", "rain", "storm", "night", "cloudnight"):
        check(f"{cond} pattern paints pixels", paints(cond))

    # Cloudy night differs from a clear night (clouds added), and the moon
    # position tracks the `sun` fraction (east vs west).
    def render(cond, sun):
        w, h = 80, 60
        raw, st = wallpaper._build_raw_gradient(w, h, (20, 26, 50), (5, 8, 20))
        wallpaper._render_pattern(cond, raw, st, w, h, 0.3, 0.15, sun)
        return bytes(raw)
    check("cloudy night != clear night", render("cloudnight", 0.5) != render("night", 0.5))
    check("moon moves east->west", render("night", 0.1) != render("night", 0.9))

    # Engine picks the right wallpaper condition for the sky.
    check("clear night -> night", engine._pattern_condition("clear", True) == "night")
    check("cloudy night -> cloudnight", engine._pattern_condition("cloud", True) == "cloudnight")
    check("cloudy day stays cloud", engine._pattern_condition("cloud", False) == "cloud")
    check("rain at night stays rain", engine._pattern_condition("rain", True) == "rain")

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
    check("rain->rain", sound.select_ambient("rain", False).endswith("rain.wav"))
    check("storm->storm", sound.select_ambient("storm", False).endswith("storm.wav"))
    check("clear day->clearday", sound.select_ambient("clear", False).endswith("clearday.wav"))
    check("clear night->clearnight", sound.select_ambient("clear", True).endswith("clearnight.wav"))
    check("night->clearnight", sound.select_ambient("night", True).endswith("clearnight.wav"))
    check("cloud->cloud", sound.select_ambient("cloud", False).endswith("cloud.wav"))

    with tempfile.TemporaryDirectory() as d:
        created = sound.ensure_placeholder_sounds(directory=d)
        check("placeholders created", len(created) == 6)
        sample = os.path.join(d, "rain.wav")
        with wave.open(sample, "rb") as wf:
            check("wav mono 16-bit", wf.getnchannels() == 1 and wf.getsampwidth() == 2)
            check("wav has frames", wf.getnframes() > 1000)
        # second call creates nothing new
        again = sound.ensure_placeholder_sounds(directory=d)
        check("placeholders idempotent", again == [])


def test_music():
    section("music player")
    import music
    check("music dir is absolute", os.path.isabs(music.MUSIC_DIR))
    with tempfile.TemporaryDirectory() as d:
        for fn in ["b_song.mp3", "a_song.ogg", "tune.wav", "notes.txt", "cover.jpg"]:
            open(os.path.join(d, fn), "wb").close()
        tracks = music.list_tracks(d)
        check("only audio files listed", len(tracks) == 3)
        check("tracks sorted by name",
              [os.path.basename(t) for t in tracks] == ["a_song.ogg", "b_song.mp3", "tune.wav"])
        check("non-audio excluded",
              not any(t.endswith((".txt", ".jpg")) for t in tracks))
    # Playback degrades gracefully when audio is unavailable (no crash).
    o = sound._ensure_mixer
    sound._ensure_mixer = lambda: False
    try:
        check("play returns False without audio", music.play("nope.mp3") is False)
        check("is_playing False without audio", music.is_playing() is False)
        music.set_volume(50)   # no-op, must not raise
    finally:
        sound._ensure_mixer = o


def test_duck_other_audio():
    section("pause ambient for other audio")
    import music
    import audiocheck
    o_music, o_ext = music.is_playing, audiocheck.external_audio_active
    music.is_playing = lambda: False
    audiocheck.external_audio_active = lambda: False
    try:
        off = config.default_config()             # external-audio toggle off
        check("nothing playing => no duck", engine.other_audio_playing(off) is False)

        # Priority: our music ALWAYS ducks ambient, even with the toggle off.
        music.is_playing = lambda: True
        check("our music ducks ambient even with toggle off",
              engine.other_audio_playing(off) is True)
        music.is_playing = lambda: False

        # External-app audio only ducks ambient when the toggle is on.
        audiocheck.external_audio_active = lambda: True
        check("external audio ignored while toggle off",
              engine.other_audio_playing(off) is False)
        on = config.default_config()
        on["pause_when_other_audio"] = True
        check("external audio ducks when toggle on",
              engine.other_audio_playing(on) is True)
        audiocheck.external_audio_active = lambda: None   # unknown platform
        check("unknown => no duck", engine.other_audio_playing(on) is False)
    finally:
        music.is_playing, audiocheck.external_audio_active = o_music, o_ext

    # Engine stops ambient while other audio plays, resumes after.
    import audiocheck as ac
    saved = (theme.apply_theme_color, wallpaper.apply_weather_wallpaper,
             sound.play_ambient, sound.stop_sound, sound.set_volume,
             sound.pick_base, weather.get_weather, ac.external_audio_active,
             music.is_playing)
    counts = {"play": 0, "stop": 0}
    theme.apply_theme_color = lambda *a, **k: "t"
    wallpaper.apply_weather_wallpaper = lambda *a, **k: True
    sound.play_ambient = lambda *a, **k: counts.__setitem__("play", counts["play"] + 1)
    sound.stop_sound = lambda *a, **k: counts.__setitem__("stop", counts["stop"] + 1)
    sound.set_volume = lambda *a, **k: None
    sound.pick_base = lambda *a, **k: "x"
    music.is_playing = lambda: False
    sr = datetime.datetime.combine(datetime.date.today(), datetime.time(6, 0))
    ss = datetime.datetime.combine(datetime.date.today(), datetime.time(20, 0))
    weather.get_weather = lambda *a, **k: {
        "condition": "clear", "sunrise": sr, "sunset": ss, "is_day": True,
        "temperature": 15, "feels_like": 15, "humidity": 50, "uv_index": 3,
        "uv_index_max": 5, "pressure": 1010, "rain": 0, "precip_chance": 0,
        "wind_speed": 5, "wind_gust": 8, "wind_dir": 180, "cloud_cover": 10}
    try:
        cfg = config.default_config()
        cfg["manual_time"] = "midday"
        cfg["pause_when_other_audio"] = True
        cfg["features"]["wallpaper"] = False
        eng = engine.Engine()
        t0 = datetime.datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
        ac.external_audio_active = lambda: False
        eng.step(cfg, None, now=t0)
        check("ambient plays when nothing else is", counts["play"] == 1)
        ac.external_audio_active = lambda: True
        eng.step(cfg, None, now=t0)
        check("ambient stops when other audio starts", counts["stop"] >= 1)
        base_plays = counts["play"]
        ac.external_audio_active = lambda: False
        eng.step(cfg, None, now=t0)
        check("ambient resumes after other audio stops", counts["play"] == base_plays + 1)
    finally:
        (theme.apply_theme_color, wallpaper.apply_weather_wallpaper,
         sound.play_ambient, sound.stop_sound, sound.set_volume,
         sound.pick_base, weather.get_weather, ac.external_audio_active,
         music.is_playing) = saved


def test_audio_priority():
    section("audio priority: chime > music > ambient")

    class FakeMusic:
        def __init__(self, busy, vol):
            self._busy, self.vol = busy, vol
        def get_busy(self):
            return self._busy
        def get_volume(self):
            return self.vol
        def set_volume(self, v):
            self.vol = v

    class FakeMixer:
        def __init__(self, music):
            self.music = music

    class FakeSnd:
        def __init__(self, v):
            self.vol = v
        def set_volume(self, v):
            self.vol = v

    o = (sound._mixer, sound.current_sound, sound._current_volume, sound._music_prev_vol)
    try:
        # Music + ambient both playing: a chime ducks BOTH, then restores.
        fm = FakeMusic(busy=True, vol=0.6)
        sound._mixer = FakeMixer(fm)
        amb = FakeSnd(0.25)
        sound.current_sound = amb
        sound._current_volume = 0.25
        sound._music_prev_vol = None

        sound._duck_for_chime()
        check("chime ducks the music stream", fm.vol < 0.6)
        check("chime ducks the ambient loop", amb.vol < 0.25)
        check("music level remembered for restore", sound._music_prev_vol == 0.6)

        sound._restore_after_chime()
        check("music restored to its level", abs(fm.vol - 0.6) < 1e-9)
        check("ambient restored to its level", abs(amb.vol - 0.25) < 1e-9)
        check("duck state cleared", sound._music_prev_vol is None)

        # No music playing: nothing to duck/remember for the music stream.
        fm2 = FakeMusic(busy=False, vol=0.5)
        sound._mixer = FakeMixer(fm2)
        sound.current_sound = None
        sound._music_prev_vol = None
        sound._duck_for_chime()
        check("silent music not ducked", abs(fm2.vol - 0.5) < 1e-9)
        check("no duck state when music silent", sound._music_prev_vol is None)
    finally:
        (sound._mixer, sound.current_sound, sound._current_volume,
         sound._music_prev_vol) = o


def test_sound_variants_and_modes():
    section("sound variants + random mode")
    import random as _r
    import datetime as dt

    # --- variant discovery -------------------------------------------
    with tempfile.TemporaryDirectory() as d:
        for fn in ["rain.wav", "rain2.wav", "rain-heavy.wav",
                   "cloud.wav", "clearday.wav", "clearnight.wav", "chime.wav"]:
            open(os.path.join(d, fn), "wb").close()
        v = sound.list_variants("rain", d)
        check("finds all rain*.wav variants", len(v) == 3)
        check("variants are all rain files",
              all("rain" in os.path.basename(x) for x in v))
        cd = sound.list_variants("clearday", d)
        check("clearday not matched by clearnight",
              len(cd) == 1 and cd[0].endswith("clearday.wav"))
        pick = sound.pick_variant("rain", False, d, rng=_r.Random(0))
        check("pick_variant returns a real variant", pick in v)
        check("pick_variant falls back to base when none",
              sound.pick_variant("storm", False, d).endswith("storm.wav"))
        check("pick_base picks a cloud variant",
              sound.pick_base("cloud", d).endswith("cloud.wav"))

    # --- wind picks the cloud (windy) ambience -----------------------
    check("calm clear day -> clearday", sound.ambient_base("clear", False, 5) == "clearday")
    check("windy clear day -> cloud", sound.ambient_base("clear", False, 40) == "cloud")
    check("windy clear night -> cloud", sound.ambient_base("clear", True, 40) == "cloud")
    check("wind doesn't override rain", sound.ambient_base("rain", False, 40) == "rain")
    check("cloudy stays cloud", sound.ambient_base("cloud", False, 0) == "cloud")
    check("sounds dir is absolute", os.path.isabs(sound.SOUNDS_DIR))

    # --- engine random mode: occasional, not continuous --------------
    counts = {"play": 0, "stop": 0}
    saved = (sound.play_ambient, sound.stop_sound, sound.set_volume,
             sound.pick_variant, theme.apply_theme_color,
             wallpaper.apply_weather_wallpaper)
    sound.play_ambient = lambda *a, **k: counts.__setitem__("play", counts["play"] + 1)
    sound.stop_sound = lambda *a, **k: counts.__setitem__("stop", counts["stop"] + 1)
    sound.set_volume = lambda *a, **k: None
    sound.pick_variant = lambda *a, **k: "sounds/rain.wav"
    theme.apply_theme_color = lambda *a, **k: "t"
    wallpaper.apply_weather_wallpaper = lambda *a, **k: True
    try:
        cfg = config.default_config()
        cfg["manual_weather"] = "rain"
        cfg["sound_mode"] = "random"
        cfg["sound_interval_minutes"] = 5
        cfg["features"]["wallpaper"] = False
        eng = engine.Engine()
        t0 = dt.datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
        eng.step(cfg, None, now=t0)
        check("random plays once at start", counts["play"] == 1)
        eng.step(cfg, None, now=t0)
        check("random not replayed immediately", counts["play"] == 1)
        eng.step(cfg, None, now=t0 + dt.timedelta(minutes=20))
        check("random replays after the interval", counts["play"] == 2)
    finally:
        (sound.play_ambient, sound.stop_sound, sound.set_volume,
         sound.pick_variant, theme.apply_theme_color,
         wallpaper.apply_weather_wallpaper) = saved


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

        # Future-dated one-off (as the GUI now assembles it: "YYYY-MM-DDT HH:MM").
        future_day = datetime.date.today() + datetime.timedelta(days=3)
        tf = store.add_task("Future", type="once",
                            datetime_str=f"{future_day.isoformat()}T09:00")
        check("future task not due today", tf not in store.due_tasks(now))
        at_future = datetime.datetime.combine(future_day, datetime.time(9, 30))
        check("future task due on the day", tf in store.due_tasks(at_future))
        store.remove_task(tf["id"])

        # GUI row formatting (plain-English, no raw internals).
        import gui
        check("daily 'when' reads friendly",
              gui._task_when_str({"type": "daily", "time": "07:30"}) == "Every day · 07:30")
        check("once 'when' shows a date",
              "·" in gui._task_when_str({"type": "once", "datetime": "2026-08-01T09:00"}))
        check("does shows weather target",
              gui._task_does_str({"action": "set_weather", "action_value": "rain"}) == "Weather → rain")
        check("notify does is friendly",
              gui._task_does_str({"action": "notify"}) == "Notify me")

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
def test_bugfixes():
    section("regression tests (fixed bugs)")
    import datetime as dt
    sr = dt.datetime.combine(dt.date.today(), dt.time(6, 0))
    ss = dt.datetime.combine(dt.date.today(), dt.time(20, 0))
    saved = (theme.apply_theme_color, wallpaper.apply_weather_wallpaper,
             sound.play_ambient, sound.stop_sound, sound.set_volume,
             sound.pick_base, weather.get_weather)
    counts = {"theme": 0, "wall": 0, "stop": 0}
    theme.apply_theme_color = lambda *a, **k: counts.__setitem__("theme", counts["theme"] + 1) or "t"
    wallpaper.apply_weather_wallpaper = lambda *a, **k: counts.__setitem__("wall", counts["wall"] + 1) or True
    sound.play_ambient = lambda *a, **k: None
    sound.stop_sound = lambda *a, **k: counts.__setitem__("stop", counts["stop"] + 1)
    sound.set_volume = lambda *a, **k: None
    sound.pick_base = lambda *a, **k: "x"
    weather.get_weather = lambda *a, **k: {
        "condition": "clear", "sunrise": sr, "sunset": ss, "is_day": True,
        "temperature": 15, "feels_like": 15, "humidity": 50, "uv_index": 3,
        "uv_index_max": 5, "pressure": 1010, "rain": 0, "precip_chance": 0,
        "wind_speed": 5, "wind_gust": 8, "wind_dir": 180, "cloud_cover": 10}

    def at(h):
        return dt.datetime.combine(dt.date.today(), dt.time(h, 0))

    try:
        # BUG: day/night was derived from the real clock, not the injected
        # `now` — so the engine was non-deterministic. It must follow `now`.
        eng = engine.Engine()
        cfg = config.default_config()
        s_noon = eng.step(cfg, None, now=at(12))
        s_night = eng.step(cfg, None, now=at(23))
        check("day at noon (injected now)", s_noon["is_night"] is False)
        check("night at 23:00 (injected now)", s_night["is_night"] is True)

        # BUG: a pinned manual accent kept overriding the weather theme; clearing
        # it (None) must let the colour follow the weather again.
        cfg2 = config.default_config()
        cfg2["manual_weather"] = "clear"
        cfg2["manual_theme_color"] = [10, 20, 30]
        st = engine.tick(cfg2, None)
        check("pinned accent is used", st["color"] == [10, 20, 30]
              and st["color_source"] == "manual")
        cfg2["manual_theme_color"] = None
        st2 = engine.tick(cfg2, None)
        check("unpinned accent follows the weather",
              st2["color"] != [10, 20, 30] and st2["color_source"] == "computed")

        # BUG: the master switch "did nothing". Off => engine applies nothing
        # and silences sound.
        counts.update(theme=0, wall=0, stop=0)
        cfg3 = config.default_config()
        cfg3["enabled"] = False
        eng3 = engine.Engine()
        eng3._sound_on = True
        st3 = eng3.step(cfg3, None, now=at(12))
        check("master off => not enabled", st3["enabled"] is False and "note" in st3)
        check("master off applies no theme/wallpaper", counts["theme"] == 0 and counts["wall"] == 0)
        check("master off stops sound", counts["stop"] >= 1)

        # BUG: ambient wouldn't stop when the feature was turned off.
        counts.update(theme=0, wall=0, stop=0)
        cfg4 = config.default_config()
        cfg4["features"]["ambient_sound"] = False
        eng4 = engine.Engine()
        eng4._sound_on = True
        eng4.step(cfg4, None, now=at(12))
        check("ambient off stops the sound", counts["stop"] >= 1)

        # BUG: a picked accent didn't apply while the engine ran, because the
        # change-guards suppressed it. Dropping _last_theme/_last_wall_at (what
        # the GUI now does on a manual change) must force a re-apply even when
        # the theme signature is unchanged.
        counts.update(theme=0, wall=0)
        cfg5 = config.default_config()
        cfg5["manual_time"] = "midday"
        cfg5["manual_weather"] = "clear"
        cfg5["wallpaper_min_interval_seconds"] = 0
        cfg5["smooth_transitions"] = False
        eng5 = engine.Engine()
        eng5.step(cfg5, None, now=at(12))
        base = counts["theme"]
        eng5.step(cfg5, None, now=at(12))
        check("unchanged step skips re-apply", counts["theme"] == base)
        eng5._last_theme = None
        eng5._last_wall_at = None
        eng5.step(cfg5, None, now=at(12))
        check("guard reset forces immediate re-apply", counts["theme"] == base + 1)

        # BUG: picking an accent colour "did nothing" — the cross-fade eased the
        # display slowly from the old colour while the wallpaper redraw stayed
        # throttled, so the pick was barely visible. A manual colour must snap to
        # full strength on the very first step, even mid cross-fade.
        cfg6 = config.default_config()
        cfg6["smooth_transitions"] = True          # easing ON (the hard case)
        cfg6["theme_transition_seconds"] = 8
        eng6 = engine.Engine()
        eng6._eased_rgb = (140.0, 118.0, 162.0)    # a stale "purple" mid-fade
        eng6._eased_at = at(12)
        eng6.step(cfg6, None, now=at(12))           # dt≈0 => easing would barely move
        # (no manual colour yet — establishes the eased baseline)
        cfg6["manual_theme_color"] = [0, 238, 0]    # user picks green
        st6b = eng6.step(cfg6, None, now=at(12))
        check("manual colour snaps to full strength at once",
              st6b["color"] == [0, 238, 0] and st6b["color_source"] == "manual")
        check("manual colour is not left mid-transition",
              eng6.transitioning is False)
    finally:
        (theme.apply_theme_color, wallpaper.apply_weather_wallpaper,
         sound.play_ambient, sound.stop_sound, sound.set_volume,
         sound.pick_base, weather.get_weather) = saved


def test_city_change_refetch():
    section("changing city refetches weather immediately")
    import datetime as dt
    o_get = weather.get_weather
    sr = dt.datetime.combine(dt.date.today(), dt.time(6, 0))
    ss = dt.datetime.combine(dt.date.today(), dt.time(20, 0))
    # Rain in the south, clear in the north — keyed by latitude sign.
    def fake(lat, lon):
        return {"condition": "rain" if lat < 0 else "clear",
                "sunrise": sr, "sunset": ss, "is_day": True, "temperature": 15,
                "feels_like": 15, "humidity": 50, "uv_index": 3, "uv_index_max": 5,
                "pressure": 1010, "rain": 0, "precip_chance": 0, "wind_speed": 5,
                "wind_gust": 8, "wind_dir": 180, "cloud_cover": 10}
    weather.get_weather = fake
    try:
        eng = engine.Engine()
        cfg = config.default_config()
        cfg["features"] = {"dynamic_theme": False, "wallpaper": False,
                           "ambient_sound": False, "tasks": False}
        cfg["weather_refresh_seconds"] = 600      # long cache window
        now = dt.datetime.combine(dt.date.today(), dt.time(12, 0))
        cfg["location"] = {"lat": -33.8, "lon": 151.2, "name": "Sydney"}
        s1 = eng.step(cfg, None, now=now)
        check("first city fetched", s1["condition"] == "rain")
        # Same `now` (well inside the cache window): the OLD code would keep the
        # stale rain; the fix refetches because the location changed.
        cfg["location"] = {"lat": 51.5, "lon": -0.1, "name": "London"}
        s2 = eng.step(cfg, None, now=now)
        check("city change refetches (not stuck on old weather)",
              s2["condition"] == "clear")
        # Same city again within the window => still cached (no needless refetch).
        calls = {"n": 0}
        def counted(lat, lon):
            calls["n"] += 1
            return fake(lat, lon)
        weather.get_weather = counted
        eng.step(cfg, None, now=now)
        check("same city stays cached", calls["n"] == 0)
    finally:
        weather.get_weather = o_get


def test_task_recolors_now():
    section("task changes the background promptly")
    import datetime as dt
    o_notify, o_chime, o_save = engine.notify, sound.play_chime, config.save_config
    engine.notify = lambda *a, **k: None
    sound.play_chime = lambda *a, **k: None
    config.save_config = lambda *a, **k: True   # never touch the real config file
    try:
        check("set_weather is a visual change",
              engine._run_task_action({"action": "set_weather", "action_value": "storm"},
                                      config.default_config()) is True)
        check("set_theme is a visual change",
              engine._run_task_action({"action": "set_theme", "action_value": "255,0,0"},
                                      config.default_config()) is True)
        check("notify is not a visual change",
              engine._run_task_action({"action": "notify"}, {}) is False)
    finally:
        engine.notify, sound.play_chime, config.save_config = o_notify, o_chime, o_save

    # A due weather task resets the wallpaper/theme guards so the new look
    # applies at once instead of waiting out the redraw interval.
    saved = (theme.apply_theme_color, wallpaper.apply_weather_wallpaper,
             sound.play_ambient, sound.stop_sound, sound.set_volume,
             sound.pick_base, weather.get_weather, config.save_config)
    theme.apply_theme_color = lambda *a, **k: "t"
    wallpaper.apply_weather_wallpaper = lambda *a, **k: True
    sound.play_ambient = lambda *a, **k: None
    sound.stop_sound = lambda *a, **k: None
    sound.set_volume = lambda *a, **k: None
    sound.pick_base = lambda *a, **k: "x"
    config.save_config = lambda *a, **k: True         # keep the disk untouched
    sr = dt.datetime.combine(dt.date.today(), dt.time(6, 0))
    ss = dt.datetime.combine(dt.date.today(), dt.time(20, 0))
    weather.get_weather = lambda *a, **k: {
        "condition": "clear", "sunrise": sr, "sunset": ss, "is_day": True,
        "temperature": 15, "feels_like": 15, "humidity": 50, "uv_index": 3,
        "uv_index_max": 5, "pressure": 1010, "rain": 0, "precip_chance": 0,
        "wind_speed": 5, "wind_gust": 8, "wind_dir": 180, "cloud_cover": 10}
    try:
        with tempfile.TemporaryDirectory() as d:
            store = tasks_mod.TaskStore(os.path.join(d, "tasks.json"))
            t0 = dt.datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
            store.add_task("Storm", type="once",
                           datetime_str=(t0 - dt.timedelta(minutes=1)).isoformat(),
                           action="set_weather", action_value="storm")
            eng = engine.Engine()
            eng.step(config.default_config(), store, now=t0)
            check("wallpaper guard reset after task", eng._last_wall_at is None)
            check("engine marked transitioning", eng.transitioning is True)
    finally:
        (theme.apply_theme_color, wallpaper.apply_weather_wallpaper,
         sound.play_ambient, sound.stop_sound, sound.set_volume,
         sound.pick_base, weather.get_weather, config.save_config) = saved


def test_sun_tracking():
    section("sun tracks the real clock")
    import datetime as dt
    captured = {}
    o_wall, o_get = wallpaper.apply_weather_wallpaper, weather.get_weather
    wallpaper.apply_weather_wallpaper = lambda *a, **k: captured.update(sun=k.get("sun")) or True
    sr = dt.datetime.combine(dt.date.today(), dt.time(6, 0))
    ss = dt.datetime.combine(dt.date.today(), dt.time(20, 0))
    weather.get_weather = lambda *a, **k: {
        "condition": "clear", "sunrise": sr, "sunset": ss, "is_day": True,
        "temperature": 18, "feels_like": 18, "humidity": 50, "uv_index": 3,
        "uv_index_max": 5, "pressure": 1010, "rain": 0, "precip_chance": 0,
        "wind_speed": 5, "wind_gust": 8, "wind_dir": 180, "cloud_cover": 10}
    try:
        # A step computes the sun position from `now` and forwards it to the
        # wallpaper — so the sun follows the real clock, not a stale value.
        cfg = config.default_config()
        cfg["features"]["dynamic_theme"] = False
        engine.Engine().step(cfg, None, now=dt.datetime.combine(dt.date.today(), dt.time(13, 0)))
        expect = theme.celestial_fraction(None, sr, ss,
                                          dt.datetime.combine(dt.date.today(), dt.time(13, 0)))
        check("step forwards the live sun to the wallpaper",
              captured.get("sun") is not None and abs(captured["sun"] - expect) < 0.02)

        # Time passing moves the sun west (fixed times, clock-independent).
        s1 = theme.celestial_fraction(None, sr, ss, dt.datetime.combine(dt.date.today(), dt.time(10, 0)))
        s2 = theme.celestial_fraction(None, sr, ss, dt.datetime.combine(dt.date.today(), dt.time(14, 0)))
        check("sun advances with time", s2 > s1)
    finally:
        wallpaper.apply_weather_wallpaper, weather.get_weather = o_wall, o_get


def test_wallpaper_no_revert():
    section("wallpaper never deletes the displayed file")
    with tempfile.TemporaryDirectory() as d:
        orig, prev = wallpaper.CACHE_DIR, wallpaper._applied_path
        wallpaper.CACHE_DIR = d
        wallpaper._applied_path = None
        try:
            shown = wallpaper.build_weather_image(40, 80, 180, 0.6, condition="clear",
                                                  width=48, height=32)
            wallpaper._applied_path = shown          # the OS is now showing this file
            for i in range(8):                        # lots of new frames + cleanup
                wallpaper.build_weather_image(10 + i, 20, 30, 0.3, condition="rain",
                                              width=48, height=32)
            check("displayed file survives churn (no revert to default)",
                  os.path.isfile(shown))
        finally:
            wallpaper.CACHE_DIR, wallpaper._applied_path = orig, prev


def test_wallpaper_force_refresh():
    section("wallpaper periodic re-apply (fullscreen catch-up)")
    import datetime as dt
    counts = {"wall": 0}
    saved = (theme.apply_theme_color, wallpaper.apply_weather_wallpaper,
             sound.play_ambient, sound.stop_sound, sound.set_volume,
             sound.pick_variant, weather.get_weather)
    theme.apply_theme_color = lambda *a, **k: "t"
    wallpaper.apply_weather_wallpaper = lambda *a, **k: counts.__setitem__("wall", counts["wall"] + 1) or True
    sound.play_ambient = lambda *a, **k: None
    sound.stop_sound = lambda *a, **k: None
    sound.set_volume = lambda *a, **k: None
    sound.pick_variant = lambda *a, **k: "x"
    sr = dt.datetime.combine(dt.date.today(), dt.time(6, 0))
    ss = dt.datetime.combine(dt.date.today(), dt.time(20, 0))
    weather.get_weather = lambda *a, **k: {
        "condition": "clear", "sunrise": sr, "sunset": ss, "is_day": True,
        "temperature": 15, "feels_like": 15, "humidity": 50, "uv_index": 3,
        "uv_index_max": 5, "pressure": 1010, "rain": 0, "precip_chance": 0,
        "wind_speed": 5, "wind_gust": 8, "wind_dir": 180, "cloud_cover": 10}
    try:
        cfg = config.default_config()
        cfg["manual_time"] = "midday"
        cfg["wallpaper_dynamic"] = False
        cfg["wallpaper_min_interval_seconds"] = 0
        cfg["wallpaper_refresh_seconds"] = 90
        cfg["smooth_transitions"] = False
        t0 = dt.datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
        eng = engine.Engine()
        eng.step(cfg, None, now=t0)
        eng.step(cfg, None, now=t0)                              # unchanged -> skip
        check("static drawn once then skipped", counts["wall"] == 1)
        eng.step(cfg, None, now=t0 + dt.timedelta(seconds=100))  # force refresh
        check("re-applies after the refresh interval", counts["wall"] == 2)

        counts["wall"] = 0
        cfg["wallpaper_refresh_seconds"] = 0                     # disable periodic
        eng2 = engine.Engine()
        eng2.step(cfg, None, now=t0)
        eng2.step(cfg, None, now=t0 + dt.timedelta(seconds=1000))
        check("no re-apply when refresh disabled", counts["wall"] == 1)
    finally:
        (theme.apply_theme_color, wallpaper.apply_weather_wallpaper,
         sound.play_ambient, sound.stop_sound, sound.set_volume,
         sound.pick_variant, weather.get_weather) = saved


def test_wallpaper_agent_warmup():
    section("macOS wallpaper agent restarted once (no grey flash per change)")
    import sys as _sys
    if _sys.platform != "darwin":
        check("skipped (not macOS)", True)
        return
    o = (wallpaper._set_wallpaper_macos, wallpaper._refresh_wallpaper_agent_macos,
         wallpaper._applied_path, wallpaper._agent_warmed)
    calls = {"refresh": 0}
    wallpaper._set_wallpaper_macos = lambda path, multi=True: True
    wallpaper._refresh_wallpaper_agent_macos = lambda: calls.__setitem__(
        "refresh", calls["refresh"] + 1)
    wallpaper._applied_path = None
    wallpaper._agent_warmed = False
    try:
        wallpaper.set_wallpaper("/tmp/a.png")
        wallpaper.set_wallpaper("/tmp/b.png")     # weather change
        wallpaper.set_wallpaper("/tmp/c.png")     # weather change
        check("agent restarted exactly once across many changes",
              calls["refresh"] == 1)
    finally:
        (wallpaper._set_wallpaper_macos, wallpaper._refresh_wallpaper_agent_macos,
         wallpaper._applied_path, wallpaper._agent_warmed) = o


def test_wallpaper_restore_on_disable():
    section("disabling weather wallpaper restores the original desktop")
    import datetime as dt
    saved = (theme.apply_theme_color, wallpaper.apply_weather_wallpaper,
             wallpaper.restore_original, wallpaper.is_showing_ours,
             sound.play_ambient, sound.stop_sound, sound.set_volume,
             sound.pick_base, weather.get_weather)
    counts = {"apply": 0, "restore": 0}
    theme.apply_theme_color = lambda *a, **k: "t"
    wallpaper.apply_weather_wallpaper = lambda *a, **k: counts.__setitem__("apply", counts["apply"] + 1) or True
    wallpaper.restore_original = lambda *a, **k: counts.__setitem__("restore", counts["restore"] + 1) or True
    wallpaper.is_showing_ours = lambda: True
    sound.play_ambient = lambda *a, **k: None
    sound.stop_sound = lambda *a, **k: None
    sound.set_volume = lambda *a, **k: None
    sound.pick_base = lambda *a, **k: "x"
    sr = dt.datetime.combine(dt.date.today(), dt.time(6, 0))
    ss = dt.datetime.combine(dt.date.today(), dt.time(20, 0))
    weather.get_weather = lambda *a, **k: {
        "condition": "clear", "sunrise": sr, "sunset": ss, "is_day": True,
        "temperature": 15, "feels_like": 15, "humidity": 50, "uv_index": 3,
        "uv_index_max": 5, "pressure": 1010, "rain": 0, "precip_chance": 0,
        "wind_speed": 5, "wind_gust": 8, "wind_dir": 180, "cloud_cover": 10}
    try:
        now = dt.datetime.combine(dt.date.today(), dt.time(12, 0))
        cfg = config.default_config()
        cfg["features"]["ambient_sound"] = False
        eng = engine.Engine()
        eng.step(cfg, None, now=now)
        check("wallpaper set while enabled", counts["apply"] == 1 and counts["restore"] == 0)

        cfg["features"]["wallpaper"] = False        # user unticks it
        eng.step(cfg, None, now=now)
        check("restores original once on disable", counts["restore"] == 1)
        eng.step(cfg, None, now=now)
        check("does not keep restoring while off", counts["restore"] == 1)

        cfg["features"]["wallpaper"] = True          # re-enable...
        eng.step(cfg, None, now=now)
        cfg["features"]["wallpaper"] = False         # ...and disable again
        eng.step(cfg, None, now=now)
        check("restores again after re-enable then disable", counts["restore"] == 2)

        # One-shot tick(): feature off + a weather wallpaper still showing.
        counts["restore"] = 0
        cfg2 = config.default_config()
        cfg2["features"]["wallpaper"] = False
        cfg2["features"]["ambient_sound"] = False
        engine.tick(cfg2, None, now=now)
        check("tick restores when off + showing ours", counts["restore"] == 1)
    finally:
        (theme.apply_theme_color, wallpaper.apply_weather_wallpaper,
         wallpaper.restore_original, wallpaper.is_showing_ours,
         sound.play_ambient, sound.stop_sound, sound.set_volume,
         sound.pick_base, weather.get_weather) = saved


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

    # City picker mapping.
    out3 = gui.apply_values_to_config(config.default_config(),
                                      {**base_vals, "city": "Tokyo, Japan"})
    check("city sets location name", out3["location"]["name"] == "Tokyo")
    check("city sets latitude", abs(out3["location"]["lat"] - 35.6762) < 0.001)
    check("no location_precision key", "location_precision" not in out3)
    cfg_keep = config.default_config()
    cfg_keep["location"] = {"lat": 1.0, "lon": 2.0, "name": "Nowhere"}
    out4 = gui.apply_values_to_config(cfg_keep, {**base_vals, "city": "Atlantis"})
    check("unknown city keeps existing location", out4["location"]["name"] == "Nowhere")


def test_cities():
    section("city picker")
    check("choices are the city list", config.city_choices() == list(config.CITIES.keys()))
    check("many cities listed", len(config.CITIES) >= 20)
    check("every city has coords+name",
          all({"lat", "lon", "name"} <= set(c) for c in config.CITIES.values()))
    check("lat/lon in range",
          all(-90 <= c["lat"] <= 90 and -180 <= c["lon"] <= 180
              for c in config.CITIES.values()))
    check("lookup returns a copy",
          config.location_for_city("Tokyo, Japan") is not config.CITIES["Tokyo, Japan"])
    check("unknown lookup => None", config.location_for_city("Atlantis") is None)
    # label_for resolves by name...
    check("label by name",
          config.city_label_for({"location": {"name": "London"}}) == "London, UK")
    # ...and by coordinates alone.
    check("label by coords",
          config.city_label_for({"location": {"lat": 48.8566, "lon": 2.3522}})
          == "Paris, France")
    check("default config resolves to its city",
          config.city_label_for(config.DEFAULTS) == "Sydney, Australia")
    # Unknown location falls back to the first listed city (never a raw sentinel).
    check("unmatched coords => first city",
          config.city_label_for({"location": {"lat": 0.0, "lon": 0.0}})
          == next(iter(config.CITIES)))


def test_clocks():
    section("stopwatch + countdown timer")
    import clocks
    check("format mm:ss", clocks.format_time(75) == "01:15")
    check("format h:mm:ss", clocks.format_time(3661) == "1:01:01")

    # Stopwatch counts up only while running.
    sw = clocks.Stopwatch()
    for _ in range(5):
        sw.tick(1)
    check("paused stopwatch stays at 0", sw.elapsed == 0)
    sw.toggle()
    for _ in range(5):
        sw.tick(1)
    check("running stopwatch counts up", sw.elapsed == 5)
    sw.lap()
    check("lap recorded", sw.laps == [5])
    sw.reset()
    check("reset clears stopwatch", sw.elapsed == 0 and sw.laps == [] and not sw.running)

    # Countdown counts down and fires once at zero.
    ct = clocks.CountdownTimer(minutes=1)      # 60 s
    check("starts at duration", ct.remaining == 60 and not ct.running)
    ct.toggle()
    events = [ct.tick(1) for _ in range(60)]
    check("fires 'done' exactly once", events.count("done") == 1)
    check("finished at zero", ct.finished and ct.remaining == 0 and not ct.running)
    ct.toggle()                                # restart a finished timer
    check("restart refills", ct.remaining == 60 and ct.running)
    ct.reset()
    check("reset stops and refills", ct.remaining == 60 and not ct.running)
    ct.set_minutes(5)
    check("set_minutes changes duration", ct.remaining == 300)
    # A paused countdown doesn't advance.
    ct2 = clocks.CountdownTimer(2)
    for _ in range(10):
        ct2.tick(1)
    check("paused countdown holds", ct2.remaining == 120)


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


# ---------------------------------------------------------
# activity (idle detection)
# ---------------------------------------------------------
def test_activity():
    section("activity — idle detection")
    import sys as _sys
    import subprocess as _sp
    import activity

    # The public entry always returns a float, whatever the platform.
    idle = activity.get_idle_time()
    check("get_idle_time returns a float", isinstance(idle, float))
    check("idle time non-negative", idle >= 0.0)

    # Unsupported platform degrades to 0.0 (never crashes / never None).
    o_plat = _sys.platform
    _sys.platform = "linux"
    try:
        check("unsupported platform => 0.0", activity.get_idle_time() == 0.0)
    finally:
        _sys.platform = o_plat

    # Dispatch: each platform routes to its own implementation.
    o_win, o_mac = activity._get_idle_windows, activity._get_idle_macos
    activity._get_idle_windows = lambda: 11.0
    activity._get_idle_macos = lambda: 22.0
    try:
        _sys.platform = "win32"
        check("win32 routes to windows impl", activity.get_idle_time() == 11.0)
        _sys.platform = "darwin"
        check("darwin routes to macos impl", activity.get_idle_time() == 22.0)
    finally:
        activity._get_idle_windows, activity._get_idle_macos = o_win, o_mac
        _sys.platform = o_plat

    # macOS impl parses ioreg's HIDIdleTime (nanoseconds -> seconds).
    o_run = _sp.run
    try:
        class _R:
            stdout = ('  |   "HIDIdleTime" = 4500000000\n'
                      '  |   "HIDIdleCount" = 3\n')
        _sp.run = lambda *a, **k: _R()
        check("macos parses HIDIdleTime seconds",
              abs(activity._get_idle_macos() - 4.5) < 1e-9)

        class _R2:
            stdout = "no idle field here\n"
        _sp.run = lambda *a, **k: _R2()
        check("macos missing field => 0.0", activity._get_idle_macos() == 0.0)

        def _boom(*a, **k):
            raise OSError("ioreg unavailable")
        _sp.run = _boom
        check("macos subprocess error => 0.0", activity._get_idle_macos() == 0.0)
    finally:
        _sp.run = o_run

    # Windows impl swallows errors (ctypes.windll is absent off-Windows).
    if _sys.platform != "win32":
        check("windows impl error-safe off Windows",
              activity._get_idle_windows() == 0.0)


# ---------------------------------------------------------
# audiocheck (other-audio detection)
# ---------------------------------------------------------
def test_audiocheck():
    section("audiocheck — external audio detection")
    import sys as _sys
    import subprocess as _sp
    import audiocheck

    o_plat = _sys.platform

    # Unknown platform can't tell -> None (tri-state, not False).
    _sys.platform = "linux"
    try:
        check("unknown platform => None", audiocheck.external_audio_active() is None)
    finally:
        _sys.platform = o_plat

    # Dispatch to the per-platform probe.
    o_mac, o_win = audiocheck._macos_playing, audiocheck._windows_playing
    audiocheck._macos_playing = lambda: True
    audiocheck._windows_playing = lambda: False
    try:
        _sys.platform = "darwin"
        check("darwin routes to macos probe", audiocheck.external_audio_active() is True)
        _sys.platform = "win32"
        check("win32 routes to windows probe", audiocheck.external_audio_active() is False)
        # A probe blowing up is caught and reported as unknown (None).
        def _boom():
            raise RuntimeError("probe failed")
        audiocheck._macos_playing = _boom
        _sys.platform = "darwin"
        check("probe error => None", audiocheck.external_audio_active() is None)
    finally:
        audiocheck._macos_playing, audiocheck._windows_playing = o_mac, o_win
        _sys.platform = o_plat

    # macOS probe: not-running app => not playing; running + "playing" => True.
    o_run = _sp.run
    try:
        class _R:
            def __init__(self, out):
                self.stdout = out
        _sp.run = lambda *a, **k: _R("false")
        check("no media app running => False", audiocheck._macos_playing() is False)

        state = {"n": 0}

        def _seq(*a, **k):
            # First call: "is it running?"; second: "player state".
            state["n"] += 1
            return _R("true") if state["n"] % 2 == 1 else _R("playing")
        _sp.run = _seq
        check("running + playing => True", audiocheck._macos_playing() is True)
    finally:
        _sp.run = o_run

    # Windows probe returns None when pycaw isn't installed (import fails).
    if _sys.platform != "win32":
        check("windows probe => None without pycaw",
              audiocheck._windows_playing() is None)


# ---------------------------------------------------------
# engine.notify (desktop notification, no OS mutation)
# ---------------------------------------------------------
def test_notify():
    section("notify — cross-platform, error-safe")
    import sys as _sys
    import subprocess as _sp

    o_plat = _sys.platform
    o_run = _sp.run
    seen = {}

    def _capture(cmd, *a, **k):
        seen["cmd"] = cmd
        class _R:
            stdout = ""
            returncode = 0
        return _R()

    try:
        _sp.run = _capture
        _sys.platform = "darwin"
        engine.notify("Flow", "Stand up")
        check("macOS uses osascript", seen["cmd"][0] == "osascript")
        check("macOS command carries the message",
              any("Stand up" in str(part) for part in seen["cmd"]))

        _sys.platform = "win32"
        engine.notify("Flow", "Break time")
        check("Windows uses powershell", seen["cmd"][0] == "powershell")

        # Unsupported platform just logs (no subprocess call) and never raises.
        seen.clear()
        _sys.platform = "linux"
        engine.notify("Flow", "hello")
        check("unsupported platform makes no subprocess call", "cmd" not in seen)

        # A failing subprocess is swallowed, not propagated.
        def _boom(*a, **k):
            raise OSError("no osascript")
        _sp.run = _boom
        _sys.platform = "darwin"
        engine.notify("Flow", "test")   # must not raise
        check("notify swallows subprocess errors", True)
    finally:
        _sp.run = o_run
        _sys.platform = o_plat


# ---------------------------------------------------------
# gui display helpers (pure formatting — no window)
# ---------------------------------------------------------
def test_gui_display_helpers():
    section("gui display helpers")
    import gui

    # Hex + luminance.
    check("hex formats rgb", gui._hex((40, 80, 180)) == "#2850b4")
    check("hex clamps out-of-range", gui._hex((-5, 300, 128)) == "#00ff80")
    check("luminance white ~1", abs(gui._lum((255, 255, 255)) - 1.0) < 1e-9)
    check("luminance black 0", gui._lum((0, 0, 0)) == 0.0)
    check("green brighter than blue (luma)", gui._lum((0, 255, 0)) > gui._lum((0, 0, 255)))

    # Palette: a very dark accent is lifted so it stays a usable button colour,
    # and the foreground flips for contrast.
    pal = gui.build_palette(True, (5, 5, 5))
    check("palette has accent + fg", "ACCENT" in pal and "ACCENT_FG" in pal)
    check("dark accent lifted (not near-black)", pal["ACCENT"] != gui._hex((5, 5, 5)))
    light = gui.build_palette(False, (250, 250, 120))
    check("bright accent => dark foreground", light["ACCENT_FG"] == "#0d1117")

    # Weather icon selection (day/night aware).
    check("storm icon", gui._weather_icon("storm", False) == "⛈️")
    check("rain icon", gui._weather_icon("rain", True) == "🌧️")
    check("cloud icon", gui._weather_icon("cloud", False) == "⛅")
    check("cloudnight still a cloud icon", gui._weather_icon("cloudnight", True) == "⛅")
    check("clear day => sun", gui._weather_icon("clear", False) == "☀️")
    check("clear night => moon", gui._weather_icon("clear", True) == "🌙")
    check("night => moon", gui._weather_icon("night", True) == "🌙")
    check("unknown => fallback", gui._weather_icon("fog", False) == "🌡️")

    # Temperature formatting.
    check("temp rounds to whole degrees", gui._fmt_temp(20.4) == "20°C")
    check("temp None => dash", gui._fmt_temp(None) == "—")
    check("temp non-numeric => dash", gui._fmt_temp("hot") == "—")

    # UV label with risk band.
    check("uv low", gui._uv_label(1) == "UV 1 (low)")
    check("uv moderate", gui._uv_label(5) == "UV 5 (moderate)")
    check("uv high", gui._uv_label(7) == "UV 7 (high)")
    check("uv very high", gui._uv_label(9) == "UV 9 (very high)")
    check("uv extreme", gui._uv_label(12) == "UV 12 (extreme)")
    check("uv None => None", gui._uv_label(None) is None)
    check("uv bad => None", gui._uv_label("x") is None)

    # Live-data detail line.
    line = gui._fmt_details({
        "feels_like": 18.6, "humidity": 55, "uv_index": 4,
        "wind_speed": 12, "wind_gust": 20, "precip_chance": 10, "pressure": 1013,
    })
    for want in ["Feels 19°", "Humidity 55%", "UV 4", "Wind 12 km/h",
                 "gust 20", "Rain 10%", "1013 hPa"]:
        check(f"details contains {want!r}", want in line)
    check("empty details => placeholder",
          gui._fmt_details({}) == "live data unavailable")
    check("uv_index_max used when uv_index missing",
          "UV 6" in gui._fmt_details({"uv_index_max": 6}))


# ---------------------------------------------------------
# engine pure helpers
# ---------------------------------------------------------
def test_engine_helpers():
    section("engine pure helpers")
    import datetime as dt

    # Colour delta is the max per-channel difference.
    check("color delta max channel", engine._color_delta((10, 20, 30), (10, 25, 90)) == 60)
    check("color delta zero when equal", engine._color_delta((1, 2, 3), (1, 2, 3)) == 0)

    # _style_color: none profile + no accessibility is an int-tuple identity.
    base = config.default_config()
    base["active_profile"] = "none"
    base["accessibility_mode"] = "none"
    styled = engine._style_color((60, 120, 200), base)
    check("style none => unchanged", styled == (60, 120, 200))
    check("style returns int tuple", all(isinstance(c, int) for c in styled))

    # High-contrast accessibility bends the colour to a bold one.
    hc = config.default_config()
    hc["active_profile"] = "none"
    hc["accessibility_mode"] = "high_contrast"
    check("style high-contrast intensifies",
          _chroma(engine._style_color((90, 120, 170), hc)) > _chroma((90, 120, 170)))

    # _season_now: off => None; on (south, July) => winter.
    off = config.default_config()
    off["seasonal_themes"] = False
    check("season off => None", engine._season_now(off, dt.datetime(2026, 7, 15, 12)) is None)
    on = config.default_config()
    on["seasonal_themes"] = True
    on["hemisphere"] = "south"
    check("season on (south July) => winter",
          engine._season_now(on, dt.datetime(2026, 7, 15, 12)) == "winter")
    on["hemisphere"] = "north"
    check("season on (north July) => summer",
          engine._season_now(on, dt.datetime(2026, 7, 15, 12)) == "summer")


def main():
    test_config()
    test_weather()
    test_theme()
    test_day_phase()
    test_profiles()
    test_seasons()
    test_transitions()
    test_high_contrast()
    test_wallpaper()
    test_wallpaper_patterns()
    test_sound()
    test_sound_variants_and_modes()
    test_music()
    test_duck_other_audio()
    test_audio_priority()
    test_tasks()
    test_autostart()
    test_bugfixes()
    test_city_change_refetch()
    test_task_recolors_now()
    test_sun_tracking()
    test_wallpaper_no_revert()
    test_wallpaper_force_refresh()
    test_wallpaper_agent_warmup()
    test_wallpaper_restore_on_disable()
    test_engine()
    test_pomodoro()
    test_clocks()
    test_drift()
    test_engine_guards()
    test_gui_helper()
    test_cities()
    test_activity()
    test_audiocheck()
    test_notify()
    test_gui_display_helpers()
    test_engine_helpers()
    print(f"\n{'='*40}\nRESULT: {_passed} passed, {_failed} failed")
    return 1 if _failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
