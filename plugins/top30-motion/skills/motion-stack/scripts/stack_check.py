#!/usr/bin/env python3
"""Which animation tools does this machine have, and which ones does a given job need?

  stack_check.py tools [--json]          node, bun, uv, python, ffmpeg (+ libass, loudnorm, x264),
                                         Chrome/Chromium, Blender, LaTeX, Manim, WhisperX, librosa...
  stack_check.py skills [--json]         which of the 18 motion repos are installed for Claude Code
  stack_check.py plan <job> [--json]     the repos and kit scripts for a job, what is missing,
                                         and the install line for each missing piece
  stack_check.py jobs                    list the jobs

Read-only: it runs version commands and looks for files; it installs nothing.
Standard library only. Item numbers refer to catalog.json in venkatesanps/top30ongithub.
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HOME = Path(os.environ.get("HOME", str(Path.home())))
SKILLS = HOME / ".claude" / "skills"

# n: (name, how it is installed, how to install, needs)
ITEMS = {
    84: ("reanimate", ("skill", "reanimate"), "npx -y skills add NiazMorshed2007/reanimate -g -a claude-code -y", ["node", "bun"]),
    85: ("motion-design (LottieFiles)", ("skill", "motion-design"), "npx -y skills add LottieFiles/motion-design-skill -g -a claude-code -y", ["node"]),
    86: ("15 motion design styles", ("dir", "mg-styles-15/prompts"), "./install.sh 86   (sparse clone into ~/mg-styles-15)", ["git", "node", "python", "ffmpeg", "chrome"]),
    87: ("huashu-art-motion", ("skill", "huashu-art-motion"), "npx -y skills add alchaincyf/huashu-art-motion -g -a claude-code -y", ["node", "uv", "ffmpeg"]),
    88: ("anidoodle", ("plugin", "anidoodle@alexgreensh-anidoodle"), "claude plugin marketplace add alexgreensh/anidoodle && claude plugin install anidoodle@alexgreensh-anidoodle", ["node"]),
    89: ("cinetic", ("plugin", "cinetic@cinetic"), "claude plugin marketplace add Leonxlnx/cinetic && claude plugin install cinetic@cinetic", ["node", "python", "ffmpeg", "chrome"]),
    90: ("motionmaxxing", ("skill", "motionmaxxing"), "git clone --depth 1 https://github.com/Tejashmakwana/motionmaxxing ~/.claude/skills/motionmaxxing", ["node", "python", "ffmpeg", "chrome"]),
    91: ("Manim", ("tool", "manim"), "uv tool install manim", ["uv", "ffmpeg"]),
    92: ("Blender skills", ("plugin", "blender-agent-skills@blender-agent-skills"), "claude plugin marketplace add EL4CTEO/blender-skills && claude plugin install blender-agent-skills@blender-agent-skills", ["blender"]),
    93: ("three.quarks", ("npm", "three.quarks"), "npm install three three.quarks   (in your three.js project)", ["node"]),
    94: ("react-postprocessing", ("npm", "@react-three/postprocessing"), "npm install @react-three/postprocessing postprocessing   (in your R3F project)", ["node"]),
    95: ("Tweakpane", ("npm", "tweakpane"), "npm install tweakpane", ["node"]),
    96: ("EffectCraft", ("tool", "effectcraft-cli"), "download from https://github.com/storytold/effectcraft/releases/latest", []),
    97: ("Openverse (free-sound)", ("kit", "free-sound"), "built in: openverse_audio.py in top30-motion", ["python"]),
    98: ("librosa (beat-cues)", ("py", "librosa"), "python3 -m pip install --user librosa   (or uv run --with librosa ...)", ["python"]),
    99: ("WhisperX", ("tool", "whisperx"), "uv tool install whisperx", ["uv", "ffmpeg"]),
    100: ("Remotion skills", ("skill", "remotion-best-practices"), "npx -y skills add remotion-dev/skills -g -a claude-code -y", ["node"]),
    101: ("FFmpeg", ("tool", "ffmpeg"), "brew install ffmpeg   (Linux: sudo apt install ffmpeg)", ["ffmpeg"]),
}

KIT = {
    "beat-cues": "beat_cues.py analyze track.mp3 --fps 30 --out cues.json",
    "word-captions": "captions.py build voiceover.json --preset social --out captions.ass",
    "free-sound": "openverse_audio.py search \"<mood>\" --category music --use commercial,modify",
    "ship-video": "ship.py run --in film.mp4 --preset reels --subs captions.ass",
}

# job: (what it is, first choice items, alternatives, kit skills)
JOBS = {
    "copy": ("Rebuild an animation you saw (site, recording, gif, Lottie) and prove the copy matches",
             [84], [85], []),
    "ui-motion": ("Timing, easing and choreography for interface animation", [85], [90], []),
    "explainer": ("A short explainer animation from code", [87, 100], [86, 88, 91], ["word-captions", "free-sound", "ship-video"]),
    "math": ("Formulas, graphs and geometry that transform", [91], [87], ["word-captions", "ship-video"]),
    "launch-film": ("A launch or update film for a product, cut to music", [89, 100], [86, 90], ["beat-cues", "word-captions", "ship-video"]),
    "polish": ("Make an AI-made film look designed, with measured gates", [90], [85], ["ship-video"]),
    "styles": ("Pick a motion style and copy its prompt and source", [86], [87, 88], ["ship-video"]),
    "art": ("Paintings or drawings that move", [87, 88], [86], ["free-sound", "ship-video"]),
    "3d": ("Model, rig, animate and render in Blender", [92], [93], ["ship-video"]),
    "web-vfx": ("Particles, bloom and live tuning in a three.js / React Three Fiber scene", [93, 94, 95], [], []),
    "composite": ("Layer, keyframe and composite like After Effects, scriptable over MCP", [96], [101], ["ship-video"]),
    "beat": ("Cut and animate on the music's beat", [98], [], ["beat-cues"]),
    "captions": ("Word-timed captions from a voiceover", [99], [100], ["word-captions"]),
    "sound": ("Music and sound effects you may use, with credits", [97], [], ["free-sound"]),
    "ship": ("Turn frames or a render into a platform-ready file and check it", [101], [], ["ship-video"]),
}


def run(cmd, timeout=15):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr)
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""


def version(out):
    m = re.search(r"(\d+\.\d+(?:\.\d+)?)", out or "")
    return m.group(1) if m else None


def chrome():
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"):
        if shutil.which(name):
            return shutil.which(name)
    for p in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              "/Applications/Chromium.app/Contents/MacOS/Chromium"):
        if Path(p).exists():
            return p
    env = os.environ.get("CHROME_PATH") or os.environ.get("MG_CHROME")
    if env and Path(env).exists():
        return env
    hits = glob.glob(str(HOME / ".cache/ms-playwright/chromium*")) + glob.glob(str(HOME / "Library/Caches/ms-playwright/chromium*"))
    return hits[0] if hits else None


def blender():
    if shutil.which("blender"):
        return shutil.which("blender")
    p = "/Applications/Blender.app/Contents/MacOS/Blender"
    return p if Path(p).exists() else None


def tools():
    t = {}

    def tool(key, exe, args=("--version",), minimum=None):
        path = exe if exe and os.path.sep in str(exe) else (shutil.which(exe) if exe else None)
        if not path:
            t[key] = {"ok": False, "version": None, "path": None}
            return
        rc, out = run([path, *args])
        v = version(out)
        ok = rc == 0 or bool(v)
        if ok and minimum and v:
            ok = tuple(int(x) for x in v.split(".")[:2]) >= minimum
        t[key] = {"ok": ok, "version": v, "path": path, **({"minimum": ".".join(map(str, minimum))} if minimum else {})}

    tool("node", "node", ("--version",), (22, 0))
    tool("bun", "bun", ("--version",), (1, 1))
    tool("uv", "uv", ("--version",))
    tool("python", sys.executable, ("--version",), (3, 11))
    tool("git", "git", ("--version",))
    tool("ffmpeg", "ffmpeg", ("-version",), (6, 0))
    tool("ffprobe", "ffprobe", ("-version",))
    tool("claude", "claude", ("--version",))
    tool("manim", "manim", ("--version",))
    tool("whisperx", "whisperx", ("--help",))
    tool("effectcraft-cli", "effectcraft-cli", ("--version",))
    tool("latex", "latex", ("--version",))
    b = blender()
    tool("blender", b, ("--version",), (5, 2)) if b else t.setdefault("blender", {"ok": False, "version": None, "path": None})
    c = chrome()
    t["chrome"] = {"ok": bool(c), "version": None, "path": c}
    if t["ffmpeg"]["path"]:
        _, filt = run(["ffmpeg", "-hide_banner", "-filters"])
        _, enc = run(["ffmpeg", "-hide_banner", "-encoders"])
        t["ffmpeg"]["features"] = {
            "libass (burn captions)": " subtitles " in filt,
            "loudnorm": " loudnorm " in filt,
            "libx264": "libx264" in enc,
            "libvpx-vp9": "libvpx-vp9" in enc,
            "libopus": "libopus" in enc,
        }
    rc, _ = run([sys.executable, "-c", "import librosa"], timeout=60)
    t["librosa"] = {"ok": rc == 0, "version": None, "path": None}
    return t


def plugins():
    if not shutil.which("claude"):
        return None
    rc, out = run(["claude", "plugin", "list"], timeout=30)
    return out if rc == 0 else None


def installed(n, plugin_list=None, cwd=None):
    kind, ref = ITEMS[n][1]
    if kind == "skill":
        return (SKILLS / ref / "SKILL.md").exists() or (Path(cwd or ".") / ".claude/skills" / ref / "SKILL.md").exists()
    if kind == "plugin":
        return bool(plugin_list and ref in plugin_list)
    if kind == "dir":
        return (HOME / ref).exists()
    if kind == "tool":
        return bool(shutil.which(ref)) or (ref == "effectcraft-cli" and Path("/Applications/EffectCraft.app").exists())
    if kind == "npm":
        for base in (Path(cwd or "."), HOME / "motion-lab"):
            if (base / "node_modules" / ref).exists():
                return True
        return False
    if kind == "py":
        return run([sys.executable, "-c", f"import {ref}"], timeout=60)[0] == 0
    if kind == "kit":
        return (Path(__file__).resolve().parents[2] / ref).exists()
    return False


def skills_state(cwd=None):
    pl = plugins()
    return {n: {"name": ITEMS[n][0], "installed": installed(n, pl, cwd), "install": ITEMS[n][2]} for n in ITEMS}


def plan(job, tl=None, st=None):
    if job not in JOBS:
        sys.exit(f"unknown job {job!r}; try: {', '.join(JOBS)}")
    what, first, alts, kit = JOBS[job]
    tl = tl or tools()
    st = st or skills_state()
    rows = []
    for n in first + alts:
        needs = ITEMS[n][3]
        missing = [x for x in needs if not tl.get(x, {}).get("ok")]
        rows.append({"n": n, "name": ITEMS[n][0], "role": "use" if n in first else "alternative",
                     "installed": st[n]["installed"], "missing_tools": missing,
                     "install": None if st[n]["installed"] else ITEMS[n][2]})
    return {"job": job, "what": what, "items": rows, "kit": [{"skill": k, "run": KIT[k]} for k in kit]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("tools", "skills"):
        s = sub.add_parser(name)
        s.add_argument("--json", action="store_true")
    p = sub.add_parser("plan")
    p.add_argument("job")
    p.add_argument("--json", action="store_true")
    sub.add_parser("jobs")
    o = ap.parse_args(argv)

    if o.cmd == "jobs":
        for k, v in JOBS.items():
            print(f"{k:12s} {v[0]}")
    elif o.cmd == "tools":
        t = tools()
        if o.json:
            print(json.dumps(t, indent=1))
            return
        for k, v in t.items():
            mark = "ok  " if v["ok"] else "--  "
            extra = f" (need {v['minimum']}+)" if not v["ok"] and v.get("minimum") and v.get("version") else ""
            print(f"{mark}{k:16s} {v.get('version') or ''}{extra}")
            for f, ok in (v.get("features") or {}).items():
                print(f"      {'ok' if ok else 'NO'}  {f}")
    elif o.cmd == "skills":
        s = skills_state()
        if o.json:
            print(json.dumps(s, indent=1))
            return
        for n, v in s.items():
            print(f"{'ok  ' if v['installed'] else '--  '}{n:3d} {v['name']}")
    elif o.cmd == "plan":
        r = plan(o.job)
        if o.json:
            print(json.dumps(r, indent=1))
            return
        print(f"{r['job']}: {r['what']}")
        for it in r["items"]:
            state = "installed" if it["installed"] else "not installed"
            print(f"  {it['role']:11s} {it['n']:3d} {it['name']} ({state})")
            if it["missing_tools"]:
                print(f"              missing tools: {', '.join(it['missing_tools'])}")
            if it["install"]:
                print(f"              install: {it['install']}")
        for k in r["kit"]:
            print(f"  kit         {k['skill']}: {k['run']}")


if __name__ == "__main__":
    main()
