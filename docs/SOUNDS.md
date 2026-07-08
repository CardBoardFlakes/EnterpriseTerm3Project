# Sound Guide

The app can play a subtle ambient soundscape that matches the weather and time
of day. It's optional — if `pygame` isn't installed, sound is silently skipped.

- [Turning it on](#turning-it-on)
- [The sound files](#the-sound-files)
- [Using your own sounds](#using-your-own-sounds)
- [Variants (multiple clips per condition)](#variants-multiple-clips-per-condition)
- [Loop vs. random playback](#loop-vs-random-playback)
- [Placeholder sounds](#placeholder-sounds)

---

## Turning it on

1. On the **Dashboard** tab, tick **Ambient sound**.
2. On the **Appearance** tab, set the **Ambient volume** (subtle by default).
3. Press **▶ Start**.

---

## The sound files

Sounds live in the `sounds/` folder and are named by condition, so replacing
them is obvious. The **Appearance → Sound → Sound files…** button lists these
names and opens the folder for you.

| When it plays | Filename |
|---|---|
| Clear sky, daytime | `clearday.wav` |
| Clear sky, night (and the `night` condition) | `clearnight.wav` |
| Cloudy (and the fallback) | `cloud.wav` |
| Rain | `rain.wav` |
| Storm | `storm.wav` |
| A task/timer chime fires | `chime.wav` |

Files must be **`.wav`**. (Renaming an `.mp3` won't work — convert it to WAV
first.)

---

## Using your own sounds

Just drop your own `.wav` files into `sounds/` using the names above,
overwriting the placeholders. No restart or config change needed — the engine
picks up the new file the next time that sound plays.

Tips:
- Loopable clips (a few seconds to a minute, seamless) work best for **loop**
  mode.
- The placeholder synth never overwrites a file that already exists, so your
  custom audio is safe.

---

## Variants (multiple clips per condition)

To keep the ambience from getting repetitive, add **variants** — extra files
whose names start with the base name followed by a digit, `-`, `_`, or space:

```
sounds/rain.wav
sounds/rain2.wav
sounds/rain-heavy.wav
sounds/rain_forest.wav
```

All four count as "rain", and **one is chosen at random** each time rain
ambience starts. This works for every condition (`clearday2.wav`,
`storm-distant.wav`, etc.).

> Naming is prefix-based but bounded: `clearday` variants never accidentally
> match `clearnight`, because the character after the base must be a
> digit/`-`/`_`/space.

---

## Loop vs. random playback

Choose the **Playback** style on the Appearance → Sound card:

- **loop** — the chosen clip plays continuously in the background. When the
  weather changes, it switches (and picks a fresh random variant).
- **random** — no continuous loop. A single clip plays now and then — roughly
  every **N minutes** (set by the interval spinbox), with a bit of jitter so it
  never feels metronomic. Great for occasional birdsong / distant thunder rather
  than a constant bed of sound.

---

## Placeholder sounds

If a base file is missing, the app synthesises a simple placeholder loop for it
on first use (standard-library `wave`, no dependencies) so the feature works out
of the box. Replace any of them with real audio whenever you like — see
[Using your own sounds](#using-your-own-sounds).

Sound not playing at all? See
[Troubleshooting → no sound](TROUBLESHOOTING.md#theres-no-sound).
