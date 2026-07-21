# Sound Guide

The app can play a subtle ambient soundscape that matches the weather and time
of day. It's optional — if `pygame` isn't installed, sound is silently skipped.

- [Turning it on](#turning-it-on)
- [The sound files](#the-sound-files)
- [Using your own sounds](#using-your-own-sounds)
- [Variants (multiple clips per condition)](#variants-multiple-clips-per-condition)
- [Continuous playback](#continuous-playback)
- [Pause when other audio plays](#pause-when-other-audio-plays)
- [Placeholder sounds](#placeholder-sounds)
- [Play music](#play-music)

---

## Turning it on

1. On the **Dashboard** tab, tick **Ambient sound**.
2. On the **Settings** tab, set the **Ambient volume** (subtle by default).

The engine starts with the app; no Start action is needed.

---

## The sound files

Sounds live in the `sounds/` folder and are named by condition, so replacing
them is obvious. The **Settings → Sound → Sound files…** button lists these
names and opens the folder for you.

| When it plays | Filename |
|---|---|
| Clear sky, daytime | `clearday.wav` |
| Clear sky, night | `clearnight.wav` |
| Cloudy — **or a clear but windy sky** | `cloud.wav` |
| Rain | `rain.wav` |
| Storm | `storm.wav` |
| A task/timer chime fires | `chime.wav` |

Files must be **`.wav`**. (Renaming an `.mp3` won't work — convert it to WAV
first.)

> **Windy?** There's no separate "windy" sound — a strong wind on an otherwise
> clear sky uses **`cloud.wav`** (the breezy/overcast ambience). So `cloud.wav`
> is what you'll hear when it's windy. Pure "clear & calm" plays
> `clearday`/`clearnight`.

> The `sounds/` folder is found automatically next to the app, so your files
> are picked up no matter where you launch from. Sound plays while the app or
> `--background` engine is running (`--once` exits immediately).

---

## Using your own sounds

Just drop your own `.wav` files into `sounds/` using the names above,
overwriting the placeholders. No restart or config change needed — the engine
picks up the new file the next time that sound plays.

Tips:
- Loopable clips (a few seconds to a minute, seamless) work best.
- Generated legacy clips are upgraded automatically, but files whose contents
  do not match a known generated clip are treated as custom and preserved.

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

## Continuous playback

The chosen ambience loops continuously in the background. When weather or time
changes, the engine selects the matching sound and may pick a fresh variant. If
the operating system drops the audio channel, the engine detects that and
restarts it.

---

## Pause when other audio plays

Flow's own music player always takes priority: starting a song stops weather
ambience, and stopping or pausing the song starts ambience again.

Tick **Pause ambient when other audio is playing** (Settings → Sound) to extend
that behavior to detectable external audio:

Flow checks for audio changes every five seconds while this option is enabled,
then resumes ambience after the other audio stops.

- **macOS** — Spotify / Apple Music that are already running (their player
  state is `playing`). Browser/YouTube audio can't be detected this way.
- **Windows** — essentially any app, if [`pycaw`](https://pypi.org/project/pycaw/)
  is installed (`pip install pycaw`); without it, external audio is not detected.

Flow music priority works without `pycaw` and without the external-audio option.

---

## Placeholder sounds

If a base file is missing, the app synthesises a longer, softly levelled loop
for it on first use (standard-library `wave`, no dependencies) so the feature
works out of the box. Clear night uses quiet grasshopper-like calls; rain,
cloud, storm, and clear day use gentle condition-matched textures. Replace any
of them with your own audio whenever you like — see
[Using your own sounds](#using-your-own-sounds).

Sound not playing at all? See
[Troubleshooting → no sound](TROUBLESHOOTING.md#theres-no-sound).

---

## Play music

Open **⏱ Focus & Tasks → Music**. When the `music/` folder has no audio, Flow
creates two short, original sample tracks so the player works immediately.
Adding any of your own audio leaves that library untouched.

- **Add songs…** — pick `.mp3` / `.ogg` / `.wav` files; they're copied into the
  `music/` folder (next to the app). Or drop files there yourself and hit
  **Refresh**.
- **Play / ⏸ / ⏹ / ⏮ / ⏭** — play the selected track (double-click also plays)
  and move through the playlist manually.
- **Music volume** — saved separately from ambient volume. Ambience pauses
  while music is actively playing.
- **Open music folder** — reveal the folder in your file manager.

Music keeps playing while Flow is in the background, but stops when the main
app process exits. Tracks do not auto-advance at the end; use Previous/Next.

Needs `pygame` (same as ambient sound). `.mp3` and `.ogg` stream well; some
`.flac`/`.m4a` files may not load depending on your platform's codecs.
