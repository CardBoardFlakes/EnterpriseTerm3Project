"""
User tasks & schedules.

A task either repeats daily at a wall-clock time ("daily") or fires once at
a specific datetime ("once"). When due, the engine performs the task's
action: pop up a notification or play a chime.
"""

import json
import os
import datetime

# Absolute path next to this module, so tasks are read/written from the same
# place regardless of the launch directory (see config.CONFIG_FILE).
TASKS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tasks.json")

TASK_TYPES = ["daily", "once"]
ACTIONS = ["notify", "chime"]


class TaskStore:
    def __init__(self, path: str = TASKS_FILE):
        self.path = path
        self.tasks = []
        self.load()

    # --- persistence ---------------------------------------------------
    def load(self):
        self.tasks = []
        if os.path.exists(self.path):
            try:
                with open(self.path, "r") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    self.tasks = data
            except (json.JSONDecodeError, OSError) as e:
                print(f"[tasks] Could not load {self.path}: {e}")
        return self.tasks

    def save(self) -> bool:
        try:
            with open(self.path, "w") as f:
                json.dump(self.tasks, f, indent=2)
            return True
        except OSError as e:
            print(f"[tasks] Could not save {self.path}: {e}")
            return False

    # --- CRUD ----------------------------------------------------------
    def _next_id(self) -> str:
        n = 0
        for t in self.tasks:
            tid = str(t.get("id", ""))
            if tid.startswith("t") and tid[1:].isdigit():
                n = max(n, int(tid[1:]))
        return f"t{n + 1}"

    def add_task(self, title, type="daily", time="08:00", datetime_str=None,
                 action="notify", action_value="", enabled=True) -> dict:
        if type not in TASK_TYPES:
            raise ValueError(f"bad task type: {type}")
        if action not in ACTIONS:
            raise ValueError(f"bad action: {action}")
        task = {
            "id": self._next_id(),
            "title": title,
            "type": type,
            "time": time,                 # "HH:MM" for daily
            "datetime": datetime_str,     # ISO string for once
            "action": action,
            "action_value": action_value,
            "enabled": enabled,
            "last_fired": None,
        }
        self.tasks.append(task)
        self.save()
        return task

    def remove_task(self, task_id) -> bool:
        before = len(self.tasks)
        self.tasks = [t for t in self.tasks if t.get("id") != task_id]
        changed = len(self.tasks) != before
        if changed:
            self.save()
        return changed

    def update_task(self, task_id, **fields) -> bool:
        for t in self.tasks:
            if t.get("id") == task_id:
                t.update(fields)
                self.save()
                return True
        return False

    def list_tasks(self):
        return list(self.tasks)

    # --- scheduling ----------------------------------------------------
    def due_tasks(self, now: datetime.datetime = None):
        """Return enabled tasks that are due at *now* and not yet fired."""
        now = now or datetime.datetime.now()
        due = []
        for t in self.tasks:
            if not t.get("enabled", True):
                continue
            if self._is_due(t, now):
                due.append(t)
        return due

    @staticmethod
    def _is_due(task, now) -> bool:
        ttype = task.get("type", "daily")
        if ttype == "daily":
            hh_mm = task.get("time") or "00:00"
            try:
                hh, mm = (int(x) for x in hh_mm.split(":"))
            except ValueError:
                return False
            scheduled = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if now < scheduled:
                return False
            # Fire at most once per calendar day.
            last = task.get("last_fired")
            return last != now.date().isoformat()
        elif ttype == "once":
            dt = task.get("datetime")
            if not dt:
                return False
            try:
                when = datetime.datetime.fromisoformat(dt)
            except ValueError:
                return False
            if now < when:
                return False
            return not task.get("last_fired")
        return False

    def mark_fired(self, task, now: datetime.datetime = None):
        now = now or datetime.datetime.now()
        if task.get("type") == "daily":
            task["last_fired"] = now.date().isoformat()
        else:
            task["last_fired"] = now.isoformat()
        self.save()
