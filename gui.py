"""
Settings GUI for the Flow.

Layout:
  * Main window
      - Dashboard   — live weather + temperature, feature toggles, and the
                      manual theme changer (weather / time / colour), together.
      - Settings    — wallpaper look, sound, engine cadence, run-at-login.
  * Separate "Focus & Tasks" window (opened from the header)
      - Pomodoro timer
      - To-do & schedules

The window only drives state; all behaviour lives in the engine + modules,
so the heavy logic stays testable without a display.
"""

import os
import queue
import threading
import datetime

import tkinter as tk
from tkinter import ttk, messagebox, colorchooser, filedialog, font as tkfont

import config
import weather
import theme
import tasks as tasks_mod
import autostart
import engine
import sound
import music
import pomodoro
import clocks


# ---------------------------------------------------------
# Pure helper (testable without a display)
# ---------------------------------------------------------

def apply_values_to_config(cfg: dict, values: dict) -> dict:
    """
    Merge a flat dict of widget values into *cfg* and return it.
    Kept free of tkinter so it can be unit-tested directly.
    """
    cfg["enabled"] = bool(values["enabled"])
    cfg["features"] = {
        "dynamic_theme": bool(values["dynamic_theme"]),
        "wallpaper":     bool(values["wallpaper"]),
        "ambient_sound": bool(values["ambient_sound"]),
        "tasks":         bool(values["tasks"]),
    }
    cfg["weather_tint_strength"] = int(round(values["tint"]))
    cfg["sound_volume"] = int(round(values["volume"]))
    cfg["music_volume"] = max(0, min(100, int(values.get("music_volume", 60))))
    cfg["pause_when_other_audio"] = bool(values.get("pause_when_other_audio", False))
    cfg["tick_interval_seconds"] = max(5, int(values["tick_interval"]))
    cfg["weather_refresh_seconds"] = max(30, int(values["weather_refresh"]))
    cfg["wallpaper_dynamic"] = bool(values["wallpaper_dynamic"])
    cfg["wallpaper_shift_strength"] = int(round(values["wallpaper_shift"]))
    cfg["wallpaper_patterns"] = bool(values.get("wallpaper_patterns", True))
    cfg["wallpaper_warmth"] = bool(values.get("wallpaper_warmth", True))
    cfg["countdown_minutes"] = max(1, int(values.get("countdown_minutes", 10)))
    cfg["pomodoro"] = {
        "work_min": max(1, int(values["p_work"])),
        "break_min": max(1, int(values["p_break"])),
        "long_break_min": max(1, int(values["p_long"])),
        "cycles_before_long": max(1, int(values["p_cycles"])),
    }
    manual_weather = str(values["manual_weather"]).lower()
    cfg["manual_weather"] = (
        manual_weather if manual_weather in config.WEATHER_CHOICES else "auto")
    cfg["manual_time"] = values["manual_time"]

    color = (values.get("manual_theme_color") or "").strip()
    if not color or color.lower() == "auto":
        cfg["manual_theme_color"] = None
    else:
        try:
            rgb = [max(0, min(255, int(x))) for x in color.split(",")]
            cfg["manual_theme_color"] = rgb if len(rgb) == 3 else None
        except ValueError:
            cfg["manual_theme_color"] = None
    cfg["run_at_login"] = bool(values["run_at_login"])

    prof = str(values.get("active_profile", "none")).lower()
    cfg["active_profile"] = prof if prof in config.PROFILE_CHOICES else "none"
    acc = str(values.get("accessibility_mode", "none")).lower()
    cfg["accessibility_mode"] = acc if acc in config.ACCESSIBILITY_CHOICES else "none"
    appr = str(values.get("appearance_mode", "auto")).lower()
    cfg["appearance_mode"] = appr if appr in config.APPEARANCE_CHOICES else "auto"
    hemi = str(values.get("hemisphere", "auto")).lower()
    cfg["hemisphere"] = hemi if hemi in config.HEMISPHERE_CHOICES else "auto"
    cfg["seasonal_themes"] = bool(values.get("seasonal_themes", True))
    cfg["multi_monitor"] = bool(values.get("multi_monitor", True))
    cfg["smooth_transitions"] = bool(values.get("smooth_transitions", True))
    # City picker sets the location; an unknown label leaves it unchanged.
    city_loc = config.location_for_city(values.get("city", ""))
    if city_loc is not None:
        cfg["location"] = city_loc
    return cfg


# ---------------------------------------------------------
# Look & feel
# ---------------------------------------------------------

# The window follows the time of day, like the wallpaper/theme: a light palette
# by day, a dark one at night, with an accent tinted from the current
# weather/phase colour. Two base palettes; the accent is filled in per-phase.
#   BTN/BTN2 = the "ghost" button surface (distinct from cards so buttons read
#   as buttons) and its hover shade; LINE also outlines them.
LIGHT = {"BG": "#eef1f7", "CARD": "#ffffff", "INK": "#1f2937",
         "MUTED": "#6b7280", "FIELD": "#ffffff", "LINE": "#d3d9e4",
         "BTN": "#e7ebf3", "BTN2": "#d9e0ee"}
DARK  = {"BG": "#151a24", "CARD": "#1f2632", "INK": "#e8ebf1",
         "MUTED": "#8b97a9", "FIELD": "#2a323f", "LINE": "#3a4453",
         "BTN": "#333d4c", "BTN2": "#3f4a5b"}
# Accessibility: black background, white text, yellow accent — maximum contrast.
HIGH_CONTRAST = {"BG": "#000000", "CARD": "#000000", "INK": "#ffffff",
                 "MUTED": "#ffd400", "FIELD": "#000000", "LINE": "#ffe000",
                 "BTN": "#111111", "BTN2": "#222222",
                 "ACCENT": "#ffe000", "ACCENT_FG": "#000000"}


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(c))) for c in rgb)


def _lum(rgb):
    return (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) / 255.0


def build_palette(dark, accent_rgb):
    """A full palette for the given mode + accent colour."""
    pal = dict(DARK if dark else LIGHT)
    # Keep the accent readable as a button colour; lift very dark accents.
    if _lum(accent_rgb) < 0.28:
        accent_rgb = tuple(min(255, int(c + (150 - c) * 0.5)) for c in accent_rgb)
    pal["ACCENT"] = _hex(accent_rgb)
    pal["ACCENT_FG"] = "#0d1117" if _lum(accent_rgb) > 0.6 else "#ffffff"
    return pal


# Emoji per weather condition (day/night aware for clear skies).
_WEATHER_ICON = {
    "clear": "☀️", "clear_night": "🌙", "night": "🌙",
    "cloud": "⛅", "rain": "🌧️", "storm": "⛈️", "fallback": "🌡️",
}


def _weather_icon(condition, is_night):
    c = (condition or "").lower()
    if "storm" in c:
        return _WEATHER_ICON["storm"]
    if "rain" in c:
        return _WEATHER_ICON["rain"]
    if "cloud" in c:
        return _WEATHER_ICON["cloud"]
    if "night" in c or (("clear" in c) and is_night):
        return _WEATHER_ICON["night"]
    if "clear" in c:
        return _WEATHER_ICON["clear"]
    return _WEATHER_ICON["fallback"]


def _fmt_temp(t):
    try:
        return f"{float(t):.0f}°C"
    except (TypeError, ValueError):
        return "—"


# Friendly names for task actions (the stored value stays the internal key).
ACTION_TO_LABEL = {
    "notify": "Notify me",
    "chime": "Play a chime",
}
LABEL_TO_ACTION = {v: k for k, v in ACTION_TO_LABEL.items()}


def _task_when_str(t):
    if t.get("type") == "daily":
        return f"Every day · {t.get('time', '')}"
    dts = t.get("datetime") or ""
    try:
        return datetime.datetime.fromisoformat(dts).strftime("%a %d %b · %H:%M")
    except (ValueError, TypeError):
        return dts


def _task_does_str(t):
    a = t.get("action", "")
    return {"notify": "Notify me", "chime": "Play a chime"}.get(a, a)


def _uv_label(uv):
    """UV index with a risk word."""
    try:
        uv = float(uv)
    except (TypeError, ValueError):
        return None
    band = ("low" if uv < 3 else "moderate" if uv < 6 else "high"
            if uv < 8 else "very high" if uv < 11 else "extreme")
    return f"UV {uv:.0f} ({band})"


def _fmt_details(d):
    """A compact 'live data' line: feels-like, humidity, UV, wind, pressure."""
    bits = []
    if d.get("feels_like") is not None:
        bits.append(f"Feels {float(d['feels_like']):.0f}°")
    if d.get("humidity") is not None:
        bits.append(f"Humidity {float(d['humidity']):.0f}%")
    uv = _uv_label(d.get("uv_index") if d.get("uv_index") is not None
                   else d.get("uv_index_max"))
    if uv:
        bits.append(uv)
    if d.get("wind_speed") is not None:
        w = f"Wind {float(d['wind_speed']):.0f} km/h"
        if d.get("wind_gust"):
            w += f" (gust {float(d['wind_gust']):.0f})"
        bits.append(w)
    if d.get("precip_chance") is not None:
        bits.append(f"Rain {float(d['precip_chance']):.0f}%")
    if d.get("pressure") is not None:
        bits.append(f"{float(d['pressure']):.0f} hPa")
    return "   ·   ".join(bits) if bits else "live data unavailable"


def _weather_summary(condition, phase, manual=False):
    """Compact dashboard label: weather first, then time of day."""
    weather_text = (condition or "unknown").capitalize()
    phase_text = (phase or "unknown").lower()
    suffix = "  ·  manual" if manual else ""
    return f"{weather_text}  ·  {phase_text}{suffix}"


