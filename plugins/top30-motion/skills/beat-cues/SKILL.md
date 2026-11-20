---
name: beat-cues
description: Find a music track's tempo, beats, downbeats, onsets and sections with librosa and turn them into frame numbers an animation can use - cut points on downbeats, scene times snapped to the beat, and exports for Remotion (TypeScript), GSAP labels, Manim waits and CSS variables. Use when a video or animation should be cut or animated to music, when the user says "on the beat", "sync to the music" or "cut on the drop", or when scene timings feel off the rhythm.
---

# Beat cues

Motion that lands on the beat feels edited; motion that misses by a few frames feels wrong
without anyone knowing why. `scripts/beat_cues.py` measures the track once and gives every
other tool the same numbers, as frames at your video's frame rate.

```bash
B="python3 ${CLAUDE_PLUGIN_ROOT}/skills/beat-cues/scripts/beat_cues.py"   # or this folder's scripts/
$B analyze track.mp3 --fps 30 --out cues.json      # needs librosa (item 98)
#   or without installing it: uv run --with librosa python3 .../beat_cues.py analyze ...
$B cuts cues.json --count 6 --min-gap 1.5           # six scene changes, each on a downbeat
$B cuts cues.json --every-bars 2                     # a cut every two bars
$B snap cues.json --times 2.1,4.8,9.3 --to downbeat  # move planned scene times onto the grid
$B export cues.json --format ts --kind downbeat --out src/beats.ts   # Remotion: frames + sections
$B export cues.json --format gsap|manim|css|csv|json
```

`cues.json` holds the tempo (fitted through all the beats, not librosa's rounded estimate),
every beat with its frame and whether it starts a bar, downbeats, onsets with their strength
(hits worth a flash or a shake), and sections with relative energy (the quiet intro, the
drop). Use `--start/--end` to analyse only the part of the track you use, `--beats-per-bar 3`
for waltz time, `--bpm-hint` when it locks onto half or double time.

## Using the cues

- **Cuts and scene changes** on downbeats; **small moves** (a pop, a word landing) on beats;
  **accents** (flash, shake, particle burst) on the strongest onsets.
- Land, don't start, on the beat: an element arriving on beat 3 starts its move a few frames
  earlier. With a 10-frame entrance, start at `beat_frame - 8` so it settles on the beat.
- Use the highest-energy section for the reveal or the logo; keep the quiet section for text
  people have to read.
- `snap --max-shift` (default 0.25 s) leaves a time alone if no beat is near; it tells you
  which, so a scene that needs more time isn't squeezed.

## Check by ear

Downbeats are an estimate: the beat phase with the most bass energy just after it (where the
kick drum usually sits), assuming 4 beats a bar. Render a draft with a click or flash on each downbeat and listen once before
building on them. Swing, rubato, live recordings and ambient pads without percussion are where
it drifts; there, place the few cuts that matter by hand and use `snap --to onset`.
