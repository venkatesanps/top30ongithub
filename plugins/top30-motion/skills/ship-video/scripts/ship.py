#!/usr/bin/env python3
"""Turn a rendered animation into a file a platform accepts, then prove it does.

  ship.py presets                                   list the presets
  ship.py plan  --in film.mp4 --preset reels [...]  print the ffmpeg commands, run nothing
  ship.py run   --in film.mp4 --preset reels [...]  run them (loudness in two passes)
  ship.py check out.mp4 --preset reels              ffprobe + loudness checks; exit 1 on a failure

Inputs: --in VIDEO, or --frames 'out/%05d.png' --fps 30 for an image sequence.
Options: --audio track.wav [--audio-offset S] [--audio-volume DB], --subs captions.srt|.ass
(--burn, the default for vertical presets, or --soft), --fit pad|crop|blur, --trim START END,
--loudness LUFS (default -14), --no-loudness, --quality fast|best, --out FILE.
Needs ffmpeg and ffprobe on PATH (6.0 or newer; burning captions needs libass). Standard library only.
"""
import argparse
import json
import re
import shlex
import shutil
import struct
import subprocess
import sys
from pathlib import Path

PRESETS = {
    # name: width, height, fps cap, container/codec family, extras
    "reels": dict(w=1080, h=1920, fps=30, kind="h264", note="Instagram Reels, 9:16"),
    "shorts": dict(w=1080, h=1920, fps=60, kind="h264", note="YouTube Shorts, 9:16"),
    "tiktok": dict(w=1080, h=1920, fps=30, kind="h264", note="TikTok, 9:16"),
    "youtube": dict(w=1920, h=1080, fps=60, kind="h264", note="YouTube 1080p, 16:9"),
    "youtube-4k": dict(w=3840, h=2160, fps=60, kind="h264", note="YouTube 2160p, 16:9"),
    "square": dict(w=1080, h=1080, fps=30, kind="h264", note="Feed post, 1:1"),
    "portrait": dict(w=1080, h=1350, fps=30, kind="h264", note="Feed post, 4:5"),
    "linkedin": dict(w=1920, h=1080, fps=30, kind="h264", note="LinkedIn and X, 16:9"),
    "web": dict(w=1920, h=1080, fps=60, kind="webm", note="VP9 + Opus WebM for a site's <video>"),
    "gif": dict(w=720, h=0, fps=15, kind="gif", note="Looping GIF, width 720, two-pass palette"),
    "master": dict(w=0, h=0, fps=0, kind="prores", note="ProRes 422 HQ + PCM, source size, for editing"),
}
VERTICAL = {"reels", "shorts", "tiktok"}
TRUE_PEAK = -1.0
LRA = 11


def die(msg, code=2):
    print(f"ship.py: {msg}", file=sys.stderr)
    sys.exit(code)


def need(tool):
    if not shutil.which(tool):
        die(f"{tool} not found on PATH (macOS: brew install ffmpeg; Linux: sudo apt install ffmpeg)")


def esc_filter_path(p):
    """Escape a path for a filter option inside a filtergraph (subtitles=, ass=), without quotes.
    Two levels: the option parser treats \\ ' : as special, then the graph parser treats
    \\ ' [ ] , ; as special. Spaces need nothing."""
    s = str(Path(p).resolve())
    s = "".join("\\" + c if c in "\\':" else c for c in s)        # option level
    return "".join("\\" + c if c in "\\'[],;" else c for c in s)  # graph level


def default_out(a):
    src = Path(a.inp) if a.inp else Path("frames")
    ext = {"h264": ".mp4", "webm": ".webm", "gif": ".gif", "prores": ".mov"}[PRESETS[a.preset]["kind"]]
    return str(src.with_name(f"{src.stem}.{a.preset}{ext}"))


