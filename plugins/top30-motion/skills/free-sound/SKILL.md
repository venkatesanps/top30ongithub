---
name: free-sound
description: Find music and sound effects you are allowed to use on Openverse (openly licensed audio from Freesound, Jamendo, ccMixter, Wikimedia and others), filtered by what you'll do with them (commercial use, editing), download them and keep a credits file with title, creator, source and licence. Use when a video or animation needs a music bed, sound effects or ambience, when the user asks for royalty-free or Creative Commons audio, or asks what a CC licence allows.
---

# Free sound

```bash
O="python3 ${CLAUDE_PLUGIN_ROOT}/skills/free-sound/scripts/openverse_audio.py"   # or this folder's scripts/
$O search "warm lofi piano" --category music --min-sec 25 --max-sec 90
$O search "whoosh transition" --category sound_effect --length shortest
$O fetch <id> <id> --dir audio/          # downloads, records the licence, writes audio/CREDITS.md
$O license by-nc-sa                       # what a licence allows
```

`--use` says what you'll do with the file. The default, `commercial,modify`, is right for
almost any video: it's published by a business, and a film always cuts, loops or mixes its
audio. That rules out NC (non-commercial) and ND (no derivatives). Use `--use modify` only for
personal, non-commercial work. `fetch` checks each file's licence again and refuses what your
use doesn't allow, so a file you found earlier under another filter can't slip in.

## Choosing

1. Search with mood and use words ("tense build", "upbeat corporate", "soft click UI"), and a
   length that covers the film; loops are fine for longer ones.
2. Open the page link of the top few (`--json` prints them) and **listen** before fetching:
   the index has no idea how a track sounds.
3. Fetch the one you pick, then `beat-cues analyze` it before building scenes.

## Credits and licences

- **CC0 and Public Domain Mark**: no credit required (credit anyway when there's room).
- **BY**: credit in the description or end card. `CREDITS.md` has the line to paste.
- **BY-SA**: credit, and a work that *adapts* the track must carry the same licence; syncing
  music to a video is usually treated as an adaptation, so avoid SA for anything you don't want
  under CC BY-SA.
- **NC, ND, Sampling+**: refused by default; Sampling licences are retired, so read the deed.
- Keep `audio/credits.json` and `CREDITS.md` with the project: they are the record of where
  each file came from and under what terms.

Openverse indexes what its sources publish and doesn't verify it. For anything paid or
high-profile, check the licence on the source page (the `page` link) as well.
Anonymous API use is rate-limited; set `OPENVERSE_TOKEN` if you hit the limit. No key or
account is needed otherwise.
