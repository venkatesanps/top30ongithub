#!/usr/bin/env python3
"""Find a track's beats, bars and sections, and give them to an animation as frame numbers.

  beat_cues.py analyze track.mp3 --fps 30 --out cues.json       needs librosa
  beat_cues.py cuts cues.json --count 6 [--min-gap 1.5]          N cut points on downbeats
  beat_cues.py cuts cues.json --every-bars 2
  beat_cues.py snap cues.json --times 1.2,3.4,7 [--to beat|downbeat|onset] [--max-shift 0.25]
  beat_cues.py export cues.json --format ts|json|csv|gsap|manim|css [--name BEATS]

analyze needs librosa (pip install librosa, or: uv run --with librosa python3 beat_cues.py ...).
The other commands only read cues.json and need nothing beyond Python.
Downbeats are an estimate: the beat phase with the most bass energy (under 150 Hz, where the
kick drum sits), assuming the bar length you give (default 4 beats). Check them by ear on anything
that isn't in 4/4.
"""
import argparse
import csv
import io
import json
import sys
from pathlib import Path


def frames(t, fps):
    return int(round(t * fps))


# ---------- analyze ----------
def analyze(path, fps=30.0, beats_per_bar=4, start=None, end=None, bpm_hint=None, sections=None):
    try:
        import numpy as np
        import librosa
    except ImportError:
        sys.exit("beat_cues.py analyze needs librosa: pip install librosa  (or uv run --with librosa ...)")
    offset = float(start or 0.0)
    dur = None if end is None else float(end) - offset
    y, sr = librosa.load(path, sr=22050, mono=True, offset=offset, duration=dur)
    if y.size == 0:
        sys.exit("beat_cues.py: no audio read from " + str(path))
    length = len(y) / sr
    hop = 512
    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop, aggregate=np.median)
    kw = {"start_bpm": float(bpm_hint)} if bpm_hint else {}
    tempo, beat_frames = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr, hop_length=hop, units="frames", **kw)
    tempo_grid = float(np.atleast_1d(tempo)[0])
    beat_times = librosa.frames_to_time(beat_frames, sr=sr, hop_length=hop)
    # librosa's estimate is quantised to tempogram bins (120 BPM can read as 117.5), and single
    # gaps are quantised to the 23 ms analysis hop; a line fitted through all the beats is closer
    tempo = tempo_grid
    if len(beat_times) > 3:
        period = float(np.polyfit(np.arange(len(beat_times)), beat_times, 1)[0])
        if period > 0:
            tempo = 60.0 / period

    # downbeat phase: the bar usually starts on the kick, so take the bass energy (under 150 Hz)
    # just after each beat and pick the phase where it is highest on average
    S = np.abs(librosa.stft(y, hop_length=hop)) ** 2
    freqs = librosa.fft_frequencies(sr=sr)
    low = S[freqs < 150].sum(axis=0)
    phase = 0
    if len(beat_frames) >= beats_per_bar * 2:
        strength = np.array([low[f:f + 4].max() if f < len(low) else 0.0 for f in beat_frames])
        scores = [float(strength[p::beats_per_bar].mean()) for p in range(beats_per_bar)]
        phase = int(np.argmax(scores))
    down_times = beat_times[phase::beats_per_bar]

    onset_frames = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr, hop_length=hop, backtrack=False)
    onset_times = librosa.frames_to_time(onset_frames, sr=sr, hop_length=hop)
    on_str = onset_env[onset_frames] if len(onset_frames) else np.array([])
    on_str = on_str / on_str.max() if on_str.size and on_str.max() > 0 else on_str

    # sections: agglomerative segmentation on beat-synchronous chroma + MFCC
    sec = []
    if len(beat_frames) >= 16:
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop)
        mfcc = librosa.feature.mfcc(y=y, sr=sr, hop_length=hop, n_mfcc=13)
        feat = np.vstack([librosa.util.normalize(chroma, axis=1), librosa.util.normalize(mfcc, axis=1)])
        sync = librosa.util.sync(feat, beat_frames, aggregate=np.median)
        k = sections or int(np.clip(round(length / 20.0), 2, 8))
        k = max(1, min(k, sync.shape[1] - 1))
        bounds = librosa.segment.agglomerative(sync, k)
        bound_beats = sorted(set(int(b) for b in bounds))
        edges = [0.0] + [float(beat_times[min(b, len(beat_times) - 1)]) for b in bound_beats if b > 0] + [length]
        edges = sorted(set(round(e, 3) for e in edges))
        rms = librosa.feature.rms(y=y, hop_length=hop)[0]
        rms_t = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop)
        peak = float(rms.max()) or 1.0
        for a, b in zip(edges, edges[1:]):
            if b - a < 0.5:
                continue
            m = (rms_t >= a) & (rms_t < b)
            sec.append({"start": a, "end": b, "energy": round(float(rms[m].mean()) / peak, 3) if m.any() else 0.0})
    else:
        sec = [{"start": 0.0, "end": round(length, 3), "energy": 1.0}]

    sh = lambda t: round(float(t) + offset, 3)
    return {
        "source": str(path),
        "fps": fps,
        "duration": round(length, 3),
        "offset": offset,
        "tempo": round(tempo, 2),
        "tempo_estimate": round(tempo_grid, 2),
        "beat_seconds": round(60.0 / tempo, 4) if tempo else None,
        "beats_per_bar": beats_per_bar,
        "beats": [{"t": sh(t), "frame": frames(sh(t), fps), "downbeat": i % beats_per_bar == phase}
                  for i, t in enumerate(beat_times)],
        "downbeats": [{"t": sh(t), "frame": frames(sh(t), fps)} for t in down_times],
        "onsets": [{"t": sh(t), "frame": frames(sh(t), fps), "strength": round(float(s), 3)}
                   for t, s in zip(onset_times, on_str)],
        "sections": [dict(s, start=sh(s["start"]), end=sh(s["end"]), start_frame=frames(sh(s["start"]), fps),
                          end_frame=frames(sh(s["end"]), fps)) for s in sec],
    }