def _shift_iso_date(value, days, today=None):
    """Shift an ISO date, falling back to today when the field is invalid."""
    today = today or datetime.date.today()
    try:
        base = datetime.date.fromisoformat(value)
    except (TypeError, ValueError):
        base = today
    return (base + datetime.timedelta(days=days)).isoformat()


def _sync_feature_vars(enabled, variables):
    """Set each per-feature BooleanVar to the master switch state."""
    for variable in variables:
        variable.set(bool(enabled))


def _largest_fitting_font(text, available_width, measure, sizes=range(40, 19, -2)):
    """Largest font size whose measured text fits the available width."""
    for size in sizes:
        if measure(text, size) <= available_width:
            return size
    return min(sizes)


def _card(parent, title=None):
    """A white padded panel; returns the inner content frame."""
    outer = ttk.Frame(parent, style="Card.TFrame", padding=1)
    outer.pack(fill="x", pady=7)
    inner = ttk.Frame(outer, style="Card.TFrame", padding=14)
    inner.pack(fill="both", expand=True)
    if title:
        ttk.Label(inner, text=title, style="CardH.TLabel").pack(anchor="w", pady=(0, 8))
    return inner


def _responsive_label(parent, *, padding=0, **kwargs):
    """Label whose wrap width tracks its container instead of clipping."""
    label = ttk.Label(parent, wraplength=360, **kwargs)

    def resize(event):
        try:
            label.configure(wraplength=max(120, event.width - padding))
        except tk.TclError:
            pass

    parent.bind("<Configure>", resize, add="+")
    return label


# ---------------------------------------------------------
# Application window
# ---------------------------------------------------------