def video_chain(a, p):
    """Scale/fit/fps filters for the preset, then captions."""
    f = []
    w, h, fps = p["w"], p["h"], p["fps"]
    if p["kind"] == "gif":
        f.append(f"fps={fps}" if fps else "fps=15")
        f.append(f"scale={w}:-2:flags=lanczos")
    elif w and h:
        fit = a.fit or ("blur" if a.preset in VERTICAL else "pad")
        if fit == "crop":
            f.append(f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,crop={w}:{h}")
        elif fit == "pad":
            f.append(f"scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos,"
                     f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color={a.pad_color}")
        elif fit == "blur":
            # handled as a split graph in build(); mark it
            return None
        f.append("setsar=1")
        if fps:
            f.append(f"fps={fps}")
    if a.subs and burn(a):
        f.append(sub_filter(a))
    if p["kind"] in ("h264",):
        f.append("format=yuv420p")
    return ",".join(f) if f else None


def sub_filter(a):
    """Burn-in filter. .ass files keep their own styling; SRT/VTT on 9:16 presets are lifted
    clear of the app's buttons (libass sizes SRT on a 288-line canvas: MarginV 60 is about
    400 px up on 1920)."""
    if a.subs.lower().endswith(".ass"):
        return f"ass={esc_filter_path(a.subs)}"
    style = ":force_style=MarginV=60" if a.preset in VERTICAL else ""
    return f"subtitles={esc_filter_path(a.subs)}{style}"


def burn(a):
    return not a.soft


def blur_graph(a, p):
    w, h, fps = p["w"], p["h"], p["fps"]
    g = (f"[0:v]split=2[bg][fg];"
         f"[bg]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},gblur=sigma=40,eq=brightness=-0.08[bgb];"
         f"[fg]scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos[fgs];"
         f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2,setsar=1" + (f",fps={fps}" if fps else ""))
    if a.subs and burn(a):
        g += "," + sub_filter(a)
    g += ",format=yuv420p[v]"
    return g


def inputs(a):
    args = []
    if a.frames:
        args += ["-framerate", str(a.fps or 30), "-i", a.frames]
    else:
        if a.trim:
            args += ["-ss", str(a.trim[0]), "-to", str(a.trim[1])]
        args += ["-i", a.inp]
    if a.audio:
        if a.audio_offset:
            args += ["-itsoffset", str(a.audio_offset)]
        args += ["-i", a.audio]
    return args


def audio_filter(a, measured=None):
    parts = []
    if a.audio_volume:
        parts.append(f"volume={a.audio_volume}dB")
    if not a.no_loudness:
        if measured:
            parts.append(
                f"loudnorm=I={a.loudness}:TP={TRUE_PEAK}:LRA={LRA}"
                f":measured_I={measured['input_i']}:measured_TP={measured['input_tp']}"
                f":measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}"
                f":offset={measured['target_offset']}:linear=true")
        else:
            parts.append(f"loudnorm=I={a.loudness}:TP={TRUE_PEAK}:LRA={LRA}")
        parts.append("aresample=48000")
    return ",".join(parts)


def audio_map(a):
    """Which audio stream goes out: the added track, else the source's (if any)."""
    if a.audio:
        return "1:a:0"
    if a.frames:
        return None
    return "0:a:0?"


def build(a, measured=None):
    p = PRESETS[a.preset]
    out = a.out or default_out(a)
    soft = bool(a.subs and not burn(a) and p["kind"] == "h264")
    ins = inputs(a) + (["-i", a.subs] if soft else [])
    cmd = ["ffmpeg", "-hide_banner", "-y"] + ins
    amap = audio_map(a)
    has_audio = amap is not None and p["kind"] != "gif"

    if p["kind"] == "gif":
        vf = video_chain(a, p)
        graph = f"[0:v]{vf},split[a][b];[a]palettegen=stats_mode=diff[pal];[b][pal]paletteuse=dither=sierra2_4a[v]"
        cmd += ["-filter_complex", graph, "-map", "[v]", "-loop", "0", out]
        return [cmd], out

    vf = video_chain(a, p)
    if vf is None and p["w"]:
        cmd += ["-filter_complex", blur_graph(a, p), "-map", "[v]"]
    else:
        if vf:
            cmd += ["-vf", vf]
        cmd += ["-map", "0:v:0"]
    if has_audio:
        cmd += ["-map", amap]
        af = audio_filter(a, measured)
        if af:
            cmd += ["-af", af]

    if p["kind"] == "h264":
        preset = "slow" if a.quality == "best" else "veryfast"
        crf = "18" if a.quality == "best" else "20"
        cmd += ["-c:v", "libx264", "-preset", preset, "-crf", crf, "-profile:v", "high",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
        if has_audio:
            cmd += ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]
    elif p["kind"] == "webm":
        cmd += ["-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0", "-row-mt", "1",
                "-deadline", "good", "-cpu-used", "2" if a.quality == "best" else "4", "-pix_fmt", "yuv420p"]
        if has_audio:
            cmd += ["-c:a", "libopus", "-b:a", "128k", "-ar", "48000"]
    elif p["kind"] == "prores":
        cmd += ["-c:v", "prores_ks", "-profile:v", "3", "-pix_fmt", "yuv422p10le"]
        if has_audio:
            cmd += ["-c:a", "pcm_s16le", "-ar", "48000"]
    if soft:
        sub_idx = 1 + (1 if a.audio else 0)
        cmd += ["-map", f"{sub_idx}:s:0", "-c:s", "mov_text", "-metadata:s:s:0", "language=eng"]
    if a.audio:
        cmd += ["-shortest"]
    cmd += [out]

    cmds = [cmd]
    if has_audio and not a.no_loudness and measured is None:
        cmds.insert(0, measure_cmd(a))
    return cmds, out


def measure_cmd(a):
    src = a.audio or a.inp
    cmd = ["ffmpeg", "-hide_banner", "-nostats"]
    if not a.audio and a.trim:
        cmd += ["-ss", str(a.trim[0]), "-to", str(a.trim[1])]
    cmd += ["-i", src, "-vn", "-af"]
    af = (f"volume={a.audio_volume}dB," if a.audio_volume else "") + \
        f"loudnorm=I={a.loudness}:TP={TRUE_PEAK}:LRA={LRA}:print_format=json"
    return cmd + [af, "-f", "null", "-"]


def parse_loudnorm(stderr):
    m = re.findall(r"\{[^{}]*\"input_i\"[^{}]*\}", stderr, re.S)
    if not m:
        return None
    return json.loads(m[-1])


def cmd_presets(_a):
    for k, p in PRESETS.items():
        size = f"{p['w']}x{p['h']}" if p["w"] and p["h"] else (f"width {p['w']}" if p["w"] else "source size")
        print(f"{k:11s} {size:11s} {('<=' + str(p['fps']) + ' fps') if p['fps'] else 'source fps':10s} {p['note']}")


def validate(a):
    if not (a.inp or a.frames):
        die("give --in VIDEO or --frames PATTERN")
    if a.inp and not a.dry and not Path(a.inp).exists():
        die(f"input not found: {a.inp}")
    if a.audio and not a.dry and not Path(a.audio).exists():
        die(f"audio not found: {a.audio}")
    if a.subs and not a.dry and not Path(a.subs).exists():
        die(f"captions not found: {a.subs}")
    if a.subs and a.soft and PRESETS[a.preset]["kind"] != "h264":
        die("--soft captions are only written to MP4 presets; use --burn for this preset")


def cmd_plan(a):
    a.dry = True
    validate(a)
    cmds, out = build(a)
    if len(cmds) == 2:
        print("# pass 1: measure loudness (read the JSON it prints)")
        print(shlex.join(cmds[0]))
        print("# pass 2: encode; `ship.py run` fills in measured_* from pass 1")
        print(shlex.join(cmds[1]))
    else:
        print(shlex.join(cmds[0]))
    print(f"# then: python3 {Path(__file__).name} check {shlex.quote(out)} --preset {a.preset}")


def cmd_run(a):
    a.dry = False
    need("ffmpeg")
    validate(a)
    cmds, out = build(a)
    measured = None
    if len(cmds) == 2:
        r = subprocess.run(cmds[0], capture_output=True, text=True)
        measured = parse_loudnorm(r.stderr)
        if r.returncode or not measured:
            die("loudness measurement failed:\n" + r.stderr[-1500:], 1)
        if measured["input_i"] in ("-inf", "inf"):
            print("note: the audio is silent; skipping loudness normalisation")
            a.no_loudness = True
            measured = None
        cmds, out = build(a, measured)
    final = cmds[-1]
    print("$ " + shlex.join(final))
    r = subprocess.run(final, capture_output=True, text=True)
    if r.returncode:
        die("ffmpeg failed:\n" + r.stderr[-2500:], 1)
    print(f"wrote {out}")
    if not a.no_check:
        sys.exit(check(out, a.preset, a.loudness, expect_audio=audio_map(a) is not None))


# ---------- check ----------
def ffprobe(path):
    need("ffprobe")
    r = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", path],
                       capture_output=True, text=True)
    if r.returncode:
        die(f"ffprobe could not read {path}: {r.stderr.strip()}", 1)
    return json.loads(r.stdout)


def mp4_atoms(path):
    """Top-level atom names in order (to confirm moov comes before mdat: fast start)."""
    names = []
    with open(path, "rb") as f:
        while True:
            hdr = f.read(8)
            if len(hdr) < 8:
                break
            size, name = struct.unpack(">I4s", hdr)
            if size == 1:
                size = struct.unpack(">Q", f.read(8))[0]
                f.seek(size - 16, 1)
            elif size == 0:
                names.append(name.decode("latin-1"))
                break
            else:
                f.seek(size - 8, 1)
            names.append(name.decode("latin-1"))
    return names


def measure_loudness(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-vn", "-af",
                        "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True)
    summary = r.stderr[r.stderr.rfind("Summary:"):]
    i = re.search(r"I:\s+(-?[\d.]+|-inf)\s+LUFS", summary)
    tp = re.search(r"Peak:\s+(-?[\d.]+|-inf)\s+dBFS", summary)
    to_f = lambda m: float(m.group(1)) if m and m.group(1) != "-inf" else float("-inf")
    return to_f(i), to_f(tp)


def rate(s):
    if not s or s == "0/0":
        return 0.0
    n, d = s.split("/")
    return float(n) / float(d) if float(d) else 0.0


def check(path, preset, loudness=-14.0, expect_audio=None, tolerance=1.0):
    p = PRESETS[preset]
    info = ffprobe(path)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    au = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    rows, bad = [], 0

    def row(ok, what, detail):
        nonlocal bad
        rows.append(("ok  " if ok else "FAIL") + f"  {what}: {detail}")
        bad += 0 if ok else 1

    if not v:
        row(False, "video stream", "none")
        print("\n".join(rows))
        return 1
    w, h = int(v["width"]), int(v["height"])
    if p["w"] and p["h"]:
        row((w, h) == (p["w"], p["h"]), "size", f"{w}x{h} (want {p['w']}x{p['h']})")
    elif p["w"]:
        row(w == p["w"], "width", f"{w} (want {p['w']})")
    row(w % 2 == 0 and h % 2 == 0 or p["kind"] == "gif", "even dimensions", f"{w}x{h}")
    fps = rate(v.get("avg_frame_rate")) or rate(v.get("r_frame_rate"))
    if p["fps"]:
        row(fps <= p["fps"] + 0.01, "frame rate", f"{fps:.3f} (at most {p['fps']})")
    want_codec = {"h264": "h264", "webm": "vp9", "gif": "gif", "prores": "prores"}[p["kind"]]
    row(v["codec_name"] == want_codec, "video codec", f"{v['codec_name']} (want {want_codec})")
    if p["kind"] == "h264":
        row(v.get("pix_fmt") == "yuv420p", "pixel format", f"{v.get('pix_fmt')} (want yuv420p; others fail on phones)")
        atoms = mp4_atoms(path)
        if "moov" in atoms and "mdat" in atoms:
            row(atoms.index("moov") < atoms.index("mdat"), "fast start", "moov before mdat" if atoms.index("moov") < atoms.index("mdat") else "moov after mdat (add -movflags +faststart)")
    dur = float(info["format"].get("duration", 0) or 0)
    row(dur > 0, "duration", f"{dur:.2f} s")
    if p["kind"] != "gif":
        if expect_audio is True:
            row(au is not None, "audio stream", "present" if au else "missing")
        if au:
            sr = int(au.get("sample_rate", 0) or 0)
            row(sr == 48000, "audio sample rate", f"{sr} Hz (want 48000)")
            if loudness is not None:
                i, tp = measure_loudness(path)
                if i == float("-inf"):
                    row(False, "loudness", "silent audio track")
                else:
                    row(abs(i - loudness) <= tolerance, "loudness", f"{i:.1f} LUFS (want {loudness} ± {tolerance})")
                    row(tp <= TRUE_PEAK + 0.5, "true peak", f"{tp:.1f} dBTP (want ≤ {TRUE_PEAK})")
    print(f"{path} vs {preset}:")
    print("\n".join(rows))
    print("PASS" if not bad else f"{bad} check(s) failed")
    return 1 if bad else 0


def cmd_check(a):
    loud = None if a.no_loudness else a.loudness
    sys.exit(check(a.file, a.preset, loud, expect_audio=a.expect_audio or None, tolerance=a.tolerance))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("presets").set_defaults(fn=cmd_presets)
    for name, fn in (("plan", cmd_plan), ("run", cmd_run)):
        s = sub.add_parser(name)
        s.add_argument("--in", dest="inp")
        s.add_argument("--frames", help="image sequence pattern, e.g. out/%%05d.png")
        s.add_argument("--fps", type=float, help="frame rate of --frames (default 30)")
        s.add_argument("--preset", required=True, choices=PRESETS)
        s.add_argument("--out")
        s.add_argument("--audio")
        s.add_argument("--audio-offset", type=float, default=0.0)
        s.add_argument("--audio-volume", type=float, default=0.0, help="dB applied before loudness")
        s.add_argument("--subs")
        g = s.add_mutually_exclusive_group()
        g.add_argument("--burn", action="store_true", help="draw captions into the picture (default)")
        g.add_argument("--soft", action="store_true", help="captions as a selectable track (MP4 only)")
        s.add_argument("--fit", choices=["pad", "crop", "blur"], help="default: blur for 9:16 presets, else pad")
        s.add_argument("--pad-color", default="black")
        s.add_argument("--trim", nargs=2, type=float, metavar=("START", "END"))
        s.add_argument("--loudness", type=float, default=-14.0, help="integrated LUFS target (default -14)")
        s.add_argument("--no-loudness", action="store_true")
        s.add_argument("--quality", choices=["fast", "best"], default="fast")
        s.add_argument("--no-check", action="store_true")
        s.set_defaults(fn=fn, dry=False)
    c = sub.add_parser("check")
    c.add_argument("file")
    c.add_argument("--preset", required=True, choices=PRESETS)
    c.add_argument("--loudness", type=float, default=-14.0)
    c.add_argument("--tolerance", type=float, default=1.0)
    c.add_argument("--no-loudness", action="store_true")
    c.add_argument("--expect-audio", action="store_true")
    c.set_defaults(fn=cmd_check)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