# ---------- cue maths (no librosa) ----------
def load(path):
    return json.loads(Path(path).read_text())


def points(cues, kind):
    if kind == "beat":
        return [b["t"] for b in cues["beats"]]
    if kind == "downbeat":
        return [b["t"] for b in cues["downbeats"]]
    if kind == "onset":
        return [o["t"] for o in cues["onsets"]]
    if kind == "section":
        return [s["start"] for s in cues["sections"]]
    raise ValueError(kind)


def snap(cues, times, to="beat", max_shift=0.25):
    grid = points(cues, to)
    out = []
    for t in times:
        if not grid:
            out.append({"wanted": t, "t": t, "frame": frames(t, cues["fps"]), "shift": 0.0, "snapped": False})
            continue
        best = min(grid, key=lambda g: abs(g - t))
        ok = abs(best - t) <= max_shift
        tt = best if ok else t
        out.append({"wanted": t, "t": round(tt, 3), "frame": frames(tt, cues["fps"]),
                    "shift": round(tt - t, 3), "snapped": ok})
    return out


def cuts(cues, count=None, every_bars=None, min_gap=1.0, start=None, end=None):
    """Cut points on downbeats: either every N bars, or `count` cuts spread evenly and moved to the
    nearest downbeat (never two closer than min_gap, never at 0 or the very end)."""
    downs = [d["t"] for d in cues["downbeats"]]
    lo = cues.get("offset", 0.0) if start is None else start
    hi = (cues.get("offset", 0.0) + cues["duration"]) if end is None else end
    downs = [d for d in downs if lo + 0.25 < d < hi - 0.25]
    if not downs:
        return []
    chosen = []
    if every_bars:
        chosen = downs[every_bars - 1::every_bars] if every_bars > 1 else downs
    elif count:
        span = hi - lo
        targets = [lo + span * (i + 1) / (count + 1) for i in range(count)]
        for t in targets:
            cand = sorted(downs, key=lambda d: abs(d - t))
            for d in cand:
                if all(abs(d - c) >= min_gap for c in chosen):
                    chosen.append(d)
                    break
        chosen.sort()
    return [{"t": round(t, 3), "frame": frames(t, cues["fps"])} for t in chosen]


