"""
Simple stopwatch and countdown timer to sit alongside the Pomodoro timer.

Both are pure, tick-driven state machines (like ``pomodoro.Pomodoro``) so they
test without a display: call ``tick(seconds)`` on a cadence and read ``label()``.
"""


def format_time(seconds):
    """Seconds -> "M:SS" or "H:MM:SS"."""
    seconds = int(max(0, seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


class Stopwatch:
    """Counts up from zero. Start / pause / reset, with optional laps."""

    def __init__(self):
        self.elapsed = 0
        self.running = False
        self.laps = []

    def toggle(self):
        self.running = not self.running

    def reset(self):
        self.elapsed = 0
        self.running = False
        self.laps = []

    def lap(self):
        self.laps.append(self.elapsed)
        return self.elapsed

    def tick(self, seconds=1):
        if self.running:
            self.elapsed += seconds

    def label(self):
        return format_time(self.elapsed)


class CountdownTimer:
    """Counts down from a set number of minutes and fires once when it hits 0."""

    def __init__(self, minutes=10):
        self.set_minutes(minutes)

    def set_minutes(self, minutes):
        self.duration = max(1, int(minutes)) * 60
        self.remaining = self.duration
        self.running = False

    def toggle(self):
        # Starting a finished timer restarts it from the top.
        if self.remaining <= 0:
            self.remaining = self.duration
        self.running = not self.running

    def reset(self):
        self.remaining = self.duration
        self.running = False

    @property
    def finished(self):
        return self.remaining <= 0

    def tick(self, seconds=1):
        """Advance; returns "done" on the tick it reaches zero, else None."""
        if self.running and self.remaining > 0:
            self.remaining -= seconds
            if self.remaining <= 0:
                self.remaining = 0
                self.running = False
                return "done"
        return None

    def label(self):
        return format_time(self.remaining)
