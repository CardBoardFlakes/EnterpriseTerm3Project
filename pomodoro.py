"""
A small Pomodoro productivity timer.

Pure state machine — no GUI, no threads — so it is trivially testable and
costs nothing to run (the GUI drives it one ``tick`` per second via
``root.after``). Cycles: work -> break -> work -> ... and every
``cycles_before_long`` work sessions the break becomes a long break.
"""

WORK = "work"
BREAK = "break"
LONG_BREAK = "long_break"
IDLE = "idle"


class Pomodoro:
    def __init__(self, work_min=25, break_min=5, long_break_min=15,
                 cycles_before_long=4):
        self.configure(work_min, break_min, long_break_min, cycles_before_long)
        self.phase = IDLE
        self.remaining = 0          # seconds left in the current phase
        self.running = False
        self.completed_work = 0     # finished work sessions this run

    # --- configuration -------------------------------------------------
    def configure(self, work_min, break_min, long_break_min, cycles_before_long):
        self.work_sec = int(work_min * 60)
        self.break_sec = int(break_min * 60)
        self.long_break_sec = int(long_break_min * 60)
        self.cycles_before_long = max(1, int(cycles_before_long))

    def _duration(self, phase):
        return {
            WORK: self.work_sec,
            BREAK: self.break_sec,
            LONG_BREAK: self.long_break_sec,
        }.get(phase, 0)

    def _enter(self, phase):
        self.phase = phase
        self.remaining = self._duration(phase)

    # --- controls ------------------------------------------------------
    def start(self):
        """Start from idle, or resume if paused."""
        if self.phase == IDLE:
            self._enter(WORK)
        self.running = True

    def pause(self):
        self.running = False

    def toggle(self):
        if self.running:
            self.pause()
        else:
            self.start()

    def reset(self):
        self.phase = IDLE
        self.remaining = 0
        self.running = False
        self.completed_work = 0

    def skip(self):
        """Immediately finish the current phase (returns the same event tick would)."""
        if self.phase == IDLE:
            self.start()
            return None
        return self._advance()

    # --- time ----------------------------------------------------------
    def tick(self, seconds=1):
        """
        Advance the clock. Returns ``(event, next_phase)`` when a phase ends
        (event is "work_complete" or "break_complete"), else ``None``.
        """
        if not self.running or self.phase == IDLE:
            return None
        self.remaining -= seconds
        if self.remaining <= 0:
            return self._advance()
        return None

    def _advance(self):
        if self.phase == WORK:
            self.completed_work += 1
            nxt = (LONG_BREAK
                   if self.completed_work % self.cycles_before_long == 0
                   else BREAK)
            event = "work_complete"
        else:
            nxt = WORK
            event = "break_complete"
        self._enter(nxt)
        return (event, nxt)

    # --- display -------------------------------------------------------
    def mmss(self):
        s = max(0, self.remaining)
        return f"{s // 60:02d}:{s % 60:02d}"

    def label(self):
        if self.phase == IDLE:
            return "Idle"
        names = {WORK: "Work", BREAK: "Break", LONG_BREAK: "Long break"}
        state = "" if self.running else " (paused)"
        return f"{names[self.phase]} {self.mmss()}{state}"
