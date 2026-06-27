import tkinter as tk
from tkinter import ttk, messagebox
import json
import os

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "enable_dynamic_theme": True,
    "enable_weather_sound": True,
    "weather_tint_strength": 40,   # percent, 0-100
}


def load_config() -> dict:
    cfg = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                cfg.update(json.load(f))
        except (json.JSONDecodeError, OSError) as e:
            print(f"[gui] Could not load config: {e}")
    return cfg


def save_config(cfg: dict) -> bool:
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f, indent=2)
        return True
    except OSError as e:
        print(f"[gui] Could not save config: {e}")
        return False


def main():
    cfg = load_config()

    root = tk.Tk()
    root.title("Environment Theme Controller")
    root.geometry("370x260")
    root.resizable(False, False)

    enable_theme_var = tk.BooleanVar(value=cfg["enable_dynamic_theme"])
    enable_sound_var = tk.BooleanVar(value=cfg["enable_weather_sound"])
    # Use DoubleVar so the Scale widget (which returns floats) works without
    # type errors; we round to int on save.
    tint_var = tk.DoubleVar(value=float(cfg["weather_tint_strength"]))

    pad = {"padx": 12, "pady": 6}

    ttk.Checkbutton(
        root,
        text="Enable dynamic taskbar theme",
        variable=enable_theme_var,
    ).pack(anchor="w", **pad)

    ttk.Checkbutton(
        root,
        text="Enable weather ambient sounds",
        variable=enable_sound_var,
    ).pack(anchor="w", padx=12, pady=2)

    # --- Tint strength slider ---
    tint_frame = ttk.LabelFrame(root, text="Weather tint strength", padding=8)
    tint_frame.pack(fill="x", padx=12, pady=10)

    tint_label = ttk.Label(tint_frame, text=f"{int(tint_var.get())} %", width=5)
    tint_label.pack(side="right")

    def on_tint_change(*_):
        tint_label.config(text=f"{int(tint_var.get())} %")

    tint_var.trace_add("write", on_tint_change)

    ttk.Scale(
        tint_frame,
        from_=0, to=100,
        orient="horizontal",
        variable=tint_var,
    ).pack(fill="x", side="left", expand=True)

    # --- Save button ---
    def on_save():
        cfg["enable_dynamic_theme"]  = enable_theme_var.get()
        cfg["enable_weather_sound"]  = enable_sound_var.get()
        cfg["weather_tint_strength"] = int(round(tint_var.get()))   # FIX: round float → int

        if save_config(cfg):
            messagebox.showinfo("Saved", "Settings saved successfully.")
        else:
            messagebox.showerror("Error", "Could not write config.json.\nCheck file permissions.")

    btn_frame = ttk.Frame(root)
    btn_frame.pack(fill="x", padx=12, pady=8)

    ttk.Button(btn_frame, text="Save", command=on_save, width=12).pack(side="right")

    root.mainloop()


if __name__ == "__main__":
    main()