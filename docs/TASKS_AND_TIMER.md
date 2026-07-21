# Tasks & Timers Guide

Timers, reminders, and music live in the **Focus & Tasks** window (click
**⏱ Focus & Tasks** in the header). Timers belong to the main app process: they
keep counting if you close this secondary window or switch tabs, but stop when
you quit Flow.

- [Timers](#timers)
- [Tasks & schedules](#tasks--schedules)
  - [Adding a reminder](#adding-a-reminder)
  - [When tasks fire](#when-tasks-fire)

---

## Timers

The **Timers** tab has a mode switch at the top — **🍅 Pomodoro**, **⏲ Timer**
(a plain countdown), and **⏱ Stopwatch**. They share the big display and
Start/Reset buttons; the third button and the settings below change per mode.
A running clock keeps going even while you view another mode.

### ⏲ Timer (countdown)

Set **Minutes**, press **Set**, then **Start**. It counts down and, at zero,
plays the chime and shows a notification. Starting a finished timer restarts it.
The most recently set duration is saved in `config.json`.

### ⏱ Stopwatch

**Start** counts up from zero; the third button becomes **Lap** and records the
current time into the laps list; **Reset** clears it.

### 🍅 Pomodoro

A classic work/break cycle to help you focus.

- **Start / Pause** — begins or pauses the countdown.
- **Skip** — jumps to the next phase (e.g. end a work block early).
- **Reset** — back to the start of a work block.

Set the durations under **Durations (minutes)** and click **Apply durations**:

| Setting | Meaning | Default |
|---|---|---|
| Work | Length of a focus block | 25 |
| Break | Short break after each work block | 5 |
| Long break | Longer break after several cycles | 15 |
| Cycles → long | Work blocks before a long break | 4 |

At each transition the app plays `chime.wav` and shows a system notification
("Work done — time for a break." / "Break over — back to work."). The completed
work-session count is shown under the timer.

---

## Tasks & schedules

The **To-Do & Schedules** tab shows your tasks and a form to add new ones. Tasks
are stored in `tasks.json` and run while **Task reminders** is selected on the
Dashboard. It works independently of **Enable everything**.

The form uses plain language — no need to know the internal fields.

### "Do" — what the reminder does

| Choice | Effect | Extra field |
|---|---|---|
| **Notify me** | Shows a system notification with the reminder's title | none |
| **Play a chime** | Plays `chime.wav` | none |

### "When" — every day, or a specific day

- **When** → choose **Every day** or **Just once**, and set the time (`at HH:MM`,
  24-hour).
- Choosing **Just once** reveals an **On** date (`YYYY-MM-DD`) with quick
  **Today / Tomorrow / +1 week** buttons. **+1 week** adds seven days to the
  date already in the field, so repeated clicks keep moving it forward.

### Adding a reminder

1. Enter a **Title**.
2. Pick what it should **Do**.
3. Set **When**: *Every day* + time, or *Just once* + date + time.
4. Click **Add reminder** — it appears in the list, showing **When** and
   **Does** in plain English (e.g. "Fri 01 Aug · 09:00", "Notification").

Select a row and **Remove selected** to delete it. Bad times/dates are rejected
with a clear hint.

> Example — remind yourself about a trip next week: **Do** = Notify me,
> **When** = Just once, click **+1 week**, and set `08:00`.

### When tasks fire

Tasks are evaluated on each engine step while the app or `--background` mode is
running and **Task reminders** is on. A daily task fires the first engine step
at or after its time, once per day. A one-off fires the first step at or after
its datetime, then is marked done. If the app isn't running at the exact minute,
the daily task still fires the next time it runs that day; an overdue one-off
fires the next time the engine runs.

Due reminders are claimed and saved before their action runs. This prevents the
GUI and a simultaneous `--background` process from firing the same reminder
twice.

*Notify me* and *Play a chime* do not change theme or wallpaper settings.
