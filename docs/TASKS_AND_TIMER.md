# Tasks & Timer Guide

Both live in the **Focus & Tasks** window (click **⏱ Focus & Tasks** in the
header). It runs independently — the timer keeps counting even if you close the
window or the main tabs.

- [Pomodoro timer](#pomodoro-timer)
- [Tasks & schedules](#tasks--schedules)
  - [Task types](#task-types)
  - [Actions](#actions)
  - [Adding a task](#adding-a-task)
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
are stored in `tasks.json` and run by the engine while it's started.

The form uses plain language — no need to know the internal fields.

### "Do" — what the reminder does

| Choice | Effect | Extra field |
|---|---|---|
| **Notify me** | Shows a system notification with the reminder's title | none |
| **Play a chime** | Plays `chime.wav` | none |
| **Change the weather** | Forces the manual weather look | a **Weather** dropdown (clear / cloud / rain / storm / night / auto) |
| **Change accent colour** | Forces the manual accent colour | a **Colour** as `red,green,blue` (0–255), e.g. `255,150,60` |

The extra field only appears when the action needs it, so there's no mystery
"Value" box. *Change the weather / accent* writes the override into
`config.json`, so it stays until you change it back (pick `auto`).

### "When" — every day, or a specific day

- **When** → choose **Every day** or **Just once**, and set the time (`at HH:MM`,
  24-hour).
- Choosing **Just once** reveals an **On** date (`YYYY-MM-DD`) with quick
  **Today / Tomorrow / +1 week** buttons — so scheduling something for a future
  day is one click.

### Adding a reminder

1. Enter a **Title**.
2. Pick what it should **Do** (fill the extra field if shown).
3. Set **When**: *Every day* + time, or *Just once* + date + time.
4. Click **Add reminder** — it appears in the list, showing **When** and
   **Does** in plain English (e.g. "Fri 01 Aug · 09:00", "Weather → rain").

Select a row and **Remove selected** to delete it. Bad times/dates are rejected
with a clear hint.

> Example — remind yourself about a trip next week: **Do** = Notify me,
> **When** = Just once, click **+1 week**, set `08:00`. Or a daily warm sunrise:
> **Do** = Change accent colour, `255,150,60`, **When** = Every day at `06:45`.

### When tasks fire

Tasks are evaluated on each engine step while the engine is **started** (or in
`--background` mode). A daily task fires the first time the engine steps at or
after its time, once per day. A one-off fires the first step at or after its
datetime, then is marked done. If the app isn't running at the exact minute,
the task still fires the next time it runs that day.

A **Change the weather / accent** task recolours the desktop **immediately**
when it fires (it drops the normal redraw interval and cross-fades to the new
look). *Notify me* and *Play a chime* don't change any colours — if you want the
background to change, pick one of the "Change …" actions. The engine must be
**Started** for tasks to run at all.
