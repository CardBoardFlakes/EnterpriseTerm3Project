"""
Flow — entry point.

Usage:
  python main.py              Launch the settings GUI (default).
  python main.py --background Run the headless engine loop (used at login).
  python main.py --once       Run a single engine tick and exit.
"""

import sys

import config
import tasks as tasks_mod
import engine


def run_once():
    cfg = config.load_config()
    store = tasks_mod.TaskStore()
    status = engine.tick(cfg, store)
    print("[main] tick status:", status)


def main():
    args = sys.argv[1:]

    if "--background" in args:
        engine.run_forever()
        return

    if "--once" in args:
        run_once()
        return

    # Default: launch the GUI. Fall back to a single tick if no display.
    try:
        import gui
        gui.main()
    except Exception as e:
        print(f"[main] GUI unavailable ({e}); running a single tick instead.")
        run_once()


if __name__ == "__main__":
    main()
