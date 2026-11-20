"""Tests for the top30-motion scripts: captions, beat cues, Openverse audio, ship-video, stack check.

python3 tests/motion_kit/test_motion_kit.py
Needs ffmpeg/ffprobe for the ship-video part and librosa (+ numpy, soundfile) for beat analysis;
either part is skipped with a note if missing. No network: Openverse is a local stand-in server.
"""
import contextlib
import http.server
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
P = ROOT / "plugins/top30-motion/skills"
for s in ("word-captions", "beat-cues", "free-sound", "ship-video", "motion-stack"):
    sys.path.insert(0, str(P / s / "scripts"))
import beat_cues as bc  # noqa: E402
import captions as cap  # noqa: E402
import openverse_audio as ova  # noqa: E402
import ship  # noqa: E402
import stack_check as sc  # noqa: E402

FAILS = []


def ok(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        FAILS.append(msg)


def quiet(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return fn(*a, **k)


TMP = Path(tempfile.mkdtemp(prefix="motion-kit-"))

# ---------------------------------------------------------------- captions
WX = {"segments": [
    {"start": 0.5, "end": 4.9, "text": "Ship it in 30 seconds. Every frame, timed to the word.", "words": [
        {"word": "Ship", "start": 0.52, "end": 0.80, "score": 0.91}, {"word": "it", "start": 0.82, "end": 0.95},
        {"word": "in", "start": 0.97, "end": 1.05}, {"word": "30"}, {"word": "seconds.", "start": 1.62, "end": 2.1},
        {"word": "Every", "start": 2.9, "end": 3.2}, {"word": "frame,", "start": 3.22, "end": 3.6},
        {"word": "timed", "start": 3.9, "end": 4.2}, {"word": "to", "start": 4.22, "end": 4.3},
        {"word": "the", "start": 4.32, "end": 4.4}, {"word": "word.", "start": 4.42, "end": 4.9}]},
    {"start": 7.0, "end": 11.4, "text": "", "words": [
        {"word": w, "start": s, "end": e} for w, s, e in [
            ("Captions", 7.0, 7.5), ("that", 7.52, 7.7), ("follow", 7.72, 8.0), ("the", 8.02, 8.1),
            ("voice,", 8.12, 8.5), ("not", 8.7, 8.9), ("the", 8.92, 9.0), ("other", 9.02, 9.3),
            ("way", 9.32, 9.5), ("round,", 9.52, 9.9), ("and", 10.1, 10.2), ("never", 10.22, 10.5),
            ("cover", 10.52, 10.8), ("the", 10.82, 10.9), ("button.", 10.92, 11.4)]]}]}
wxp = TMP / "vo.json"
wxp.write_text(json.dumps(WX))
words = quiet(cap.load_words, wxp)
ok(len(words) == 26, "captions: 26 words read from WhisperX JSON")
thirty = next(w for w in words if w["text"] == "30")
ok(thirty.get("filled") and 1.05 <= thirty["start"] < thirty["end"] <= 1.62, "captions: unaligned '30' placed between neighbours")

sub = cap.group(words, cap.PRESETS["subtitle"])
texts = [" / ".join(cap.text_of(l) for l in c["lines"]) for c in sub]
ok(texts[0] == "Ship it in 30 seconds.", "captions: sentence end closes a caption")
ok(any(t.endswith("round,") for t in texts) and texts[-1] == "and never cover the button.",
   "captions: long caption breaks at the last comma, no stranded last word")
ok(all(len(cap.text_of(l)) <= 42 for c in sub for l in c["lines"]), "captions: subtitle lines within 42 characters")
ok(all(sub[i]["end"] <= sub[i + 1]["start"] - cap.GAP + 1e-6 for i in range(len(sub) - 1)), "captions: cues never overlap")
iss = cap.check(sub, cap.PRESETS["subtitle"])
ok(not [i for i in iss if i[1] == "error"], "captions: subtitle output has no errors in its own check")
ok([(i[0], i[2].split(" ")[1]) for i in iss] == [(4, "characters")], "captions: check flags the one fast caption (27 characters in 1.3 s)")

soc = cap.group(words, cap.PRESETS["social"])
ok(all(len(c["words"]) <= 4 for c in soc) and all(len(cap.text_of(l)) <= 18 for c in soc for l in c["lines"]),
   "captions: social preset keeps 4 words and 18 characters a line")
ok(any(cap.text_of(c["words"]) == "Every frame," for c in soc), "captions: social preset breaks after 'frame,'")

srt = cap.write_srt(sub)
ok(srt.startswith("1\n00:00:00,520 --> 00:00:02,100\nShip it in 30 seconds.\n"), "captions: SRT timestamps and text")
ok(cap.write_vtt(sub).startswith("WEBVTT\n\n00:00:00.520 --> "), "captions: VTT header and dot milliseconds")
parsed = cap.parse_srt_vtt(srt)
ok(len(parsed) == len(sub) and abs(parsed[1]["start"] - sub[1]["start"]) < 1e-3, "captions: SRT parses back")

ass = cap.write_ass(cap.group(words, cap.PRESETS["karaoke"]), 1080, 1920, True, "Arial", "#FFD400")
ok("PlayResX: 1080" in ass and "PlayResY: 1920" in ass and "&H0000D4FF" in ass, "captions: ASS sized for 1080x1920 with highlight colour")
first = next(l for l in ass.splitlines() if l.startswith("Dialogue"))
ok("{\\kf30}Ship {\\kf15}it" in first, "captions: karaoke word lit until the next word starts")
rem = json.loads(cap.write_remotion(words))
ok(rem[0]["text"] == "Ship" and rem[1]["text"] == " it" and rem[0]["startMs"] == 520 and rem[0]["endMs"] == 800,
   "captions: Remotion Caption[] with leading spaces and ms")
back = quiet(cap.load_words, (lambda p: (p.write_text(json.dumps(rem)), p)[1])(TMP / "rem.json"))
ok(len(back) == 26 and back[1]["text"] == "it", "captions: Remotion JSON reads back as input")
bad = [{"start": 0.0, "end": 0.3, "text_lines": ["A much too long line for a short caption to read here"]},
       {"start": 0.2, "end": 1.0, "text_lines": ["x"]}]
kinds = {m.split(" ")[0] for _, _, m in cap.check(bad, cap.PRESETS["subtitle"])}
ok({"line", "on", "overlaps"} <= kinds, "captions: check flags long lines, short display and overlaps")

# ---------------------------------------------------------------- beat cues (maths)
fake = {"source": "t.wav", "fps": 30, "duration": 24.0, "offset": 0.0, "tempo": 120.0, "beat_seconds": 0.5,
        "beats_per_bar": 4,
        "beats": [{"t": round(0.25 + 0.5 * i, 3), "frame": 0, "downbeat": i % 4 == 1} for i in range(47)],
        "downbeats": [{"t": round(0.75 + 2.0 * i, 3), "frame": 0} for i in range(12)],
        "onsets": [{"t": 0.75, "frame": 22, "strength": 1.0}],
        "sections": [{"start": 0.0, "end": 12.0, "energy": 0.2, "start_frame": 0, "end_frame": 360},
                     {"start": 12.0, "end": 24.0, "energy": 0.8, "start_frame": 360, "end_frame": 720}]}
sn = bc.snap(fake, [2.6, 9.6], to="downbeat", max_shift=0.3)
ok(sn[0]["t"] == 2.75 and sn[0]["frame"] == 82 and sn[0]["snapped"], "beat-cues: snap moves 2.6 s to the 2.75 s downbeat")
ok(not sn[1]["snapped"] and sn[1]["t"] == 9.6, "beat-cues: snap leaves a time far from any downbeat alone")
cs = bc.cuts(fake, count=3, min_gap=1.5)
ok(len(cs) == 3 and all(c["t"] in [d["t"] for d in fake["downbeats"]] for c in cs), "beat-cues: cuts land on downbeats")
ok([c["t"] for c in bc.cuts(fake, every_bars=4)] == [6.75, 14.75, 22.75], "beat-cues: every 4 bars")
ts = bc.export(fake, "ts", kind="downbeat")
ok("export const DOWNBEATS: number[] = [22, 82," in ts and "export const SECTIONS" in ts, "beat-cues: TypeScript export in frames")
ok("tl.addLabel('beat0', 0.25);" in bc.export(fake, "gsap"), "beat-cues: GSAP labels")
ok("--beat: 0.5s" in bc.export(fake, "css"), "beat-cues: CSS beat variable")

# ---------------------------------------------------------------- beat cues (librosa)
try:
    import numpy as np
    import soundfile as sf
    import librosa  # noqa: F401
    have_librosa = True
except ImportError:
    have_librosa = False
    print("skip beat analysis: librosa/numpy/soundfile not installed")
if have_librosa:
    sr, bpm, dur = 22050, 120, 24.0
    y = np.zeros(int(sr * dur))
    t = np.arange(int(0.08 * sr)) / sr
    for i in range(int(dur / 0.5)):
        n = int((0.25 + i * 0.5) * sr)
        if n + len(t) >= len(y):
            break
        if i % 4 == 1:  # bars start on the second beat
            sig = 0.9 * np.sin(2 * np.pi * 55 * t) * np.exp(-t * 30)
        else:
            sig = 0.35 * np.random.RandomState(i).randn(len(t)) * np.exp(-t * 80)
        y[n:n + len(t)] += sig
    y[int(12 * sr):] += 0.15 * np.sin(2 * np.pi * 220 * np.arange(len(y) - int(12 * sr)) / sr)
    wav = TMP / "click.wav"
    sf.write(wav, y.astype(np.float32), sr)
    res = bc.analyze(str(wav), fps=30)
    ok(abs(res["tempo"] - 120) < 1.0, f"beat-cues: tempo {res['tempo']} within 1 BPM of 120")
    gaps = np.diff([b["t"] for b in res["beats"]])
    ok(abs(float(np.median(gaps)) - 0.5) < 0.03, "beat-cues: beats every 0.5 s")
    downs = [d["t"] for d in res["downbeats"]]
    ok(all(min(abs(d - (0.75 + 2.0 * k)) for k in range(12)) < 0.05 for d in downs),
       "beat-cues: downbeats found on the accented phase")
    ok(len(res["sections"]) >= 2 and res["sections"][-1]["energy"] > res["sections"][0]["energy"],
       "beat-cues: louder second half is a higher-energy section")
    ok(all(b["frame"] == round(b["t"] * 30) for b in res["beats"]), "beat-cues: frames are seconds x fps")

# ---------------------------------------------------------------- free-sound (local stand-in for the API)
RESULTS = [
    {"id": "aaaa1111-0000-0000-0000-000000000001", "title": "Calm Piano Loop", "creator": "Ana", "license": "by",
     "license_version": "4.0", "license_url": "https://creativecommons.org/licenses/by/4.0/", "duration": 42000,
     "filetype": "mp3", "source": "freesound", "foreign_landing_url": "https://freesound.org/s/1/"},
    {"id": "bbbb2222-0000-0000-0000-000000000002", "title": "Night Pad", "creator": "Ben", "license": "by-nc",
     "license_version": "3.0", "duration": 61000, "filetype": "wav", "source": "jamendo",
     "foreign_landing_url": "https://jamendo.com/2"},
    {"id": "cccc3333-0000-0000-0000-000000000003", "title": "Tiny Click", "creator": "", "license": "cc0",
     "license_version": "1.0", "duration": 400, "filetype": "wav", "source": "freesound",
     "foreign_landing_url": "https://freesound.org/s/3/"},
    {"id": "dddd4444-0000-0000-0000-000000000004", "title": "Pure Tone", "creator": "Dee", "license": "by-nd",
     "license_version": "4.0", "duration": 30000, "filetype": "mp3", "source": "ccmixter",
     "foreign_landing_url": "https://ccmixter.org/4"},
]
SEEN = []


class Fake(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        SEEN.append((self.path, self.headers.get("Authorization")))
        if self.path.startswith("/v1/audio/?"):
            body = json.dumps({"result_count": len(RESULTS), "results": RESULTS}).encode()
            ctype = "application/json"
        elif self.path.startswith("/v1/audio/"):
            i = self.path.split("/")[3]
            r = next((x for x in RESULTS if x["id"] == i), None)
            if not r:
                self.send_response(404)
                self.end_headers()
                return
            r = dict(r, url=f"http://127.0.0.1:{PORT}/files/{i}.{r['filetype']}")
            body, ctype = json.dumps(r).encode(), "application/json"
        elif self.path.startswith("/files/"):
            body, ctype = b"ID3fake-audio-bytes", "audio/mpeg"
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
ova.API = f"http://127.0.0.1:{PORT}/v1"
os.environ["OPENVERSE_TOKEN"] = "tok123"
rows, total = ova.search("piano", {"commercial", "modify"}, category="music", min_sec=20, max_sec=90)
q = SEEN[-1][0]
ok("license_type=commercial%2Cmodification" in q and "category=music" in q and "mature=false" in q,
   "free-sound: search asks the API for commercial + modification licences")
ok(SEEN[-1][1] == "Bearer tok123", "free-sound: OPENVERSE_TOKEN sent as a bearer token")
ok([r["title"] for r in rows] == ["Calm Piano Loop"], "free-sound: NC, ND and too-short results dropped client-side too")
ok(rows[0]["seconds"] == 42.0, "free-sound: duration converted from milliseconds")
adir = TMP / "audio"
done, refused, _ = quiet(ova.fetch, [RESULTS[0]["id"], RESULTS[1]["id"], RESULTS[2]["id"]], {"commercial", "modify"}, adir)
ok([e["title"] for e in done] == ["Calm Piano Loop", "Tiny Click"] and len(refused) == 1 and "NC" in refused[0][2][0],
   "free-sound: fetch refuses the NC track for commercial use")
ok((adir / done[0]["file"]).read_bytes() == b"ID3fake-audio-bytes" and done[0]["file"].startswith("calm-piano-loop-aaaa1111"),
   "free-sound: file saved with a readable name")
credits = (adir / "CREDITS.md").read_text()
ok('"Calm Piano Loop" by Ana, from freesound (https://freesound.org/s/1/), CC BY 4.0' in credits and "credit required" in credits,
   "free-sound: CREDITS.md has the TASL line for CC BY")
ok("Tiny Click" in credits and "no credit required" in credits, "free-sound: CC0 marked as no credit required")
done2, _, _ = quiet(ova.fetch, [RESULTS[0]["id"]], {"commercial", "modify"}, adir)
ok(len(json.loads((adir / "credits.json").read_text())) == 2, "free-sound: re-fetching does not duplicate credits")
ok(not ova.permitted("by-nd", {"modify"})[0] and ova.permitted("by-nd", {"commercial"})[0], "free-sound: ND blocks edits only")
ok(ova.allows("by-sa")["share_alike"] and not ova.allows("cc0")["credit"], "free-sound: SA and CC0 rules")
srv.shutdown()

# ---------------------------------------------------------------- ship-video
if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
    print("skip ship-video renders: ffmpeg/ffprobe not installed")
else:
    def ff(*args):
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)

    src = TMP / "src clip.mp4"  # a space in the name, on purpose
    ff("-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=60", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
       "-t", "3", "-c:v", "libx264", "-pix_fmt", "yuv444p", "-c:a", "aac", str(src))
    srt = TMP / "it's: captions.srt"  # apostrophe and colon must survive filter escaping
    srt.write_text("1\n00:00:00,300 --> 00:00:01,800\nHello: it's a test, okay\n\n")
    music = TMP / "music.wav"
    ff("-f", "lavfi", "-i", "sine=frequency=220:sample_rate=44100", "-t", "6", "-af", "volume=-30dB", str(music))

    def args(**kw):
        base = dict(inp=None, frames=None, fps=None, preset="reels", out=None, audio=None, audio_offset=0.0,
                    audio_volume=0.0, subs=None, burn=False, soft=False, fit=None, pad_color="black", trim=None,
                    loudness=-14.0, no_loudness=False, quality="fast", no_check=True, dry=True)
        base.update(kw)
        return type("A", (), base)()

    cmds, out = ship.build(args(inp=str(src), subs=str(srt)))
    ok(len(cmds) == 2 and "print_format=json" in " ".join(cmds[0]), "ship-video: loudness measured in a first pass")
    graph = cmds[1][cmds[1].index("-filter_complex") + 1]
    ok("gblur" in graph and "MarginV=60" in graph and "format=yuv420p" in graph, "ship-video: 9:16 blur fill, lifted captions, yuv420p")
    ok(cmds[1][cmds[1].index("-preset") + 1] == "veryfast", "ship-video: veryfast unless --quality best")

    reel = TMP / "reel.mp4"
    try:
        quiet(ship.cmd_run, args(inp=str(src), subs=str(srt), out=str(reel), dry=False, no_check=True))
    except SystemExit as e:
        ok(not e.code, f"ship-video: run exited {e.code}")
    rc = quiet(ship.check, str(reel), "reels", -14.0, True)
    ok(rc == 0, "ship-video: Reels file passes size, fps, codec, yuv420p, fast start, 48 kHz, -14 LUFS, true peak")
    ok(ship.mp4_atoms(str(reel)).index("moov") < ship.mp4_atoms(str(reel)).index("mdat"), "ship-video: moov before mdat")
    rc_src = quiet(ship.check, str(src), "reels", -14.0, True)
    ok(rc_src == 1, "ship-video: check fails the unprocessed 1280x720 yuv444 source")

    frames_dir = TMP / "frames"
    frames_dir.mkdir()
    ff("-f", "lavfi", "-i", "testsrc=size=1920x1080:rate=30", "-t", "2", str(frames_dir / "%05d.png"))
    yt = TMP / "yt.mp4"
    try:
        quiet(ship.cmd_run, args(frames=str(frames_dir / "%05d.png"), fps=30, preset="youtube", audio=str(music),
                                 out=str(yt), dry=False, no_check=True))
    except SystemExit as e:
        ok(not e.code, f"ship-video: frames run exited {e.code}")
    info = ship.ffprobe(str(yt))
    dur = float(info["format"]["duration"])
    ok(abs(dur - 2.0) < 0.15, f"ship-video: image sequence + longer music trimmed to the picture ({dur:.2f} s)")
    i, tp = ship.measure_loudness(str(yt))
    ok(abs(i + 14) <= 1.0, f"ship-video: quiet music raised to {i:.1f} LUFS")

    gif = TMP / "loop.gif"
    try:
        quiet(ship.cmd_run, args(inp=str(src), preset="gif", trim=[0.5, 1.5], out=str(gif), dry=False, no_check=True))
    except SystemExit as e:
        ok(not e.code, f"ship-video: gif run exited {e.code}")
    g = next(s for s in ship.ffprobe(str(gif))["streams"] if s["codec_type"] == "video")
    ok(g["codec_name"] == "gif" and int(g["width"]) == 720, "ship-video: GIF 720 wide")

    soft = TMP / "soft.mp4"
    try:
        quiet(ship.cmd_run, args(inp=str(src), preset="square", subs=str(srt), soft=True, out=str(soft), dry=False, no_check=True))
    except SystemExit as e:
        ok(not e.code, f"ship-video: soft-caption run exited {e.code}")
    st = ship.ffprobe(str(soft))["streams"]
    ok(any(s["codec_type"] == "subtitle" and s["codec_name"] == "mov_text" for s in st)
       and next(s for s in st if s["codec_type"] == "video")["width"] == 1080, "ship-video: square with a soft caption track")

# ---------------------------------------------------------------- stack check
fakebin = TMP / "bin"
fakebin.mkdir()
for name, out in (("node", "v22.12.0"), ("bun", "1.1.30"), ("ffmpeg", "ffmpeg version 5.1.2"), ("uv", "uv 0.5.0")):
    f = fakebin / name
    f.write_text(f"#!/bin/sh\necho '{out}'\n")
    f.chmod(0o755)
old_path, old_home = os.environ["PATH"], os.environ.get("HOME")
os.environ["PATH"] = f"{fakebin}{os.pathsep}/usr/bin{os.pathsep}/bin"
home = TMP / "home"
(home / ".claude/skills/reanimate").mkdir(parents=True)
(home / ".claude/skills/reanimate/SKILL.md").write_text("---\nname: reanimate\n---\n")
sc.HOME, sc.SKILLS = home, home / ".claude/skills"
t = sc.tools()
ok(t["node"]["ok"] and t["node"]["version"] == "22.12.0", "stack: node 22 found")
ok(not t["ffmpeg"]["ok"] and t["ffmpeg"]["version"] == "5.1.2", "stack: ffmpeg 5 reported below the 6.0 minimum")
st = {n: {"installed": sc.installed(n, plugin_list="cinetic@cinetic  1.5.1"), "install": sc.ITEMS[n][2]} for n in sc.ITEMS}
ok(st[84]["installed"] and not st[85]["installed"], "stack: skill folders detected")
ok(st[89]["installed"] and not st[88]["installed"], "stack: plugins detected from `claude plugin list`")
pl = sc.plan("launch-film", t, st)
first = [r for r in pl["items"] if r["role"] == "use"]
ok([r["n"] for r in first] == [89, 100] and "ffmpeg" in first[0]["missing_tools"], "stack: launch-film plan names cinetic + Remotion and the old ffmpeg")
ok(first[1]["install"].startswith("npx -y skills add remotion-dev/skills"), "stack: install line for what is missing")
ok({k["skill"] for k in pl["kit"]} == {"beat-cues", "word-captions", "ship-video"}, "stack: kit scripts for the job")
ok(all(j in sc.JOBS for j in ("copy", "captions", "sound", "ship", "3d", "web-vfx")), "stack: jobs cover every step")
cat = json.loads((ROOT / "catalog.json").read_text())
names = {i["n"]: i for i in cat["items"]}
ok(all(n in names and names[n]["collection"] == "motion18" for n in sc.ITEMS), "stack: every item number matches catalog.json")
os.environ["PATH"] = old_path
if old_home is not None:
    os.environ["HOME"] = old_home

shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{'all passed' if not FAILS else str(len(FAILS)) + ' failed'}")
sys.exit(1 if FAILS else 0)
