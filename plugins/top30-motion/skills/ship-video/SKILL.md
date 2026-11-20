---
name: ship-video
description: Turn a rendered animation or image sequence into a file a platform accepts - Reels, Shorts, TikTok, YouTube, square, 4:5, LinkedIn/X, a web WebM, a looping GIF or a ProRes master - with blur or pad fill for 9:16, burned or soft captions, music muxed and loudness normalised to -14 LUFS in two passes, then verify size, frame rate, codec, pixel format, fast start, sample rate, loudness and true peak with ffprobe. Use when exporting or delivering a video, when a platform rejects or re-compresses an upload, when audio is too quiet or loud, or before calling a film done.
---

# Ship video

Renders from Remotion, HyperFrames, a canvas page, Manim or Blender come out at whatever size,
rate and loudness they were made at. Platforms then reject them, crop them, or squash the sound.
`scripts/ship.py` makes the file each platform expects, and checks it.

```bash
V="python3 ${CLAUDE_PLUGIN_ROOT}/skills/ship-video/scripts/ship.py"   # or this folder's scripts/
$V presets
$V plan --in film.mp4 --preset reels --audio track.mp3 --subs captions.ass   # prints the commands
$V run  --in film.mp4 --preset reels --audio track.mp3 --subs captions.ass   # runs, then checks
$V run  --frames 'out/%05d.png' --fps 30 --preset youtube --audio track.mp3
$V run  --in film.mp4 --preset gif --trim 2 6
$V check delivered.mp4 --preset shorts          # exit 1 if anything fails
```

| Preset | Output |
|---|---|
| `reels`, `tiktok` / `shorts` | 1080x1920, up to 30 / 60 fps, H.264 High, yuv420p, AAC 48 kHz |
| `youtube`, `youtube-4k` | 1920x1080 / 3840x2160, up to 60 fps |
| `square`, `portrait`, `linkedin` | 1080x1080, 1080x1350, 1920x1080 |
| `web` | VP9 + Opus WebM for a site's `<video>` |
| `gif` | 720 wide, 15 fps, two-pass palette, loops |
| `master` | ProRes 422 HQ + PCM at source size, for an editor |

## What it does for you

- **Fit**: 16:9 into 9:16 defaults to a blurred, darkened copy behind the picture (`--fit
  blur`); `pad` adds bars, `crop` fills and cuts the edges.
- **Loudness**: measures first, then normalises to -14 LUFS integrated with a -1 dBTP ceiling
  (`--loudness -16` for a quieter target; `--no-loudness` to leave it). Silent audio is left alone.
- **Captions**: `.ass` keeps its own styling (use `word-captions`); SRT/VTT are styled by
  libass and lifted clear of the app buttons on 9:16. `--soft` adds a selectable track instead
  (MP4 only).
- **Encoding**: H.264 `-preset veryfast -crf 20`, `+faststart` so it plays before it finishes
  downloading. `--quality best` switches to `slow`, `crf 18` and takes 2-3 times as long.
- `--trim START END`, `--audio-offset S` (music starts later), `--audio-volume DB`.

## Check before you call it done

`run` ends with `check`; for a file made elsewhere run `check` yourself. It fails on the wrong
size, a frame rate above the preset's cap, a codec or pixel format phones won't play
(yuv444 from a screen recorder is the usual one), the index at the end of the file, audio not
at 48 kHz, loudness more than 1 LU off target, or true peak above -1 dBTP. Then look at it:
`ffmpeg -i out.mp4 -vf fps=1,scale=320:-1,tile=4x3 sheet.png` and open the sheet.

Needs ffmpeg and ffprobe 6+ with libass and libx264 (Homebrew's and most Linux builds have
both; `stack_check.py tools` in `motion-stack` shows what yours has).
