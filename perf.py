"""
Performance governor for the animated wallpaper.

Animated wallpaper regenerates and re-applies the desktop image many times a
second, which is deliberately more expensive than the static path. This module
watches how hard that is hitting the machine and adapts:

  * the *fast* signal is our own frame cost — an EMA of how long each
    build+apply took (this already folds in an overloaded CPU, since a busy
    machine makes our own frames slower);
  * the *secondary* signal is the system load average per core.

When either blows its budget the governor throttles the effective frame rate;
if things stay bad it *suspends* animation entirely (the caller drops back to a
single static frame) and probes periodically, resuming automatically once the
machine recovers. Every decision is a pure function of the samples handed in —
no clock, no threads — so it is deterministic and unit-testable.
"""

import os


def system_load(cpu_count=None):
    """
    1-minute load average normalised per CPU core (≈ fraction busy), or
    ``None`` where the OS has no load average (e.g. Windows). ``None`` simply
    means "fall back to the frame-cost signal only".
    """
    try:
        one_min = os.getloadavg()[0]
    except (OSError, AttributeError):
        return None
    n = cpu_count or os.cpu_count() or 1
    return one_min / n


class AdaptiveGovernor:
    """
    Decide, frame by frame, whether to render the next animation frame and how
    long to sleep afterwards.

    Feed :meth:`observe` one sample per loop iteration (pass
    ``render_seconds=0`` on iterations where you didn't actually render, e.g.
    while suspended). Then read :attr:`render`, :attr:`sleep` and
    :attr:`suspended`.
    """

    def __init__(self, target_fps=6, load_ceiling=0.85, min_fps=1,
                 patience=3, recover=2, probe_seconds=5.0, ema=0.4,
                 budget_slack=1.5):
        self.min_fps = max(1, int(min_fps))
        self.patience = max(1, int(patience))     # bad samples before suspend
        self.recover = max(1, int(recover))       # good samples before easing up
        self.probe_seconds = float(probe_seconds)
        self.alpha = float(ema)
        self.budget_slack = float(budget_slack)

        self.configure(target_fps, load_ceiling)
        self._ema = None
        self.eff_fps = float(self.target_fps)
        self.suspended = False
        self._bad = 0
        self._good = 0
        self.render = True
        self.sleep = 1.0 / self.target_fps

    def configure(self, target_fps=None, load_ceiling=None):
        """Update targets live (the GUI can change these between frames)."""
        if target_fps:
            self.target_fps = max(1, int(target_fps))
        if load_ceiling is not None:
            self.load_ceiling = max(0.1, float(load_ceiling))

    @property
    def budget(self):
        """Seconds a single frame is allowed at the target frame rate."""
        return 1.0 / self.target_fps

    def _overloaded(self, load):
        if self._ema is not None and self._ema > self.budget * self.budget_slack:
            return True
        if load is not None and load > self.load_ceiling:
            return True
        return False

    def observe(self, render_seconds, load):
        """Record one sample and recompute the plan for the next frame."""
        if render_seconds and render_seconds > 0:
            self._ema = (render_seconds if self._ema is None
                         else self.alpha * render_seconds
                         + (1 - self.alpha) * self._ema)

        over = self._overloaded(load)

        # --- currently suspended: probe until the machine recovers --------
        if self.suspended:
            if over:
                self._good = 0
                self.render = False
                self.sleep = self.probe_seconds
                return
            self._good += 1
            if self._good < self.recover:
                self.render = False
                self.sleep = self.probe_seconds
                return
            # Recovered: resume rendering immediately, ramping back up gently.
            self.suspended = False
            self._bad = self._good = 0
            self._ema = None                # forget the stale bad frame
            self.eff_fps = float(self.min_fps)
            self.render = True
            self.sleep = 1.0 / self.eff_fps
            return

        # --- running: throttle down on strain, ease up when calm ----------
        if over:
            self._bad += 1
            self._good = 0
            self.eff_fps = max(self.min_fps, self.eff_fps / 2.0)
            if self._bad >= self.patience:
                self.suspended = True
                self.render = False
                self.sleep = self.probe_seconds
                return
        else:
            self._good += 1
            self._bad = 0
            if self.eff_fps < self.target_fps and self._good >= self.recover:
                self.eff_fps = min(self.target_fps, self.eff_fps * 2.0)
                self._good = 0

        self.render = True
        self.sleep = 1.0 / max(self.min_fps, self.eff_fps)
