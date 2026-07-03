"""
Settings GUI for the Environment Theme Controller.

Tabs:
  * General         — master switch, per-feature toggles, sliders, run-at-login
  * Manual Override — pick weather / time-of-day / theme colour by hand
  * Tasks           — create and manage tasks & schedules

The window only drives state; all behaviour lives in the engine + modules,
so the heavy logic stays testable without a display.
"""

import queue
import threading
import datetime

import tkinter as tk
from tkinter import ttk, messagebox

import config
import tasks as tasks_mod
import autostart
import engine
import sound
import pomodoro
import webwall


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
    cfg["tick_interval_seconds"] = max(5, int(values["tick_interval"]))
    cfg["weather_refresh_seconds"] = max(30, int(values["weather_refresh"]))
    cfg["wallpaper_dynamic"] = bool(values["wallpaper_dynamic"])
    cfg["wallpaper_shift_strength"] = int(round(values["wallpaper_shift"]))
    cfg["wallpaper_patterns"] = bool(values.get("wallpaper_patterns", True))
    cfg["wallpaper_warmth"] = bool(values.get("wallpaper_warmth", True))
    cfg["wallpaper_animated"] = bool(values.get("wallpaper_animated", False))
    cfg["wallpaper_animated_fps"] = max(1, int(round(values.get("wallpaper_animated_fps", 6))))
    backend = str(values.get("wallpaper_backend", "png")).lower()
    cfg["wallpaper_backend"] = backend if backend in config.WALLPAPER_BACKENDS else "png"
    cfg["pomodoro"] = {
        "work_min": max(1, int(values["p_work"])),
        "break_min": max(1, int(values["p_break"])),
        "long_break_min": max(1, int(values["p_long"])),
        "cycles_before_long": max(1, int(values["p_cycles"])),
    }
    cfg["manual_weather"] = values["manual_weather"]
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
    return cfg


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

        root.title("Environment Theme Controller")
        root.geometry("520x520")
        root.minsize(480, 480)

        self._build_vars()
        self._build_ui()
        self._poll_status_queue()
        self._timer_loop()

    # --- tk variables --------------------------------------------------
    def _build_vars(self):
        c = self.cfg
        f = c.get("features", {})
        self.v_enabled = tk.BooleanVar(value=c.get("enabled", True))
        self.v_theme = tk.BooleanVar(value=f.get("dynamic_theme", True))
        self.v_wallpaper = tk.BooleanVar(value=f.get("wallpaper", True))
        self.v_sound = tk.BooleanVar(value=f.get("ambient_sound", True))
        self.v_tasks = tk.BooleanVar(value=f.get("tasks", True))
        self.v_tint = tk.DoubleVar(value=float(c.get("weather_tint_strength", 40)))
        self.v_volume = tk.DoubleVar(value=float(c.get("sound_volume", 25)))
        self.v_tick = tk.IntVar(value=int(c.get("tick_interval_seconds", 30)))
        self.v_weatherrefresh = tk.IntVar(value=int(c.get("weather_refresh_seconds", 600)))
        self.v_wpdynamic = tk.BooleanVar(value=c.get("wallpaper_dynamic", True))
        self.v_wpshift = tk.DoubleVar(value=float(c.get("wallpaper_shift_strength", 35)))
        self.v_wppatterns = tk.BooleanVar(value=c.get("wallpaper_patterns", True))
        self.v_wpwarmth = tk.BooleanVar(value=c.get("wallpaper_warmth", True))
        self.v_wpanimated = tk.BooleanVar(value=c.get("wallpaper_animated", False))
        self.v_wpfps = tk.DoubleVar(value=float(c.get("wallpaper_animated_fps", 6)))
        self.v_wpbackend = tk.StringVar(value=c.get("wallpaper_backend", "png"))
        self.v_weather = tk.StringVar(value=c.get("manual_weather", "auto"))
        self.v_time = tk.StringVar(value=c.get("manual_time", "auto"))
        mc = c.get("manual_theme_color")
        self.v_color = tk.StringVar(value=("auto" if not mc else ",".join(map(str, mc))))
        self.v_runlogin = tk.BooleanVar(value=autostart.is_autostart_enabled())
        self.v_status = tk.StringVar(value="Idle. Press Start or Apply Now.")

        # Pomodoro durations + live timer state.
        p = c.get("pomodoro", {})
        self.v_pwork = tk.IntVar(value=int(p.get("work_min", 25)))
        self.v_pbreak = tk.IntVar(value=int(p.get("break_min", 5)))
        self.v_plong = tk.IntVar(value=int(p.get("long_break_min", 15)))
        self.v_pcycles = tk.IntVar(value=int(p.get("cycles_before_long", 4)))
        self.v_timer = tk.StringVar(value="Idle")
        self.pomo = pomodoro.Pomodoro(
            self.v_pwork.get(), self.v_pbreak.get(),
            self.v_plong.get(), self.v_pcycles.get())

    # --- UI ------------------------------------------------------------
    def _build_ui(self):
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill="x")
        ttk.Button(top, text="Apply Now", command=self.on_apply_now).pack(side="left")
        self.btn_engine = ttk.Button(top, text="Start", command=self.on_toggle_engine)
        self.btn_engine.pack(side="left", padx=6)
        ttk.Button(top, text="Save", command=self.on_save).pack(side="right")

        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=8, pady=4)
        nb.add(self._tab_general(nb), text="General")
        nb.add(self._tab_override(nb), text="Manual Override")
        nb.add(self._tab_tasks(nb), text="Tasks")
        nb.add(self._tab_timer(nb), text="Timer")

        status = ttk.Label(self.root, textvariable=self.v_status,
                           relief="sunken", anchor="w", padding=4)
        status.pack(fill="x", side="bottom")

    def _tab_general(self, parent):
        fr = ttk.Frame(parent, padding=12)
        ttk.Checkbutton(fr, text="Enable application (master switch)",
                        variable=self.v_enabled).pack(anchor="w", pady=(0, 8))

        feats = ttk.LabelFrame(fr, text="Features", padding=8)
        feats.pack(fill="x")
        ttk.Checkbutton(feats, text="Dynamic theme (accent colour)",
                        variable=self.v_theme).pack(anchor="w")
        ttk.Checkbutton(feats, text="Weather wallpaper",
                        variable=self.v_wallpaper).pack(anchor="w")
        ttk.Checkbutton(feats, text="Ambient sound",
                        variable=self.v_sound).pack(anchor="w")
        ttk.Checkbutton(feats, text="Tasks & schedules",
                        variable=self.v_tasks).pack(anchor="w")

        self._slider(fr, "Weather tint strength", self.v_tint)
        self._slider(fr, "Sound volume", self.v_volume)

        ttk.Checkbutton(fr, text="Dynamic wallpaper (subtle colour shift)",
                        variable=self.v_wpdynamic).pack(anchor="w", pady=(6, 0))
        self._slider(fr, "Wallpaper shift strength", self.v_wpshift)
        ttk.Checkbutton(fr, text="Weather patterns (rain, sun, clouds, stars)",
                        variable=self.v_wppatterns).pack(anchor="w", pady=(6, 0))
        ttk.Checkbutton(fr, text="Warm palette when it's cold outside",
                        variable=self.v_wpwarmth).pack(anchor="w")
        ttk.Checkbutton(fr, text="Animated wallpaper (smooth motion — uses more "
                                 "power, auto-pauses under load)",
                        variable=self.v_wpanimated).pack(anchor="w", pady=(6, 0))
        self._slider(fr, "Animation frame rate", self.v_wpfps,
                     from_=1, to=30, unit="fps")

        back = ttk.LabelFrame(fr, text="Wallpaper backend", padding=8)
        back.pack(fill="x", pady=4)
        row = ttk.Frame(back); row.pack(fill="x")
        ttk.Label(row, text="Render with:", width=12).pack(side="left")
        ttk.Combobox(row, textvariable=self.v_wpbackend, state="readonly", width=8,
                     values=config.WALLPAPER_BACKENDS).pack(side="left")
        ttk.Button(row, text="Open web wallpaper folder…",
                   command=self.on_open_webwall).pack(side="right")
        ttk.Label(back, wraplength=440, foreground="#666",
                  text="png = built-in (static or in-app animation). "
                       "web = maintain an HTML/canvas wallpaper for an external "
                       "engine (ScreenPlay, Lively, or Plash) to render with "
                       "smooth GPU animation — point it at the index.html in the "
                       "folder above.").pack(anchor="w", pady=(6, 0))

        ivfr = ttk.Frame(fr)
        ivfr.pack(fill="x", pady=6)
        ttk.Label(ivfr, text="Tick (s):").pack(side="left")
        ttk.Spinbox(ivfr, from_=5, to=3600, textvariable=self.v_tick,
                    width=6).pack(side="left", padx=(2, 12))
        ttk.Label(ivfr, text="Weather refresh (s):").pack(side="left")
        ttk.Spinbox(ivfr, from_=30, to=7200, textvariable=self.v_weatherrefresh,
                    width=7).pack(side="left", padx=2)

        ttk.Checkbutton(fr, text="Run automatically at login",
                        variable=self.v_runlogin,
                        command=self.on_toggle_autostart).pack(anchor="w", pady=8)
        return fr

    def _slider(self, parent, label, var, from_=0, to=100, unit="%"):
        fr = ttk.LabelFrame(parent, text=label, padding=6)
        fr.pack(fill="x", pady=4)
        fmt = (lambda: f"{int(var.get())} {unit}".rstrip())
        val = ttk.Label(fr, text=fmt(), width=6)
        val.pack(side="right")
        var.trace_add("write", lambda *_: val.config(text=fmt()))
        ttk.Scale(fr, from_=from_, to=to, orient="horizontal",
                  variable=var).pack(fill="x", side="left", expand=True)

    def _tab_override(self, parent):
        fr = ttk.Frame(parent, padding=12)
        row = ttk.Frame(fr); row.pack(fill="x", pady=6)
        ttk.Label(row, text="Weather:", width=12).pack(side="left")
        ttk.Combobox(row, textvariable=self.v_weather, state="readonly",
                     values=config.WEATHER_CHOICES).pack(side="left")

        row2 = ttk.Frame(fr); row2.pack(fill="x", pady=6)
        ttk.Label(row2, text="Time of day:", width=12).pack(side="left")
        ttk.Combobox(row2, textvariable=self.v_time, state="readonly",
                     values=config.TIME_CHOICES).pack(side="left")

        row3 = ttk.Frame(fr); row3.pack(fill="x", pady=6)
        ttk.Label(row3, text="Theme colour:", width=12).pack(side="left")
        ttk.Entry(row3, textvariable=self.v_color, width=16).pack(side="left")
        ttk.Label(row3, text='"auto" or "r,g,b" (0-255)').pack(side="left", padx=6)

        ttk.Label(fr, text="Overrides take effect on the next Apply Now / refresh.",
                  foreground="#666").pack(anchor="w", pady=10)
        return fr

    def _tab_tasks(self, parent):
        fr = ttk.Frame(parent, padding=10)

        cols = ("title", "when", "action", "enabled")
        self.tree = ttk.Treeview(fr, columns=cols, show="headings", height=6)
        for c, w in zip(cols, (160, 120, 110, 60)):
            self.tree.heading(c, text=c.title())
            self.tree.column(c, width=w)
        self.tree.pack(fill="both", expand=True)
        self._refresh_tasks()

        form = ttk.LabelFrame(fr, text="New task", padding=8)
        form.pack(fill="x", pady=8)

        self.t_title = tk.StringVar()
        self.t_type = tk.StringVar(value="daily")
        self.t_when = tk.StringVar(value="08:00")
        self.t_action = tk.StringVar(value="notify")
        self.t_value = tk.StringVar()

        r1 = ttk.Frame(form); r1.pack(fill="x", pady=2)
        ttk.Label(r1, text="Title:", width=7).pack(side="left")
        ttk.Entry(r1, textvariable=self.t_title).pack(side="left", fill="x", expand=True)

        r2 = ttk.Frame(form); r2.pack(fill="x", pady=2)
        ttk.Label(r2, text="Type:", width=7).pack(side="left")
        ttk.Combobox(r2, textvariable=self.t_type, state="readonly", width=8,
                     values=tasks_mod.TASK_TYPES).pack(side="left")
        ttk.Label(r2, text="When:").pack(side="left", padx=(10, 2))
        ttk.Entry(r2, textvariable=self.t_when, width=18).pack(side="left")
        ttk.Label(r2, text="HH:MM or ISO datetime").pack(side="left", padx=4)

        r3 = ttk.Frame(form); r3.pack(fill="x", pady=2)
        ttk.Label(r3, text="Action:", width=7).pack(side="left")
        ttk.Combobox(r3, textvariable=self.t_action, state="readonly", width=10,
                     values=tasks_mod.ACTIONS).pack(side="left")
        ttk.Label(r3, text="Value:").pack(side="left", padx=(10, 2))
        ttk.Entry(r3, textvariable=self.t_value, width=16).pack(side="left")

        btns = ttk.Frame(fr); btns.pack(fill="x")
        ttk.Button(btns, text="Add task", command=self.on_add_task).pack(side="left")
        ttk.Button(btns, text="Remove selected",
                   command=self.on_remove_task).pack(side="left", padx=6)
        return fr

    def _tab_timer(self, parent):
        fr = ttk.Frame(parent, padding=12)

        ttk.Label(fr, textvariable=self.v_timer,
                  font=("Helvetica", 28)).pack(pady=(10, 4))
        self.lbl_cycles = ttk.Label(fr, text="Completed: 0", foreground="#666")
        self.lbl_cycles.pack()

        ctl = ttk.Frame(fr); ctl.pack(pady=12)
        self.btn_timer = ttk.Button(ctl, text="Start", width=10,
                                    command=self.on_timer_toggle)
        self.btn_timer.pack(side="left", padx=4)
        ttk.Button(ctl, text="Skip", width=8,
                   command=self.on_timer_skip).pack(side="left", padx=4)
        ttk.Button(ctl, text="Reset", width=8,
                   command=self.on_timer_reset).pack(side="left", padx=4)

        durs = ttk.LabelFrame(fr, text="Durations (minutes)", padding=8)
        durs.pack(fill="x", pady=10)
        for label, var, hi in [("Work", self.v_pwork, 120),
                               ("Break", self.v_pbreak, 60),
                               ("Long break", self.v_plong, 120),
                               ("Cycles → long", self.v_pcycles, 12)]:
            row = ttk.Frame(durs); row.pack(fill="x", pady=2)
            ttk.Label(row, text=label, width=14).pack(side="left")
            ttk.Spinbox(row, from_=1, to=hi, textvariable=var, width=6).pack(side="left")
        ttk.Button(durs, text="Apply durations",
                   command=self.on_timer_apply_durations).pack(anchor="e", pady=(6, 0))
        return fr

    # --- timer ---------------------------------------------------------
    def _update_timer_label(self):
        self.v_timer.set(self.pomo.label())
        if hasattr(self, "lbl_cycles"):
            self.lbl_cycles.config(text=f"Completed work sessions: {self.pomo.completed_work}")
        if hasattr(self, "btn_timer"):
            self.btn_timer.config(text="Pause" if self.pomo.running else "Start")

    def _timer_loop(self):
        ev = self.pomo.tick(1) if self.pomo.running else None
        if ev:
            event, nxt = ev
            msg = ("Work done — time for a break."
                   if event == "work_complete" else "Break over — back to work.")
            try:
                sound.play_chime()
            except Exception:
                pass
            engine.notify("Pomodoro", msg)
            self.v_status.set(f"Timer: {msg}")
        self._update_timer_label()
        self.root.after(1000, self._timer_loop)

    def on_timer_toggle(self):
        self.pomo.toggle()
        self._update_timer_label()

    def on_timer_skip(self):
        self.pomo.skip()
        self._update_timer_label()

    def on_timer_reset(self):
        self.pomo.reset()
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
        for item in self.tree.get_children():
            self.tree.delete(item)
        for t in self.store.list_tasks():
            when = t.get("time") if t.get("type") == "daily" else t.get("datetime")
            self.tree.insert("", "end", iid=t["id"], values=(
                t.get("title", ""), when, t.get("action", ""),
                "yes" if t.get("enabled", True) else "no",
            ))

    def on_add_task(self):
        title = self.t_title.get().strip()
        if not title:
            messagebox.showwarning("Missing title", "Please enter a task title.")
            return
        ttype = self.t_type.get()
        when = self.t_when.get().strip()
        try:
            if ttype == "daily":
                datetime.datetime.strptime(when, "%H:%M")
                self.store.add_task(title, type="daily", time=when,
                                    action=self.t_action.get(),
                                    action_value=self.t_value.get().strip())
            else:
                datetime.datetime.fromisoformat(when)  # validate
                self.store.add_task(title, type="once", datetime_str=when,
                                    action=self.t_action.get(),
                                    action_value=self.t_value.get().strip())
        except ValueError:
            messagebox.showerror(
                "Bad time",
                "Daily: use HH:MM (e.g. 07:30).\nOnce: use ISO (e.g. 2026-06-28T09:00).")
            return
        self.t_title.set("")
        self.t_value.set("")
        self._refresh_tasks()

    def on_remove_task(self):
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
            "tick_interval": self.v_tick.get(),
            "weather_refresh": self.v_weatherrefresh.get(),
            "wallpaper_dynamic": self.v_wpdynamic.get(),
            "wallpaper_shift": self.v_wpshift.get(),
            "wallpaper_patterns": self.v_wppatterns.get(),
            "wallpaper_warmth": self.v_wpwarmth.get(),
            "wallpaper_animated": self.v_wpanimated.get(),
            "wallpaper_animated_fps": self.v_wpfps.get(),
            "wallpaper_backend": self.v_wpbackend.get(),
            "p_work": self.v_pwork.get(),
            "p_break": self.v_pbreak.get(),
            "p_long": self.v_plong.get(),
            "p_cycles": self.v_pcycles.get(),
            "manual_weather": self.v_weather.get(),
            "manual_time": self.v_time.get(),
            "manual_theme_color": self.v_color.get(),
            "run_at_login": self.v_runlogin.get(),
        })

    def on_save(self):
        self._collect()
        if config.save_config(self.cfg):
            self.v_status.set("Settings saved.")
        else:
            messagebox.showerror("Error", "Could not write config.json.")

    def on_open_webwall(self):
        """Create the HTML wallpaper assets and reveal them in the file manager."""
        webwall.ensure_assets()
        if webwall.open_folder():
            self.v_status.set(f"Web wallpaper ready: {webwall.html_path()}")
        else:
            messagebox.showinfo(
                "Web wallpaper",
                "Point your wallpaper engine (ScreenPlay / Lively / Plash) at:\n\n"
                f"{webwall.html_path()}")

    def on_toggle_autostart(self):
        ok = autostart.set_autostart(self.v_runlogin.get())
        if not ok:
            self.v_runlogin.set(autostart.is_autostart_enabled())
        self.v_status.set("Run-at-login: "
                          + ("enabled" if self.v_runlogin.get() else "disabled"))

    def on_apply_now(self):
        self._collect()
        config.save_config(self.cfg)
        self.v_status.set("Applying…")
        threading.Thread(target=self._apply_once, daemon=True).start()

    def _apply_once(self):
        try:
            st = engine.tick(self.cfg, self.store)
            self.status_queue.put(st)
        except Exception as e:
            self.status_queue.put({"error": str(e)})

    def on_toggle_engine(self):
        if self.engine_thread and self.engine_thread.is_alive():
            self.engine_thread.stop()
            self.engine_thread = None
            self.btn_engine.config(text="Start")
            self.v_status.set("Engine stopped.")
        else:
            self._collect()
            config.save_config(self.cfg)
            self.engine_thread = engine.EngineThread(
                on_status=lambda st: self.status_queue.put(st))
            self.engine_thread.start()
            self.btn_engine.config(text="Stop")
            self.v_status.set("Engine running…")

    def _poll_status_queue(self):
        try:
            while True:
                st = self.status_queue.get_nowait()
                self.v_status.set(self._format_status(st))
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
                 "night" if st.get("is_night") else "day",
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
