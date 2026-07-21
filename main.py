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
import audiocheck


def run_once():
    cfg = config.load_config()
    store = tasks_mod.TaskStore()
    status = engine.tick(cfg, store)
    print("[main] tick status:", status)


def main():
    audiocheck.register_flow_process()
    args = sys.argv[1:]

    if "--background" in args:
        engine.run_forever()
        return

    if "--once" in args:
        run_once()
        return

    # Default: launch the GUI. Fall back to a single tick if no display.
    gui_presence = None
    try:
        import gui
        gui_presence = engine._new_gui_presence()
        gui_presence.register()
        engine._signal_engine_wake()
        gui.main()
    except Exception as e:
        print(f"[main] GUI unavailable ({e}); running a single tick instead.")
        if gui_presence is not None:
            gui_presence.unregister()
            engine._signal_engine_wake()
            gui_presence = None
        run_once()
    finally:
        if gui_presence is not None:
            gui_presence.unregister()
            engine._signal_engine_wake()


if __name__ == "__main__":
    main()