def export(cues, fmt, name=None, kind="beat"):
    name = name or kind.upper() + "S"
    fps = cues["fps"]
    ts = points(cues, kind)
    fr = [frames(t, fps) for t in ts]
    if fmt == "json":
        return json.dumps({"fps": fps, "kind": kind, "frames": fr, "seconds": ts}, indent=1) + "\n"
    if fmt == "ts":
        return (f"// {kind}s from {Path(cues['source']).name} at {fps} fps, tempo {cues['tempo']} BPM\n"
                f"export const FPS = {int(fps) if float(fps).is_integer() else fps};\n"
                f"export const {name}: number[] = [{', '.join(map(str, fr))}];\n"
                f"export const SECTIONS = {json.dumps([{'from': s['start_frame'], 'to': s['end_frame'], 'energy': s['energy']} for s in cues['sections']])};\n")
    if fmt == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["kind", "seconds", "frame"])
        for t, f in zip(ts, fr):
            w.writerow([kind, t, f])
        return buf.getvalue()
    if fmt == "gsap":
        lines = [f"// add these labels to a gsap.timeline(); tempo {cues['tempo']} BPM"]
        lines += [f"tl.addLabel('{kind}{i}', {t});" for i, t in enumerate(ts)]
        return "\n".join(lines) + "\n"
    if fmt == "manim":
        return (f"# {kind} times in seconds; in construct(): self.wait(gap) between them\n"
                f"{name} = [{', '.join(str(t) for t in ts)}]\n"
                f"GAPS = [{', '.join(str(round(b - a, 3)) for a, b in zip([0.0] + ts, ts))}]\n")
    if fmt == "css":
        spb = cues["beat_seconds"] or 0.5
        return (f":root {{ --beat: {spb}s; --bar: {round(spb * cues['beats_per_bar'], 4)}s; "
                f"--first-beat: {ts[0] if ts else 0}s; }}\n"
                ".pulse { animation: pulse var(--beat) var(--first-beat) infinite; }\n")
    raise ValueError(fmt)


# ---------- CLI ----------
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze")
    a.add_argument("audio")
    a.add_argument("--fps", type=float, default=30.0)
    a.add_argument("--beats-per-bar", type=int, default=4)
    a.add_argument("--start", type=float)
    a.add_argument("--end", type=float)
    a.add_argument("--bpm-hint", type=float)
    a.add_argument("--sections", type=int, help="number of sections (default: about one per 20 s)")
    a.add_argument("--out")
    c = sub.add_parser("cuts")
    c.add_argument("cues")
    g = c.add_mutually_exclusive_group(required=True)
    g.add_argument("--count", type=int)
    g.add_argument("--every-bars", type=int)
    c.add_argument("--min-gap", type=float, default=1.0)
    c.add_argument("--start", type=float)
    c.add_argument("--end", type=float)
    s = sub.add_parser("snap")
    s.add_argument("cues")
    s.add_argument("--times", required=True, help="comma-separated seconds, or @file.json with a list")
    s.add_argument("--to", choices=["beat", "downbeat", "onset", "section"], default="beat")
    s.add_argument("--max-shift", type=float, default=0.25)
    e = sub.add_parser("export")
    e.add_argument("cues")
    e.add_argument("--format", choices=["ts", "json", "csv", "gsap", "manim", "css"], default="ts")
    e.add_argument("--kind", choices=["beat", "downbeat", "onset", "section"], default="beat")
    e.add_argument("--name", help="constant name (default: BEATS, DOWNBEATS, ONSETS or SECTIONS)")
    e.add_argument("--out")
    o = ap.parse_args(argv)

    if o.cmd == "analyze":
        res = analyze(o.audio, o.fps, o.beats_per_bar, o.start, o.end, o.bpm_hint, o.sections)
        text = json.dumps(res, indent=1) + "\n"
        if o.out:
            Path(o.out).write_text(text)
            print(f"wrote {o.out}: {res['tempo']} BPM, {len(res['beats'])} beats, {len(res['downbeats'])} bars, "
                  f"{len(res['onsets'])} onsets, {len(res['sections'])} sections over {res['duration']} s")
        else:
            sys.stdout.write(text)
    elif o.cmd == "cuts":
        res = cuts(load(o.cues), o.count, o.every_bars, o.min_gap, o.start, o.end)
        print(json.dumps(res, indent=1))
    elif o.cmd == "snap":
        if o.times.startswith("@"):
            times = [float(x) for x in json.loads(Path(o.times[1:]).read_text())]
        else:
            times = [float(x) for x in o.times.split(",") if x.strip()]
        res = snap(load(o.cues), times, o.to, o.max_shift)
        print(json.dumps(res, indent=1))
        far = [r for r in res if not r["snapped"]]
        if far:
            print(f"{len(far)} time(s) more than {o.max_shift} s from any {o.to}; left where they were", file=sys.stderr)
    elif o.cmd == "export":
        text = export(load(o.cues), o.format, o.name, o.kind)
        if o.out:
            Path(o.out).write_text(text)
            print(f"wrote {o.out}")
        else:
            sys.stdout.write(text)


if __name__ == "__main__":
    main()
