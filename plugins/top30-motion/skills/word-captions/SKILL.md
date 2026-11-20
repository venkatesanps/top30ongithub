---
name: word-captions
description: Turn a voiceover into word-timed captions - run WhisperX for word timestamps, then group words into readable captions (line length, reading speed, pauses, phrase breaks) and write SRT, WebVTT, ASS with a karaoke word highlight, or Remotion Caption JSON for createTikTokStyleCaptions; also checks existing caption files. Use when a video needs subtitles or social-style captions, when captions run too fast or break mid-phrase, or when the user has a WhisperX JSON.
---

# Word captions

```bash
# 1. word timestamps, locally (item 99; models download from Hugging Face on first use)
whisperx voiceover.wav --model small --compute_type int8 --output_format json --output_dir .

# 2. captions
C="python3 ${CLAUDE_PLUGIN_ROOT}/skills/word-captions/scripts/captions.py"   # or this folder's scripts/
$C build voiceover.json --preset social   --out captions.ass    # 9:16: 1-2 short lines, a few words
$C build voiceover.json --preset karaoke  --out captions.ass    # each word lit as it's spoken
$C build voiceover.json --preset subtitle --out captions.srt    # 2 x 42 characters, 17 chars/s
$C build voiceover.json --out captions.json                     # Remotion Caption[] per word
$C check captions.srt --preset subtitle                         # reading speed, length, overlaps
```

Then burn them in with `ship-video` (`--subs captions.ass`), or in Remotion pass the JSON to
`createTikTokStyleCaptions()` from `@remotion/captions`.

## What the grouping does

- Starts a new caption at a pause (0.35-0.6 s by preset), after a full stop, and when the next
  word would break the line length, duration or word limit. When it has to break, it breaks
  at the last comma in the back half of the caption, so the next one starts a phrase instead
  of stranding the last word.
- Balances two lines, bottom line a little longer, and prefers to break the line after a comma.
- Keeps each caption up for its minimum time, but always 80 ms clear of the next one.
- WhisperX leaves words it couldn't align (often numbers like "30" or "2026") without times;
  they're placed between their neighbours and reported.
- ASS output is sized for the video (`--size 1080x1920` by default), bold with an outline,
  sitting about 22% up on vertical video, clear of the app's buttons. `--highlight #RRGGBB`
  sets the karaoke colour; each word stays lit until the next starts, so pauses don't let the
  highlight run ahead.

Override any limit: `--max-chars`, `--max-lines`, `--max-dur`, `--min-dur`, `--pause`, `--cps`,
`--max-words`.

## Before shipping

Read the captions against the audio once: names, product terms and numbers are where speech
recognition goes wrong. Fix the words in the JSON (keep the times) and build again rather than
editing the SRT by hand, so every format stays in step. Speaker labels (`--diarize`) need a
Hugging Face token and accepting pyannote's terms; leave them off unless the video has more
than one voice.