class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.cfg = config.load_config()
        self.store = tasks_mod.TaskStore()
        self.engine_thread = None
        self.status_queue = queue.Queue()

        # Handles that only exist while the Focus & Tasks window is open.
        self.tools_win = None
        self.tree = None
        self.btn_timer = None
        self.lbl_cycles = None
        self.music_list = None
        self.btn_music_play = None
        self.timer_label = None
        self.feature_checks = []

        root.title("Flow")
        root.geometry("600x780")
        root.minsize(560, 700)
        self.status_lbl = None
        self._ui_key = None          # (dark, accent) currently applied
        self._apply_busy = False     # a preview tick is in flight
        self._auto_apply_job = None  # coalesce rapid slider/spinbox changes
        self._scroll_canvases = []   # tk.Canvas backing the scrollable tabs
        self._scroll_items = {}      # canvas -> embedded content item
        self._effective_swatch = None
        self._install_styles()

        self._build_vars()
        self._persist_master_consistency()
        self._build_ui()
        self._bind_auto_apply()
        self._start_engine()
        self._poll_status_queue()
        self._timer_loop()
        self.refresh_weather()      # populate the weather card at launch

    # --- tk variables --------------------------------------------------
    def _build_vars(self):
        c = self.cfg
        f = c.get("features", {})
        self.v_enabled = tk.BooleanVar(value=c.get("enabled", True))
        self.v_theme = tk.BooleanVar(value=f.get("dynamic_theme", True))
        self.v_wallpaper = tk.BooleanVar(value=f.get("wallpaper", True))
        self.v_sound = tk.BooleanVar(value=f.get("ambient_sound", True))
        self.v_tasks = tk.BooleanVar(value=f.get("tasks", True))
        if not self.v_enabled.get():
            _sync_feature_vars(
                False, (self.v_theme, self.v_wallpaper, self.v_sound, self.v_tasks))
        self.v_tint = tk.DoubleVar(value=float(c.get("weather_tint_strength", 40)))
        self.v_volume = tk.DoubleVar(value=float(c.get("sound_volume", 25)))
        self._vol_save_job = None            # debounced save for the volume slider
        self.v_volume.trace_add("write", self._on_ambient_volume)
        self.v_musicvol = tk.IntVar(value=int(c.get("music_volume", 60)))
        self.v_musicvol.trace_add("write", self._on_music_volume)
        self.v_duck = tk.BooleanVar(value=c.get("pause_when_other_audio", False))
        self.music_now = tk.StringVar(value="Nothing playing")
        self.v_tick = tk.IntVar(value=int(c.get("tick_interval_seconds", 30)))
        self.v_weatherrefresh = tk.IntVar(value=int(c.get("weather_refresh_seconds", 600)))
        self.v_wpdynamic = tk.BooleanVar(value=c.get("wallpaper_dynamic", True))
        self.v_wpshift = tk.DoubleVar(value=float(c.get("wallpaper_shift_strength", 35)))
        self.v_wppatterns = tk.BooleanVar(value=c.get("wallpaper_patterns", True))
        self.v_wpwarmth = tk.BooleanVar(value=c.get("wallpaper_warmth", True))
        self.v_profile = tk.StringVar(value=c.get("active_profile", "none"))
        self.v_access = tk.StringVar(value=c.get("accessibility_mode", "none"))
        self.v_appearance = tk.StringVar(value=c.get("appearance_mode", "auto"))
        self.v_season = tk.BooleanVar(value=c.get("seasonal_themes", True))
        self.v_hemisphere = tk.StringVar(value=c.get("hemisphere", "auto"))
        self.v_multimon = tk.BooleanVar(value=c.get("multi_monitor", True))
        self.v_city = tk.StringVar(value=config.city_label_for(c))
        self.v_smooth = tk.BooleanVar(value=c.get("smooth_transitions", True))
        self.v_weather = tk.StringVar(value=c.get("manual_weather", "auto"))
        self.v_time = tk.StringVar(value=c.get("manual_time", "auto"))
        mc = c.get("manual_theme_color")
        self.v_color = tk.StringVar(value=("auto" if not mc else ",".join(map(str, mc))))
        self.v_runlogin = tk.BooleanVar(value=autostart.is_autostart_enabled())
        self.v_status = tk.StringVar(value="Starting…")

        # Live weather card text.
        self.v_wicon = tk.StringVar(value="🌡️")
        self.v_wtemp = tk.StringVar(value="—")
        self.v_wcond = tk.StringVar(value="Fetching weather…")
        self.v_wsub = tk.StringVar(value=c.get("location", {}).get("name", ""))
        self.v_wdetails = tk.StringVar(value="")

        # Pomodoro durations + live timer state.
        p = c.get("pomodoro", {})
        self.v_pwork = tk.IntVar(value=int(p.get("work_min", 25)))
        self.v_pbreak = tk.IntVar(value=int(p.get("break_min", 5)))
        self.v_plong = tk.IntVar(value=int(p.get("long_break_min", 15)))
        self.v_pcycles = tk.IntVar(value=int(p.get("cycles_before_long", 4)))
        self.v_timer = tk.StringVar(value="Idle")       # shared big display
        self.pomo = pomodoro.Pomodoro(
            self.v_pwork.get(), self.v_pbreak.get(),
            self.v_plong.get(), self.v_pcycles.get())
        # Stopwatch + countdown timer, alongside the Pomodoro.
        self.v_clockmode = tk.StringVar(value="pomodoro")   # pomodoro|timer|stopwatch
        self.v_timermin = tk.IntVar(value=int(c.get("countdown_minutes", 10)))
        self.stopwatch = clocks.Stopwatch()
        self.timer = clocks.CountdownTimer(self.v_timermin.get())
        self.clock_settings = None      # per-mode settings frame (rebuilt on switch)
        self.btn_clock_extra = None     # Skip / Lap context button
        self.lap_box = None             # stopwatch laps list (when shown)

    # --- styling / time-of-day UI theme --------------------------------
    def _persist_master_consistency(self):
        """Repair legacy configs whose child features stayed on under master off."""
        if self.v_enabled.get():
            return
        if any(self.cfg.get("features", {}).values()):
            self._collect()
            config.save_config(self.cfg)

    def _install_styles(self):
        self.style = ttk.Style()
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        self.pal = build_palette(False, (59, 130, 246))   # light + blue to start
        try:
            self._configure_styles()
        except tk.TclError as e:
            print(f"[gui] style setup skipped: {e}")

    def _configure_styles(self):
        p, s = self.pal, self.style
        # Flatten clam's 3-D bevels — the light top/left edges that read as
        # clunky white outlines in dark mode. Match bevel colours to the
        # surface so nothing stands proud.
        s.configure(".", background=p["BG"], foreground=p["INK"],
                    font=("Helvetica", 11), bordercolor=p["LINE"],
                    lightcolor=p["BG"], darkcolor=p["BG"], troughcolor=p["FIELD"])
        s.configure("TFrame", background=p["BG"])
        s.configure("Card.TFrame", background=p["CARD"])
        s.configure("Bar.TLabel", background=p["BG"], foreground=p["MUTED"],
                    font=("Helvetica", 10))
        s.configure("TLabel", background=p["BG"], foreground=p["INK"])
        s.configure("Card.TLabel", background=p["CARD"], foreground=p["INK"])
        s.configure("Muted.TLabel", background=p["CARD"], foreground=p["MUTED"],
                    font=("Helvetica", 10))
        s.configure("H1.TLabel", background=p["BG"], foreground=p["INK"],
                    font=("Helvetica", 17, "bold"))
        s.configure("CardH.TLabel", background=p["CARD"], foreground=p["INK"],
                    font=("Helvetica", 12, "bold"))
        s.configure("Temp.TLabel", background=p["CARD"], foreground=p["INK"],
                    font=("Helvetica", 40, "bold"))
        s.configure("Icon.TLabel", background=p["CARD"], foreground=p["INK"],
                    font=("Helvetica", 40))
        s.configure("Cond.TLabel", background=p["CARD"], foreground=p["INK"],
                    font=("Helvetica", 15, "bold"))
        s.configure("Timer.TLabel", background=p["CARD"], foreground=p["INK"],
                    font=("Helvetica", 40, "bold"))
        for st in ("Card.TCheckbutton", "Card.TRadiobutton"):
            s.configure(st, background=p["CARD"], foreground=p["INK"])
            s.map(st, background=[("active", p["CARD"])], foreground=[("active", p["INK"])])
        s.configure("TNotebook", background=p["BG"], borderwidth=0, bordercolor=p["BG"])
        s.configure("TNotebook.Tab", padding=(16, 8), font=("Helvetica", 11),
                    borderwidth=0, background=p["BG"], foreground=p["MUTED"])
        s.map("TNotebook.Tab", background=[("selected", p["CARD"])],
              foreground=[("selected", p["INK"])])
        s.configure("TScrollbar", background=p["FIELD"], troughcolor=p["BG"],
                    bordercolor=p["BG"], arrowcolor=p["MUTED"])
        # Text fields. Read-only comboboxes ignore plain `configure`, so the
        # readonly/focus/disabled states must be mapped explicitly or the text
        # is unreadable (dark on dark) in night mode. Flat border = FIELD colour.
        try:
            s.configure("TEntry", fieldbackground=p["FIELD"], foreground=p["INK"],
                        insertcolor=p["INK"], bordercolor=p["LINE"],
                        lightcolor=p["FIELD"], darkcolor=p["FIELD"])
            for st in ("TCombobox", "TSpinbox"):
                s.configure(st, fieldbackground=p["FIELD"], foreground=p["INK"],
                            background=p["FIELD"], arrowcolor=p["INK"],
                            bordercolor=p["LINE"], lightcolor=p["FIELD"], darkcolor=p["FIELD"])
                s.map(st,
                      fieldbackground=[("readonly", p["FIELD"]), ("disabled", p["FIELD"]),
                                       ("focus", p["FIELD"])],
                      foreground=[("readonly", p["INK"]), ("disabled", p["MUTED"]),
                                  ("focus", p["INK"])],
                      selectbackground=[("readonly", p["FIELD"]), ("focus", p["FIELD"])],
                      selectforeground=[("readonly", p["INK"]), ("focus", p["INK"])],
                      background=[("readonly", p["FIELD"]), ("active", p["FIELD"])],
                      arrowcolor=[("disabled", p["MUTED"])])
            # Drop-down list (a tk Listbox under the hood) — via the option DB.
            self.root.option_add("*TCombobox*Listbox.background", p["CARD"])
            self.root.option_add("*TCombobox*Listbox.foreground", p["INK"])
            self.root.option_add("*TCombobox*Listbox.selectBackground", p["ACCENT"])
            self.root.option_add("*TCombobox*Listbox.selectForeground", p["ACCENT_FG"])
        except tk.TclError as e:
            print(f"[gui] field styling skipped: {e}")
        s.configure("Treeview", background=p["CARD"], fieldbackground=p["CARD"],
                    foreground=p["INK"])
        s.configure("Accent.TButton", background=p["ACCENT"], foreground=p["ACCENT_FG"],
                    borderwidth=0, relief="flat", focusthickness=0, padding=(14, 7),
                    font=("Helvetica", 11, "bold"))
        s.map("Accent.TButton",
              background=[("active", p["ACCENT"]), ("pressed", p["ACCENT"])],
              relief=[("pressed", "flat"), ("active", "flat")])
        # Ghost buttons: a subtle filled chip with a hairline border, so they're
        # clearly buttons (not blended into the card) but stay understated.
        s.configure("Ghost.TButton", padding=(12, 6), relief="solid", borderwidth=1,
                    background=p["BTN"], foreground=p["INK"], bordercolor=p["LINE"],
                    lightcolor=p["BTN"], darkcolor=p["BTN"], focusthickness=0)
        s.map("Ghost.TButton",
              background=[("active", p["BTN2"]), ("pressed", p["BTN2"]),
                          ("disabled", p["CARD"])],
              foreground=[("active", p["INK"]), ("disabled", p["MUTED"])],
              bordercolor=[("active", p["ACCENT"])],
              relief=[("pressed", "solid"), ("active", "solid")])
        # Raw (non-ttk) surfaces.
        try:
            self.root.configure(bg=p["BG"])
        except tk.TclError:
            pass
        if self._alive(getattr(self, "tools_win", None)):
            self.tools_win.configure(bg=p["BG"])
        for c in self._scroll_canvases:
            if self._alive(c):
                c.configure(bg=p["BG"])

    def _make_scroll(self, parent):
        """
        A vertically scrollable content frame. Lag-free: the inner width is
        only re-applied when it actually changes (so re-showing a tab doesn't
        trigger a full relayout), and the wheel binds only while hovering.
        """
        canvas = tk.Canvas(parent, bg=self.pal["BG"], highlightthickness=0)
        vsb = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        iid = canvas.create_window((0, 0), window=inner, anchor="nw")
        scrollbar_visible = [False]

        def set_scrollbar(first, last):
            vsb.set(first, last)
            if float(first) <= 0.0 and float(last) >= 1.0:
                if scrollbar_visible[0]:
                    vsb.place_forget()
                    scrollbar_visible[0] = False
            elif not scrollbar_visible[0]:
                vsb.place(relx=1.0, rely=0.0, relheight=1.0, anchor="ne")
                scrollbar_visible[0] = True

        canvas.configure(yscrollcommand=set_scrollbar)
        canvas.pack(fill="both", expand=True)
        self._scroll_canvases.append(canvas)
        self._scroll_items[canvas] = iid

        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        last = [0]
        def on_canvas(e):
            if abs(e.width - last[0]) > 2:      # skip redundant reflows
                last[0] = e.width
                canvas.itemconfigure(iid, width=e.width)
        canvas.bind("<Configure>", on_canvas)
        # Wheel/trackpad scrolling is handled app-wide by _on_mousewheel.
        return inner

    def _on_main_tab_changed(self, _event=None):
        """Force macOS to repaint the newly exposed canvas after style changes."""
        self.root.after_idle(self._redraw_scroll_content)
        # Aqua reports the tab mapped before its native view is ready to draw.
        # A second pass after that view settles fixes the intermittent blank
        # canvas that an idle-only callback leaves behind.
        self.root.after(80, self._redraw_scroll_content)

    def _redraw_scroll_content(self):
        for canvas in self._scroll_canvases:
            try:
                if not canvas.winfo_ismapped():
                    continue
                item = self._scroll_items.get(canvas)
                if item:
                    # Aqua can leave a styled ttk tree logically mapped but
                    # visually blank when its Notebook tab was hidden during
                    # a theme change.  Detaching and reattaching the existing
                    # frame forces a real native remap; merely hiding the
                    # canvas item is not sufficient on macOS.
                    inner = canvas.nametowidget(canvas.itemcget(item, "window"))
                    yview = canvas.yview()
                    canvas.itemconfigure(item, window="")
                    canvas.update_idletasks()
                    canvas.itemconfigure(item, window=inner,
                                         width=canvas.winfo_width())
                    if yview:
                        canvas.yview_moveto(yview[0])
                    # The native macOS renderer also needs each ttk
                    # descendant exposed.  Without this, geometry and style
                    # lookups are correct but the old pixels remain blank.
                    pending = [inner]
                    while pending:
                        widget = pending.pop()
                        pending.extend(widget.winfo_children())
                        widget.event_generate("<Expose>")
                        widget.update_idletasks()
                canvas.configure(scrollregion=canvas.bbox("all"))
                canvas.event_generate("<Expose>")
            except tk.TclError:
                continue

    def _on_mousewheel(self, event):
        """
        Scroll the visible tab. Handles the different wheel conventions:
        macOS/trackpad send tiny deltas, Windows sends multiples of 120, and
        X11 sends Button-4/5 — the naive ``delta/120`` rounds macOS to zero,
        which is why the wheel appeared dead.
        """
        try:
            if event.widget.winfo_toplevel() is not self.root:
                return           # let the Focus & Tasks window handle its own
        except tk.TclError:
            return
        if event.num == 4:
            step = -1
        elif event.num == 5:
            step = 1
        else:
            d = event.delta
            step = int(-d / 120) if abs(d) >= 120 else (-1 if d > 0 else 1)
        if not step:
            return
        for c in self._scroll_canvases:
            try:
                if c.winfo_ismapped():
                    first, last = c.yview()
                    if (step < 0 and first <= 0.0) or (step > 0 and last >= 1.0):
                        return "break"
                    c.yview_scroll(step, "units")
                    return "break"
            except tk.TclError:
                continue

    def _theme_ui(self, rgb, brightness):
        """Match the window to the time of day: dark at night, phase-tinted.

        In high-contrast accessibility mode, use a fixed black/white/yellow
        palette regardless of the weather or time.
        """
        try:
            hc = (self.v_access.get() or "none") == "high_contrast"
            if hc:
                key = ("hc",)
                pal = dict(HIGH_CONTRAST)
            else:
                mode = (self.v_appearance.get() or "auto").lower()
                if mode == "dark":
                    dark = True
                elif mode == "light":
                    dark = False
                else:
                    dark = brightness is not None and brightness < 0.5
                # Key on the *mode* only, not the exact accent — so the (heavy)
                # ttk restyle runs only on light<->dark<->high-contrast flips,
                # not on every small colour change. Avoids constant Aqua churn.
                key = (dark, mode)
                pal = build_palette(dark, rgb)
            if key == self._ui_key:
                return
            self._ui_key = key
            self.pal = pal
            self._configure_styles()
            self.root.after_idle(self._redraw_scroll_content)
            self.root.after(80, self._redraw_scroll_content)
        except Exception as e:
            print(f"[gui] theme update skipped: {e}")

    # --- helpers -------------------------------------------------------
    @staticmethod
    def _alive(w):
        try:
            return bool(w) and w.winfo_exists()
        except tk.TclError:
            return False

    # --- UI shell ------------------------------------------------------
    def _build_ui(self):
        header = ttk.Frame(self.root, padding=(14, 12, 14, 6))
        header.pack(fill="x")
        ttk.Label(header, text="Flow", style="H1.TLabel").pack(side="left")
        ttk.Button(header, text="⏱  Focus & Tasks", style="Ghost.TButton",
                   command=self.open_tools).pack(side="right", padx=6)

        nb = ttk.Notebook(self.root)
        self.main_notebook = nb
        nb.pack(fill="both", expand=True, padx=12, pady=(4, 6))
        nb.add(self._tab_dashboard(nb), text="  Dashboard  ")
        nb.add(self._tab_settings(nb), text="  Settings  ")
        nb.bind("<<NotebookTabChanged>>", self._on_main_tab_changed)
        self._set_feature_controls_state(self.v_enabled.get())

        bar = ttk.Frame(self.root, padding=(12, 4))
        bar.pack(fill="x", side="bottom")
        self.status_lbl = ttk.Label(bar, textvariable=self.v_status, style="Bar.TLabel")
        self.status_lbl.pack(side="left")

        # Apply the profile / accessibility / hemisphere / appearance / privacy
        # combos live.
        for v in (self.v_profile, self.v_access, self.v_hemisphere,
                  self.v_appearance):
            v.trace_add("write", lambda *_: self._on_override_change())

        # Mouse wheel / trackpad scrolling for the whole window (macOS, Windows
        # and X11 conventions all covered by _on_mousewheel).
        self.root.bind_all("<MouseWheel>", self._on_mousewheel)
        self.root.bind_all("<Button-4>", self._on_mousewheel)
        self.root.bind_all("<Button-5>", self._on_mousewheel)

    # --- Dashboard tab -------------------------------------------------
    def _tab_dashboard(self, parent):
        page = ttk.Frame(parent, padding=(10, 8))
        body = self._make_scroll(page)

        # Weather card ----------------------------------------------------
        wc = _card(body)
        top = ttk.Frame(wc, style="Card.TFrame"); top.pack(fill="x")
        ttk.Label(top, textvariable=self.v_wicon, style="Icon.TLabel").pack(side="left", padx=(0, 12))
        mid = ttk.Frame(top, style="Card.TFrame"); mid.pack(side="left", fill="x", expand=True)
        ttk.Label(mid, textvariable=self.v_wcond, style="Cond.TLabel").pack(anchor="w")
        ttk.Label(mid, textvariable=self.v_wsub, style="Muted.TLabel").pack(anchor="w")
        ttk.Label(top, textvariable=self.v_wtemp, style="Temp.TLabel").pack(side="right")
        _responsive_label(
            wc, textvariable=self.v_wdetails, style="Muted.TLabel"
        ).pack(anchor="w", pady=(8, 0))
        ttk.Button(wc, text="↻ Refresh weather", style="Ghost.TButton",
                   command=self.refresh_weather).pack(anchor="e", pady=(4, 0))

        # Mood profile ----------------------------------------------------
        pc = _card(body, "Mood profile")
        prow = ttk.Frame(pc, style="Card.TFrame"); prow.pack(fill="x")
        for val, txt in [("none", "Off"), ("focus", "🎯 Focus"),
                         ("creativity", "🎨 Creativity"), ("relax", "🌿 Relax")]:
            ttk.Radiobutton(prow, text=txt, value=val, variable=self.v_profile,
                            style="Card.TRadiobutton",
                            command=self._on_override_change).pack(side="left", padx=(0, 10))
        _responsive_label(
            pc, style="Muted.TLabel",
            text="A profile shifts the whole vibe — Focus is calm & quiet, "
                 "Creativity vivid & lively, Relax warm & gentle."
        ).pack(anchor="w", pady=(6, 0))

        # Master + features ----------------------------------------------
        fc = _card(body, "Features")
        ttk.Checkbutton(fc, text="Enable everything (master switch)",
                        style="Card.TCheckbutton", command=self.on_master_toggle,
                        variable=self.v_enabled).pack(anchor="w", pady=(0, 6))
        for text, var, cmd in [("🎨  System accent follows theme", self.v_theme,
                                self._on_override_change),
                               ("🖼  Weather wallpaper", self.v_wallpaper, self._on_override_change),
                               ("🔊  Ambient sound", self.v_sound, self.on_sound_toggle)]:
            kw = {"command": cmd} if cmd else {}
            checkbutton = ttk.Checkbutton(
                fc, text=text, style="Card.TCheckbutton", variable=var, **kw)
            checkbutton.pack(anchor="w", pady=1)
            self.feature_checks.append(checkbutton)
        _responsive_label(
            fc, style="Muted.TLabel",
            text="System accent changes the Windows taskbar/title colour or the "
                 "nearest named macOS accent. Auto accent colour follows weather "
                 "and time; a picked colour below overrides it. Existing macOS "
                 "apps may need relaunching."
        ).pack(anchor="w", pady=(6, 0))

        # Manual theme changer -------------------------------------------
        mcard = _card(body, "Manual theme changer")
        self._combo_row(mcard, "Weather", self.v_weather, config.WEATHER_CHOICES)
        self._combo_row(mcard, "Time of day", self.v_time, config.TIME_CHOICES)

        crow = ttk.Frame(mcard, style="Card.TFrame"); crow.pack(fill="x", pady=4)
        ttk.Label(crow, text="Accent colour", style="Card.TLabel", width=12).pack(side="left")
        self.swatch = tk.Label(crow, width=3, relief="groove", bg=self._swatch_color())
        self.swatch.pack(side="left", padx=(0, 8))
        entry = ttk.Entry(crow, textvariable=self.v_color, width=14)
        entry.pack(side="left")
        entry.bind("<Return>", lambda e: self._on_override_change())
        ttk.Button(crow, text="Pick…", style="Ghost.TButton",
                   command=self.on_pick_color).pack(side="left", padx=6)
        ttk.Button(crow, text="Auto", style="Ghost.TButton",
                   command=self._on_auto_color).pack(side="left")
        self.v_color.trace_add("write", lambda *_: self._update_swatch())
        # Apply weather/time the instant the selection changes. A variable
        # trace is more reliable across platforms than a widget event.
        self.v_weather.trace_add("write", lambda *_: self._on_override_change())
        self.v_time.trace_add("write", lambda *_: self._on_override_change())
        return page

    # --- Settings tab --------------------------------------------------
    def _tab_settings(self, parent):
        page = ttk.Frame(parent, padding=(10, 8))
        body = self._make_scroll(page)

        wp = _card(body, "Wallpaper look")
        self._slider(wp, "Weather tint strength", self.v_tint)
        ttk.Checkbutton(wp, text="Dynamic (subtle colour shift)", style="Card.TCheckbutton",
                        variable=self.v_wpdynamic).pack(anchor="w", pady=(6, 0))
        self._slider(wp, "Colour shift strength", self.v_wpshift)
        ttk.Checkbutton(wp, text="Weather patterns (rain, sun, clouds, stars)",
                        style="Card.TCheckbutton",
                        variable=self.v_wppatterns).pack(anchor="w", pady=(6, 0))
        ttk.Checkbutton(wp, text="Warm palette when it's cold outside",
                        style="Card.TCheckbutton",
                        variable=self.v_wpwarmth).pack(anchor="w")

        sc = _card(body, "Sound")
        self._slider(sc, "Ambient volume", self.v_volume)
        ttk.Checkbutton(sc, text="Pause ambient when other audio is playing",
                        style="Card.TCheckbutton", variable=self.v_duck,
                        command=self._on_override_change).pack(anchor="w", pady=(6, 0))
        ttk.Button(sc, text="🎵  Sound files… (names + open folder)", style="Ghost.TButton",
                   command=self.on_manage_sounds).pack(anchor="w", pady=(8, 0))
        _responsive_label(
            sc, style="Muted.TLabel",
            text="Ambience loops continuously. Add several clips per weather "
                 "for variety, e.g. rain.wav and rain2.wav — a different one "
                 "can be chosen when the weather changes."
        ).pack(anchor="w", pady=(6, 0))

        # Seasons & transitions ------------------------------------------
        st = _card(body, "Seasons & transitions")
        ttk.Checkbutton(st, text="Gradual transitions (cross-fade times & weather)",
                        style="Card.TCheckbutton", variable=self.v_smooth,
                        command=self._on_override_change).pack(anchor="w")
        ttk.Checkbutton(st, text="Seasonal palette (spring green … winter blue)",
                        style="Card.TCheckbutton", variable=self.v_season,
                        command=self._on_override_change).pack(anchor="w")
        hr = ttk.Frame(st, style="Card.TFrame"); hr.pack(fill="x", pady=(4, 0))
        ttk.Label(hr, text="Hemisphere", style="Card.TLabel", width=12).pack(side="left")
        ttk.Combobox(hr, textvariable=self.v_hemisphere, state="readonly", width=8,
                     values=config.HEMISPHERE_CHOICES).pack(side="left")

        # Device appearance (Dark/Light lock) ----------------------------
        dc = _card(body, "Device appearance")
        dr = ttk.Frame(dc, style="Card.TFrame"); dr.pack(fill="x")
        ttk.Label(dr, text="Dark / Light", style="Card.TLabel", width=12).pack(side="left")
        ttk.Combobox(dr, textvariable=self.v_appearance, state="readonly", width=10,
                     values=config.APPEARANCE_CHOICES).pack(side="left")
        _responsive_label(
            dc, style="Muted.TLabel",
            text="auto follows the time of day. dark / light lock the whole "
                 "device (and this window) to that mode."
        ).pack(anchor="w", pady=(6, 0))

        # Accessibility ---------------------------------------------------
        ac = _card(body, "Accessibility")
        ar = ttk.Frame(ac, style="Card.TFrame"); ar.pack(fill="x")
        ttk.Label(ar, text="Mode", style="Card.TLabel", width=12).pack(side="left")
        ttk.Combobox(ar, textvariable=self.v_access, state="readonly", width=14,
                     values=config.ACCESSIBILITY_CHOICES).pack(side="left")
        _responsive_label(
            ac, style="Muted.TLabel",
            text="high_contrast forces bold, maximum-contrast colours and a "
                 "black/white/yellow window, ignoring the time of day."
        ).pack(anchor="w", pady=(6, 0))

        ec = _card(body, "Engine")
        ir = ttk.Frame(ec, style="Card.TFrame"); ir.pack(fill="x", pady=2)
        ttk.Label(ir, text="Tick (s)", style="Card.TLabel", width=12).pack(side="left")
        ttk.Spinbox(ir, from_=5, to=3600, textvariable=self.v_tick, width=6).pack(side="left")
        ttk.Label(ir, text="Weather refresh (s)", style="Card.TLabel").pack(side="left", padx=(14, 4))
        ttk.Spinbox(ir, from_=30, to=7200, textvariable=self.v_weatherrefresh, width=7).pack(side="left")
        cr = ttk.Frame(ec, style="Card.TFrame"); cr.pack(fill="x", pady=(8, 0))
        ttk.Label(cr, text="City", style="Card.TLabel", width=14).pack(side="left")
        city_cb = ttk.Combobox(cr, textvariable=self.v_city, state="readonly", width=24,
                               values=config.city_choices())
        city_cb.pack(side="left")
        city_cb.bind("<<ComboboxSelected>>", lambda e: self._on_city_change())
        ttk.Checkbutton(ec, text="Set wallpaper on all monitors", style="Card.TCheckbutton",
                        variable=self.v_multimon,
                        command=self._on_override_change).pack(anchor="w", pady=(8, 0))
        ttk.Checkbutton(ec, text="Run automatically at login", style="Card.TCheckbutton",
                        variable=self.v_runlogin,
                        command=self.on_toggle_autostart).pack(anchor="w", pady=(4, 0))
        return page

    # --- small reusable widgets ----------------------------------------
    def _combo_row(self, parent, label, var, values, on_change=None):
        row = ttk.Frame(parent, style="Card.TFrame"); row.pack(fill="x", pady=4)
        ttk.Label(row, text=label, style="Card.TLabel", width=12).pack(side="left")
        cb = ttk.Combobox(row, textvariable=var, state="readonly", width=12,
                          values=values)
        cb.pack(side="left")
        if on_change:
            cb.bind("<<ComboboxSelected>>", lambda e: on_change())

    def _slider(self, parent, label, var, from_=0, to=100, unit="%"):
        card = parent.winfo_class() == "TFrame"
        row = ttk.Frame(parent, style="Card.TFrame" if card else "TFrame")
        row.pack(fill="x", pady=4)
        ttk.Label(row, text=label, style="Card.TLabel", width=18).pack(side="left")
        fmt = (lambda: f"{int(var.get())} {unit}".rstrip())
        val = ttk.Label(row, text=fmt(), style="Card.TLabel", width=6, anchor="e")
        val.pack(side="right")
        var.trace_add("write", lambda *_: val.config(text=fmt()))
        ttk.Scale(row, from_=from_, to=to, orient="horizontal",
                  variable=var).pack(fill="x", side="left", expand=True, padx=8)

    # --- weather card --------------------------------------------------
    def refresh_weather(self):
        """Fetch the effective weather in the background and update the card."""
        self.v_wcond.set("Fetching weather…")

        def work():
            try:
                w = weather.get_effective_weather(self.cfg)
                mt = (self.cfg.get("manual_time") or "auto").lower()
                ph = (theme.normalize_phase(mt) if mt != "auto"
                      else theme.compute_day_phase(w["sunrise"], w["sunset"]))
                rgb, bright = theme.compute_theme_color(
                    w["condition"], w["sunrise"], w["sunset"], phase=ph)
                data = dict(w)
                data.update({"phase": ph, "color": list(rgb), "brightness": bright})
            except Exception as e:
                data = {"error": str(e)}
            self.status_queue.put({"_weather_card": data})
        threading.Thread(target=work, daemon=True).start()

    def _update_weather_card(self, d):
        if "error" in d:
            self.v_wcond.set("Weather unavailable")
            self.v_wsub.set(str(d["error"])[:60])
            self.v_wicon.set("⚠️")
            return
        cond = d.get("condition") or "?"
        is_night = bool(d.get("is_night"))
        self.v_wicon.set(_weather_icon(cond, is_night))
        self.v_wtemp.set(_fmt_temp(d.get("temperature")))
        tod = d.get("phase") or ("night" if is_night else "day")
        self.v_wcond.set(_weather_summary(
            cond, tod, manual=d.get("condition_source") == "manual"))
        loc = self.cfg.get("location", {}).get("name", "")
        src = d.get("source")
        self.v_wsub.set(f"{loc}   ({src})" if src else loc)
        self.v_wdetails.set(_fmt_details(d))
        # Match the window's look to the time of day.
        if d.get("color") and d.get("brightness") is not None:
            self._effective_swatch = tuple(d["color"])
            self._update_swatch()
            self._theme_ui(d["color"], d["brightness"])

    # --- manual colour -------------------------------------------------
    def _swatch_color(self):
        try:
            r, g, b = [int(x) for x in self.v_color.get().split(",")]
            return f"#{r:02x}{g:02x}{b:02x}"
        except (ValueError, AttributeError):
            return (_hex(self._effective_swatch) if self._effective_swatch
                    else self.pal["CARD"])

    def _update_swatch(self):
        if self._alive(getattr(self, "swatch", None)):
            self.swatch.config(bg=self._swatch_color())

    def on_pick_color(self):
        init = self._swatch_color()
        rgb, _hex = colorchooser.askcolor(color=init, title="Pick accent colour")
        if rgb:
            self.v_color.set(",".join(str(int(v)) for v in rgb))
            self._on_override_change()

    def _on_auto_color(self):
        self.v_color.set("auto")
        self._on_override_change()

    # --- live apply ----------------------------------------------------
    def _on_override_change(self):
        """A manual override changed — apply it right away."""
        self._schedule_auto_apply("Settings updated")

    def _bind_auto_apply(self):
        """Persist and apply every main-window setting without action buttons."""
        variables = (
            self.v_theme, self.v_wallpaper, self.v_tint, self.v_wpdynamic,
            self.v_wpshift, self.v_wppatterns, self.v_wpwarmth,
            self.v_duck, self.v_tick, self.v_weatherrefresh, self.v_smooth, self.v_season,
            self.v_multimon,
        )
        for variable in variables:
            variable.trace_add("write", lambda *_: self._schedule_auto_apply())

    def _schedule_auto_apply(self, note="Settings updated"):
        job = self._auto_apply_job
        if job:
            try:
                self.root.after_cancel(job)
            except Exception:
                pass
        self._auto_apply_job = self.root.after(
            150, lambda: self._flush_auto_apply(note))

    def _flush_auto_apply(self, note):
        self._auto_apply_job = None
        self._apply_live(note)

    def _start_engine(self):
        self.engine_thread = engine.EngineThread(
            on_status=lambda st: self.status_queue.put(st))
        self.engine_thread.start()
        self.v_status.set("Running — settings apply automatically.")

    def _on_city_change(self):
        """City picked — save the new location, re-fetch weather, and apply."""
        self._apply_live("City updated")
        self.refresh_weather()

    def _on_ambient_volume(self, *_):
        """Ambient-volume slider moved: change the playing sound at once, and
        persist (debounced) so the engine keeps the new level."""
        try:
            sound.set_volume(self.v_volume.get())      # instant feedback
        except Exception:
            pass
        job = getattr(self, "_vol_save_job", None)
        if job:
            try:
                self.root.after_cancel(job)
            except Exception:
                pass
        try:
            self._vol_save_job = self.root.after(400, self._save_volume)
        except Exception:
            self._save_volume()

    def _save_volume(self):
        self._vol_save_job = None
        self._collect()
        config.save_config(self.cfg)
        if self.engine_thread and self.engine_thread.is_alive():
            self.engine_thread.wake()
        self.v_status.set(f"Ambient volume: {int(self.v_volume.get())}%")

    def _on_music_volume(self, *_):
        """Apply music volume immediately and persist it with other settings."""
        music.set_volume(self.v_musicvol.get())
        self._schedule_auto_apply("Music volume updated")

    def _apply_live(self, note):
        """
        Persist current settings and apply them *immediately* so a manual
        change is visible at once. Runs one unconditional engine tick (which
        bypasses the redraw-interval guard) in the background, and wakes the
        running engine so its cadence resyncs.
        """
        try:
            self._collect()
            config.save_config(self.cfg)
            if self.engine_thread and self.engine_thread.is_alive():
                # The engine applies on its own (single) thread — just nudge it.
                # Running a second tick here would fight it (concurrent pygame /
                # osascript access crashes on macOS). Drop its change-guards so
                # the new look (e.g. a picked accent) applies immediately instead
                # of being suppressed by the signature / redraw-interval checks.
                eng = self.engine_thread.engine
                eng.invalidate_visuals()
                self.engine_thread.wake()
                self.v_status.set(note)
                return
            # Not running: preview via ONE background tick, never overlapping.
            if self._apply_busy:
                return
            self._apply_busy = True
            self.v_status.set(f"{note} — applying…")
            threading.Thread(target=self._tick_bg, daemon=True).start()
        except Exception as e:
            self._apply_busy = False
            self.v_status.set(f"Apply failed: {e}")

    def _tick_bg(self):
        try:
            self.status_queue.put(engine.tick(self.cfg, self.store))
        except Exception as e:
            self.status_queue.put({"error": str(e)})
        finally:
            self._apply_busy = False

    # --- Focus & Tasks window ------------------------------------------
    def open_tools(self):
        if self._alive(self.tools_win):
            self.tools_win.lift()
            self.tools_win.focus_force()
            return
        win = tk.Toplevel(self.root)
        self.tools_win = win
        win.title("Focus & Tasks")
        win.geometry("560x640")
        win.minsize(500, 560)
        win.configure(bg=self.pal["BG"])
        win.protocol("WM_DELETE_WINDOW", self.on_tools_close)

        nb = ttk.Notebook(win)
        nb.pack(fill="both", expand=True, padx=12, pady=12)
        nb.add(self._build_timers_frame(nb), text="  Timers  ")
        nb.add(self._build_tasks_frame(nb), text="  To-Do & Schedules  ")
        nb.add(self._build_music_frame(nb), text="  Music  ")
        self._refresh_tasks()
        self._update_timer_label()

    def on_tools_close(self):
        if self._alive(self.tools_win):
            self.tools_win.destroy()
        self.tools_win = None
        self.tree = None
        self.btn_timer = None
        self.lbl_cycles = None
        self.music_list = None
        self.btn_music_play = None
        self.timer_label = None
        self.clock_settings = None
        self.btn_clock_extra = None

    def _build_music_frame(self, parent):
        page = ttk.Frame(parent, padding=12)
        card = _card(page, "Your music")
        ttk.Label(card, textvariable=self.music_now, style="CardH.TLabel").pack(anchor="w", pady=(0, 6))
        lb = tk.Listbox(card, height=8, activestyle="none", highlightthickness=0,
                        borderwidth=0, bg=self.pal["FIELD"], fg=self.pal["INK"],
                        selectbackground=self.pal["ACCENT"], selectforeground=self.pal["ACCENT_FG"])
        lb.pack(fill="both", expand=True)
        lb.bind("<Double-Button-1>", lambda e: self.on_music_play())
        self.music_list = lb

        ctl = ttk.Frame(card, style="Card.TFrame"); ctl.pack(fill="x", pady=(8, 0))
        ttk.Button(ctl, text="⏮", width=3, style="Ghost.TButton", command=self.on_music_prev).pack(side="left")
        # One button that flips between Play and Pause with the playback state.
        self.btn_music_play = ttk.Button(ctl, text="▶ Play", style="Accent.TButton",
                                         command=self.on_music_toggle)
        self.btn_music_play.pack(side="left", padx=4)
        ttk.Button(ctl, text="⏹", width=3, style="Ghost.TButton", command=self.on_music_stop).pack(side="left")
        ttk.Button(ctl, text="⏭", width=3, style="Ghost.TButton", command=self.on_music_next).pack(side="left", padx=4)
        self._slider(card, "Music volume", self.v_musicvol)

        files = ttk.Frame(card, style="Card.TFrame"); files.pack(fill="x", pady=(6, 0))
        ttk.Button(files, text="Add songs…", style="Ghost.TButton", command=self.on_music_add).pack(side="left")
        ttk.Button(files, text="Open music folder", style="Ghost.TButton", command=self.on_music_open).pack(side="left", padx=4)
        ttk.Button(files, text="Refresh", style="Ghost.TButton", command=self.on_music_refresh).pack(side="left")
        _responsive_label(
            card, style="Muted.TLabel",
            text="Drop .mp3 / .ogg / .wav files in the music folder (or Add songs…), "
                 "then Play. Music pauses weather ambience while it plays."
        ).pack(anchor="w", pady=(6, 0))

        self.on_music_refresh()
        self._update_music_label()
        return page

    # --- music handlers ------------------------------------------------
    def on_music_refresh(self):
        if not self._alive(self.music_list):
            return
        self.music_list.delete(0, "end")
        for p in music.list_tracks():
            self.music_list.insert("end", os.path.basename(p))

    def _nudge_engine(self):
        """Make the engine re-evaluate ambient now (music > ambient), so it
        pauses/resumes the ambience the moment music starts or stops."""
        if self.engine_thread and self.engine_thread.is_alive():
            self.engine_thread.wake()

    def on_music_play(self):
        tracks = music.list_tracks()
        if not tracks:
            messagebox.showinfo("No music",
                                "Add some songs first (Add songs…) or drop files in the music folder.")
            return
        idx = 0
        if self._alive(self.music_list) and self.music_list.curselection():
            idx = self.music_list.curselection()[0]
        if music.play_list(tracks, idx, self.v_musicvol.get()):
            self._nudge_engine()          # pause ambient right away
        else:
            messagebox.showwarning("Music", "Couldn't play — is pygame installed? (pip install pygame)")
        self._update_music_label()

    def on_music_toggle(self):
        """Play / Pause / Resume from one button, matching the current state."""
        if music.is_playing():
            music.toggle_pause()          # playing -> pause
        elif music.is_paused():
            music.toggle_pause()          # paused -> resume
        else:
            self.on_music_play()          # stopped -> start (also updates label)
            return
        self._nudge_engine()              # ambient follows: pause on play, resume on pause
        self._update_music_label()

    def on_music_stop(self):
        music.stop()
        self._nudge_engine()              # resume ambient now that music stopped
        self._update_music_label()

    def on_music_next(self):
        music.next_track(self.v_musicvol.get())
        self._nudge_engine()
        self._update_music_label()

    def on_music_prev(self):
        music.prev_track(self.v_musicvol.get())
        self._nudge_engine()
        self._update_music_label()

    def on_music_open(self):
        music.open_folder()

    def on_music_add(self):
        paths = filedialog.askopenfilenames(
            title="Add songs",
            filetypes=[("Audio", "*.mp3 *.ogg *.wav *.flac *.m4a"), ("All files", "*.*")])
        if not paths:
            return
        import shutil
        music.ensure_dir()
        added = 0
        for p in paths:
            try:
                shutil.copy(p, music.MUSIC_DIR)
                added += 1
            except Exception as e:
                print(f"[music] copy failed: {e}")
        self.on_music_refresh()
        self.v_status.set(f"Added {added} song(s) to the music folder.")

    def _update_music_label(self):
        cur = music.current()
        if cur:
            state = "Paused: " if music.is_paused() else "Playing: "
            self.music_now.set(state + os.path.basename(cur))
        else:
            self.music_now.set("Nothing playing")
        # The main button shows Pause while playing, Play otherwise.
        if self._alive(getattr(self, "btn_music_play", None)):
            self.btn_music_play.config(
                text="⏸ Pause" if music.is_playing() else "▶ Play")

    def _build_timers_frame(self, parent):
        page = ttk.Frame(parent, padding=12)

        # Mode: Pomodoro / countdown Timer / Stopwatch.
        mode = _card(page, "Timer mode")
        mrow = ttk.Frame(mode, style="Card.TFrame"); mrow.pack(fill="x")
        for val, txt in [("pomodoro", "🍅 Pomodoro"), ("timer", "⏲ Timer"),
                         ("stopwatch", "⏱ Stopwatch")]:
            ttk.Radiobutton(mrow, text=txt, value=val, variable=self.v_clockmode,
                            style="Card.TRadiobutton",
                            command=self._on_clockmode).pack(side="left", padx=(0, 10))

        # Shared big display + controls.
        disp = _card(page)
        self.timer_label = ttk.Label(
            disp, textvariable=self.v_timer, style="Timer.TLabel",
            anchor="center", justify="center")
        self.timer_label.pack(fill="x", pady=(6, 2))
        disp.bind("<Configure>", lambda _event: self._fit_timer_text())
        self.lbl_cycles = ttk.Label(disp, text="", style="Muted.TLabel")
        self.lbl_cycles.pack()
        ctl = ttk.Frame(disp, style="Card.TFrame"); ctl.pack(pady=12)
        self.btn_timer = ttk.Button(ctl, text="Start", style="Accent.TButton",
                                    command=self.on_clock_toggle)
        self.btn_timer.pack(side="left", padx=4)
        self.btn_clock_extra = ttk.Button(ctl, text="Skip", style="Ghost.TButton",
                                          command=self.on_clock_extra)
        self.btn_clock_extra.pack(side="left", padx=4)
        ttk.Button(ctl, text="Reset", style="Ghost.TButton",
                   command=self.on_clock_reset).pack(side="left", padx=4)

        # Per-mode settings, rebuilt when the mode changes.
        wrap = _card(page)
        self.clock_settings = ttk.Frame(wrap, style="Card.TFrame")
        self.clock_settings.pack(fill="both", expand=True)

        self._on_clockmode()
        return page

    def _active_clock(self):
        return {"pomodoro": self.pomo, "timer": self.timer,
                "stopwatch": self.stopwatch}[self.v_clockmode.get()]

    def _fit_timer_text(self):
        """Shrink long timer states enough to fit narrow Focus windows."""
        if not self._alive(self.timer_label):
            return
        available = max(220, self.timer_label.winfo_width() - 12)
        text = self.v_timer.get()

        def measure(value, size):
            return tkfont.Font(
                root=self.root, family="Helvetica", size=size,
                weight="bold").measure(value)

        size = _largest_fitting_font(text, available, measure)
        self.timer_label.configure(
            font=("Helvetica", size, "bold"), wraplength=available)

    def _on_clockmode(self):
        self._rebuild_clock_settings()
        self._sync_extra_button()
        self._update_timer_label()

    def _sync_extra_button(self):
        if not self._alive(self.btn_clock_extra):
            return
        m = self.v_clockmode.get()
        if m == "pomodoro":
            self.btn_clock_extra.config(text="Skip", state="normal")
        elif m == "stopwatch":
            self.btn_clock_extra.config(text="Lap", state="normal")
        else:
            self.btn_clock_extra.config(text="Skip", state="disabled")

    def _rebuild_clock_settings(self):
        if not self._alive(self.clock_settings):
            return
        for w in self.clock_settings.winfo_children():
            w.destroy()
        self.lap_box = None
        m = self.v_clockmode.get()
        c = self.clock_settings
        if m == "pomodoro":
            ttk.Label(c, text="Durations (minutes)", style="CardH.TLabel").pack(anchor="w", pady=(0, 4))
            for label, var, hi in [("Work", self.v_pwork, 120), ("Break", self.v_pbreak, 60),
                                   ("Long break", self.v_plong, 120), ("Cycles → long", self.v_pcycles, 12)]:
                row = ttk.Frame(c, style="Card.TFrame"); row.pack(fill="x", pady=2)
                ttk.Label(row, text=label, style="Card.TLabel", width=14).pack(side="left")
                ttk.Spinbox(row, from_=1, to=hi, textvariable=var, width=6).pack(side="left")
            ttk.Button(c, text="Apply durations", style="Ghost.TButton",
                       command=self.on_timer_apply_durations).pack(anchor="e", pady=(6, 0))
        elif m == "timer":
            row = ttk.Frame(c, style="Card.TFrame"); row.pack(fill="x", pady=2)
            ttk.Label(row, text="Minutes", style="Card.TLabel", width=14).pack(side="left")
            ttk.Spinbox(row, from_=1, to=600, textvariable=self.v_timermin, width=6).pack(side="left")
            ttk.Button(row, text="Set", style="Ghost.TButton",
                       command=self.on_timer_set).pack(side="left", padx=6)
            ttk.Label(c, style="Muted.TLabel",
                      text="Counts down and chimes when it reaches zero.").pack(anchor="w", pady=(4, 0))
        else:  # stopwatch
            ttk.Label(c, text="Laps", style="CardH.TLabel").pack(anchor="w")
            self.lap_box = tk.Listbox(c, height=5, activestyle="none", highlightthickness=0,
                                      borderwidth=0, bg=self.pal["FIELD"], fg=self.pal["INK"])
            self.lap_box.pack(fill="both", expand=True)
            self._refresh_laps()

    def _refresh_laps(self):
        if not self._alive(self.lap_box):
            return
        self.lap_box.delete(0, "end")
        for i, t in enumerate(self.stopwatch.laps, 1):
            self.lap_box.insert("end", f"Lap {i}:   {clocks.format_time(t)}")

    def _build_tasks_frame(self, parent):
        page = ttk.Frame(parent, padding=12)
        listcard = _card(page, "Scheduled reminders")
        cols = ("title", "when", "does")
        self.tree = ttk.Treeview(listcard, columns=cols, show="headings", height=7)
        for c, w, txt in zip(cols, (150, 150, 150), ("Reminder", "When", "Does")):
            self.tree.heading(c, text=txt)
            self.tree.column(c, width=w)
        self.tree.pack(fill="both", expand=True)

        form = _card(page, "New reminder")
        self.t_title = tk.StringVar()
        self.t_action = tk.StringVar(value=ACTION_TO_LABEL["notify"])
        self.t_value = tk.StringVar()
        self.t_repeat = tk.StringVar(value="Every day")
        self.t_time = tk.StringVar(value="08:00")
        self.t_date = tk.StringVar(value=datetime.date.today().isoformat())

        # What to call it.
        r = ttk.Frame(form, style="Card.TFrame"); r.pack(fill="x", pady=3)
        ttk.Label(r, text="Title", style="Card.TLabel", width=8).pack(side="left")
        ttk.Entry(r, textvariable=self.t_title).pack(side="left", fill="x", expand=True)

        # What it does.
        r = ttk.Frame(form, style="Card.TFrame"); r.pack(fill="x", pady=3)
        ttk.Label(r, text="Do", style="Card.TLabel", width=8).pack(side="left")
        ttk.Combobox(r, textvariable=self.t_action, state="readonly", width=20,
                     values=list(ACTION_TO_LABEL.values())).pack(side="left")

        # Extra detail for the chosen action (only shown when needed).
        self.val_row = ttk.Frame(form, style="Card.TFrame")
        self.val_row.pack(fill="x", pady=3)

        # When: every day, or once on a given date — always at a time.
        r = ttk.Frame(form, style="Card.TFrame"); r.pack(fill="x", pady=3)
        ttk.Label(r, text="When", style="Card.TLabel", width=8).pack(side="left")
        ttk.Combobox(r, textvariable=self.t_repeat, state="readonly", width=10,
                     values=["Every day", "Just once"]).pack(side="left")
        ttk.Label(r, text="at", style="Card.TLabel").pack(side="left", padx=(8, 2))
        ttk.Entry(r, textvariable=self.t_time, width=7).pack(side="left")
        ttk.Label(r, text="24-hour, e.g. 07:30", style="Muted.TLabel").pack(side="left", padx=4)

        # Date row — appears only for a one-off (lets you pick a future day).
        self.date_row = ttk.Frame(form, style="Card.TFrame")
        ttk.Label(self.date_row, text="On", style="Card.TLabel", width=8).pack(side="left")
        ttk.Entry(self.date_row, textvariable=self.t_date, width=12).pack(side="left")
        ttk.Button(self.date_row, text="Today", style="Ghost.TButton",
                   command=lambda: self.t_date.set(datetime.date.today().isoformat())
                   ).pack(side="left", padx=3)
        ttk.Button(self.date_row, text="Tomorrow", style="Ghost.TButton",
                   command=lambda: self.t_date.set(
                       (datetime.date.today() + datetime.timedelta(days=1)).isoformat())
                   ).pack(side="left", padx=3)
        ttk.Button(self.date_row, text="+1 week", style="Ghost.TButton",
                   command=lambda: self.t_date.set(_shift_iso_date(self.t_date.get(), 7))
                   ).pack(side="left", padx=3)

        self.t_action.trace_add("write", lambda *_: self._on_task_action_change())
        self.t_repeat.trace_add("write", lambda *_: self._on_task_repeat_change())

        btns = ttk.Frame(page); btns.pack(fill="x", pady=(4, 0))
        ttk.Button(btns, text="Add reminder", style="Accent.TButton",
                   command=self.on_add_task).pack(side="left")
        ttk.Button(btns, text="Remove selected", style="Ghost.TButton",
                   command=self.on_remove_task).pack(side="left", padx=6)

        self._on_task_action_change()
        self._on_task_repeat_change()
        return page

    def _on_task_action_change(self):
        """Show the right extra field for the chosen action (or none)."""
        if not self._alive(getattr(self, "val_row", None)):
            return
        for w in self.val_row.winfo_children():
            w.destroy()
        action = LABEL_TO_ACTION.get(self.t_action.get(), "notify")
        self.t_value.set("")
        msg = "— just shows a notification" if action == "notify" else "— just plays a chime"
        ttk.Label(self.val_row, text=msg, style="Muted.TLabel").pack(side="left")

    def _on_task_repeat_change(self):
        """The date picker only makes sense for a one-off reminder."""
        if not self._alive(getattr(self, "date_row", None)):
            return
        if self.t_repeat.get() == "Just once":
            self.date_row.pack(fill="x", pady=3)
        else:
            self.date_row.pack_forget()

    # --- timers (pomodoro / countdown / stopwatch) ---------------------
    def _update_timer_label(self):
        active = self._active_clock()
        self.v_timer.set(active.label())
        if self._alive(self.timer_label):
            self.root.after_idle(self._fit_timer_text)
        if self._alive(self.lbl_cycles):
            m = self.v_clockmode.get()
            if m == "pomodoro":
                self.lbl_cycles.config(
                    text=f"Completed work sessions: {self.pomo.completed_work}")
            elif m == "timer":
                self.lbl_cycles.config(
                    text="Finished" if self.timer.finished
                    else ("Running" if self.timer.running else "Paused"))
            else:
                self.lbl_cycles.config(
                    text=f"{len(self.stopwatch.laps)} lap(s)" if self.stopwatch.laps
                    else "Stopwatch")
        if self._alive(self.btn_timer):
            self.btn_timer.config(text="Pause" if active.running else "Start")

    def _timer_loop(self):
        # Tick all three so a running clock keeps going while another is shown.
        ev = self.pomo.tick(1) if self.pomo.running else None
        if ev:
            event, _nxt = ev
            msg = ("Work done — time for a break."
                   if event == "work_complete" else "Break over — back to work.")
            try:
                sound.play_chime()
            except Exception:
                pass
            engine.notify("Pomodoro", msg)
            self.v_status.set(f"Pomodoro: {msg}")
        self.stopwatch.tick(1)
        if self.timer.tick(1) == "done":
            try:
                sound.play_chime()
            except Exception:
                pass
            engine.notify("Timer", "Timer finished.")
            self.v_status.set("Timer finished.")
        self._update_timer_label()
        # Music plays only when the user presses Play — it never advances or
        # restarts on its own. When a track ends it simply stops; we just keep
        # the label + Play/Pause button in sync with that.
        self._update_music_label()
        self.root.after(1000, self._timer_loop)

    def on_clock_toggle(self):
        self._active_clock().toggle()
        self._update_timer_label()

    def on_clock_reset(self):
        self._active_clock().reset()
        if self.v_clockmode.get() == "stopwatch":
            self._refresh_laps()
        self._update_timer_label()

    def on_clock_extra(self):
        m = self.v_clockmode.get()
        if m == "pomodoro":
            self.pomo.skip()
        elif m == "stopwatch":
            self.stopwatch.lap()
            self._refresh_laps()
        self._update_timer_label()

    def on_timer_set(self):
        self.timer.set_minutes(self.v_timermin.get())
        self._collect()
        config.save_config(self.cfg)
        self._update_timer_label()

    def on_timer_apply_durations(self):
        self.pomo.configure(self.v_pwork.get(), self.v_pbreak.get(),
                            self.v_plong.get(), self.v_pcycles.get())
        self._collect()
        config.save_config(self.cfg)
        self.v_status.set("Timer durations updated.")
        self._update_timer_label()

    # --- task helpers --------------------------------------------------
    def _refresh_tasks(self):
        if not self._alive(self.tree):
            return
        for item in self.tree.get_children():
            self.tree.delete(item)
        for t in self.store.list_tasks():
            self.tree.insert("", "end", iid=t["id"], values=(
                t.get("title", ""), _task_when_str(t), _task_does_str(t)))

    def on_add_task(self):
        title = self.t_title.get().strip()
        if not title:
            messagebox.showwarning("Missing title", "Please give the reminder a name.")
            return
        action = LABEL_TO_ACTION.get(self.t_action.get(), "notify")
        time_s = self.t_time.get().strip()
        try:
            datetime.datetime.strptime(time_s, "%H:%M")
        except ValueError:
            messagebox.showerror("Bad time", "Enter the time as HH:MM (e.g. 07:30).")
            return
        value = ""

        try:
            if self.t_repeat.get() == "Just once":
                date_s = self.t_date.get().strip()
                try:
                    datetime.date.fromisoformat(date_s)
                except ValueError:
                    messagebox.showerror("Bad date",
                                         "Enter the date as YYYY-MM-DD (e.g. 2026-08-01).")
                    return
                self.store.add_task(title, type="once", datetime_str=f"{date_s}T{time_s}",
                                    action=action, action_value=value)
            else:
                self.store.add_task(title, type="daily", time=time_s,
                                    action=action, action_value=value)
        except ValueError as e:
            messagebox.showerror("Could not add", str(e))
            return
        self.t_title.set("")
        self._refresh_tasks()
        self.v_status.set(f"Added reminder: {title}")

    def on_remove_task(self):
        if not self._alive(self.tree):
            return
        sel = self.tree.selection()
        if not sel:
            return
        for iid in sel:
            self.store.remove_task(iid)
        self._refresh_tasks()

    # --- actions -------------------------------------------------------
    def _collect(self):
        return apply_values_to_config(self.cfg, {
            "enabled": self.v_enabled.get(),
            "dynamic_theme": self.v_theme.get(),
            "wallpaper": self.v_wallpaper.get(),
            "ambient_sound": self.v_sound.get(),
            "tasks": self.v_tasks.get(),
            "tint": self.v_tint.get(),
            "volume": self.v_volume.get(),
            "music_volume": self.v_musicvol.get(),
            "pause_when_other_audio": self.v_duck.get(),
            "tick_interval": self.v_tick.get(),
            "weather_refresh": self.v_weatherrefresh.get(),
            "wallpaper_dynamic": self.v_wpdynamic.get(),
            "wallpaper_shift": self.v_wpshift.get(),
            "wallpaper_patterns": self.v_wppatterns.get(),
            "wallpaper_warmth": self.v_wpwarmth.get(),
            "p_work": self.v_pwork.get(),
            "p_break": self.v_pbreak.get(),
            "p_long": self.v_plong.get(),
            "p_cycles": self.v_pcycles.get(),
            "countdown_minutes": self.v_timermin.get(),
            "manual_weather": self.v_weather.get(),
            "manual_time": self.v_time.get(),
            "manual_theme_color": self.v_color.get(),
            "run_at_login": self.v_runlogin.get(),
            "active_profile": self.v_profile.get(),
            "accessibility_mode": self.v_access.get(),
            "appearance_mode": self.v_appearance.get(),
            "seasonal_themes": self.v_season.get(),
            "hemisphere": self.v_hemisphere.get(),
            "multi_monitor": self.v_multimon.get(),
            "smooth_transitions": self.v_smooth.get(),
            "city": self.v_city.get(),
        })

    def on_master_toggle(self):
        """
        Persist the master switch and push it to the running engine immediately.
        Turning it off silences ambience and stops further updates; it leaves
        the current wallpaper/accent in place.
        """
        on = self.v_enabled.get()
        _sync_feature_vars(
            on, (self.v_theme, self.v_wallpaper, self.v_sound, self.v_tasks))
        self._set_feature_controls_state(on)
        if on:
            # Enabling applies immediately (bypasses the redraw guard).
            self._apply_live("Enabled")
            return
        # Disabling: persist, silence sound now, and stop further updates.
        self._collect()
        config.save_config(self.cfg)
        try:
            sound.stop_sound()
        except Exception:
            pass
        if self.engine_thread and self.engine_thread.is_alive():
            self.engine_thread.wake()
            self.v_status.set("Disabled — engine idle (wallpaper/accent left as-is).")
        else:
            self.v_status.set("Disabled.")

    def _set_feature_controls_state(self, enabled):
        """Prevent child toggles from appearing active while master is off."""
        state = "normal" if enabled else "disabled"
        for checkbutton in self.feature_checks:
            try:
                checkbutton.configure(state=state)
            except tk.TclError:
                pass

    def on_sound_toggle(self):
        """Turn ambient sound on/off *now* — unticking stops it immediately."""
        self._collect()
        config.save_config(self.cfg)
        if not self.v_sound.get():
            try:
                sound.stop_sound()          # kill the looping clip right away
            except Exception:
                pass
            self.v_status.set("Ambient sound off.")
        else:
            self.v_status.set("Ambient sound on.")
        if self.engine_thread and self.engine_thread.is_alive():
            self.engine_thread.wake()

    def on_manage_sounds(self):
        """Show the exact filenames each weather needs, and open the folder."""
        names = "\n".join(f"   •  {label}:   {base}.wav"
                          for label, base in sound.SOUND_CONDITIONS)
        opened = sound.open_folder()
        messagebox.showinfo(
            "Sound files",
            "Drop .wav files into the sounds folder using these exact names:\n\n"
            f"{names}\n   •  Task chime:   chime.wav\n\n"
            "Want variety? Add numbered/suffixed variants — e.g.\n"
            "   rain.wav,  rain2.wav,  rain-heavy.wav\n"
            "One is chosen at random each play.\n\n"
            + ("Folder opened in your file manager."
               if opened else f"Folder: {os.path.abspath(sound.SOUNDS_DIR)}"))
        self.v_status.set("Sound folder: " + os.path.abspath(sound.SOUNDS_DIR))

    def on_toggle_autostart(self):
        ok = autostart.set_autostart(self.v_runlogin.get())
        if not ok:
            self.v_runlogin.set(autostart.is_autostart_enabled())
        self._collect()
        config.save_config(self.cfg)
        self.v_status.set("Run-at-login: "
                          + ("enabled" if self.v_runlogin.get() else "disabled"))

    def _poll_status_queue(self):
        try:
            while True:
                st = self.status_queue.get_nowait()
                if "_weather_card" in st:
                    self._update_weather_card(st["_weather_card"])
                    continue
                self.v_status.set(self._format_status(st))
                if "condition" in st:            # engine status also feeds the card
                    self._update_weather_card(st)
        except queue.Empty:
            pass
        self.root.after(500, self._poll_status_queue)

    @staticmethod
    def _format_status(st: dict) -> str:
        if "error" in st:
            return f"Error: {st['error']}"
        if not st.get("enabled", True):
            return "Disabled (master switch off)."
        parts = [f"{st.get('condition', '?')}",
                 st.get("phase") or ("night" if st.get("is_night") else "day"),
                 _fmt_temp(st.get("temperature")),
                 f"src={st.get('source')}"]
        if st.get("applied"):
            parts.append("| " + ", ".join(st["applied"]))
        if st.get("fired_tasks"):
            parts.append("| fired: " + ", ".join(st["fired_tasks"]))
        return "  ".join(parts)

    def on_close(self):
        if self.engine_thread:
            self.engine_thread.stop()
        self.root.destroy()


def main():
    root = tk.Tk()
    app = App(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
