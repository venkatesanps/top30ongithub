#!/usr/bin/env python3
"""Word-timed captions from WhisperX (or any word list) into SRT, VTT, ASS karaoke or Remotion JSON.

  captions.py build voiceover.json --preset social --out captions.ass
  captions.py build voiceover.json --preset subtitle --out captions.srt
  captions.py build voiceover.json --out captions.remotion.json      # @remotion/captions Caption[]
  captions.py check captions.srt --preset subtitle                    # reading speed, length, gaps

Input: WhisperX JSON (segments[].words[] with word/start/end/score; words WhisperX could not
align, often numbers, have no times and are filled in from their neighbours), Remotion
Caption[] JSON, or {"words": [{"word"|"text", "start", "end"}]}.
Output format comes from the --out extension (.srt .vtt .ass .json), or --format.
Presets: social (1-2 short lines, a few words at a time, for 9:16 video), subtitle (broadcast-
style: 2 lines of up to 42 characters, 17 characters a second), karaoke (subtitle grouping,
each word lit as it is spoken). Standard library only.
"""
import argparse
import json
import re
import sys
from pathlib import Path

PRESETS = {
    "social": dict(max_chars=18, max_lines=2, max_dur=2.0, min_dur=0.5, pause=0.35, cps=22, max_words=4),
    "subtitle": dict(max_chars=42, max_lines=2, max_dur=6.0, min_dur=1.0, pause=0.6, cps=17, max_words=99),
    "karaoke": dict(max_chars=32, max_lines=2, max_dur=4.0, min_dur=0.8, pause=0.5, cps=20, max_words=99),
}
SENT_END = re.compile(r"[.!?…。！？]$")
CLAUSE_END = re.compile(r"[,;:—–]$")
GAP = 0.08  # seconds kept clear between cues so players never show two at once


# ---------- reading input ----------
def load_words(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    raw = []
    if isinstance(data, dict) and "segments" in data:
        for seg in data["segments"]:
            ws = seg.get("words")
            if ws:
                raw += [{"text": w.get("word", ""), "start": w.get("start"), "end": w.get("end"),
                         "score": w.get("score")} for w in ws]
            elif seg.get("text"):  # unaligned segment: spread its words evenly
                toks = seg["text"].split()
                s0, s1 = float(seg["start"]), float(seg["end"])
                step = (s1 - s0) / max(len(toks), 1)
                raw += [{"text": t, "start": s0 + i * step, "end": s0 + (i + 1) * step, "score": None}
                        for i, t in enumerate(toks)]
    elif isinstance(data, dict) and "words" in data:
        raw = [{"text": w.get("word", w.get("text", "")), "start": w.get("start"), "end": w.get("end"),
                "score": w.get("score")} for w in data["words"]]
    elif isinstance(data, list) and data and "startMs" in data[0]:
        raw = [{"text": w["text"], "start": w["startMs"] / 1000, "end": w["endMs"] / 1000,
                "score": w.get("confidence")} for w in data]
    else:
        raise SystemExit("captions.py: unrecognised input (expected WhisperX JSON, Remotion Caption[] or {words: [...]})")
    words = [w for w in raw if str(w["text"]).strip()]
    for w in words:
        w["text"] = str(w["text"]).strip()
    return fill_times(words)


def fill_times(words):
    """WhisperX leaves start/end off words it could not align. Spread them between known neighbours."""
    n = len(words)
    i = 0
    filled = 0
    while i < n:
        if words[i]["start"] is not None and words[i]["end"] is not None:
            i += 1
            continue
        j = i
        while j < n and (words[j]["start"] is None or words[j]["end"] is None):
            j += 1
        left = words[i - 1]["end"] if i > 0 else (words[j]["start"] - 0.3 * (j - i) if j < n else 0.0)
        right = words[j]["start"] if j < n else left + 0.3 * (j - i)
        left = max(left, 0.0)
        step = max(right - left, 0.0) / (j - i)
        for k in range(i, j):
            words[k]["start"] = round(left + (k - i) * step, 3)
            words[k]["end"] = round(left + (k - i + 1) * step, 3)
            words[k]["filled"] = True
            filled += 1
        i = j
    for w in words:
        w["start"], w["end"] = float(w["start"]), float(w["end"])
        if w["end"] < w["start"]:
            w["end"] = w["start"]
    if filled:
        print(f"note: {filled} word(s) had no timestamps and were placed between their neighbours", file=sys.stderr)
    return words


# ---------- grouping ----------
def text_of(ws):
    return " ".join(w["text"] for w in ws)


def split_lines(ws, max_chars, max_lines):
    """Balance words over up to max_lines lines; returns list of word lists or None if it can't fit."""
    if len(text_of(ws)) <= max_chars or max_lines == 1:
        return [ws] if len(text_of(ws)) <= max_chars or len(ws) == 1 else None
    best = None
    for cut in range(1, len(ws)):
        a, b = text_of(ws[:cut]), text_of(ws[cut:])
        if len(a) > max_chars or len(b) > max_chars:
            continue
        score = abs(len(a) - len(b)) - (6 if CLAUSE_END.search(ws[cut - 1]["text"]) else 0)
        if len(a) > len(b):
            score += 2  # prefer a bottom-heavy pyramid
        if best is None or score < best[0]:
            best = (score, cut)
    return [ws[:best[1]], ws[best[1]:]] if best else None


def fits(ws, p):
    return (split_lines(ws, p["max_chars"], p["max_lines"]) is not None
            and ws[-1]["end"] - ws[0]["start"] <= p["max_dur"] and len(ws) <= p["max_words"])


def group(words, p):
    cues, cur = [], []
    for i, w in enumerate(words):
        if cur and w["start"] - cur[-1]["end"] >= p["pause"]:
            cues.append(cur)
            cur = []
        while cur and not fits(cur + [w], p):
            # full: close at the last comma or full stop in the back half, so the next caption
            # starts a phrase instead of stranding its last word; otherwise close here
            cut = next((k for k in range(len(cur) - 2, max(len(cur) // 2 - 1, 0) - 1, -1)
                        if CLAUSE_END.search(cur[k]["text"]) or SENT_END.search(cur[k]["text"])), None)
            if cut is None:
                cues.append(cur)
                cur = []
            else:
                cues.append(cur[:cut + 1])
                cur = cur[cut + 1:]
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        if SENT_END.search(w["text"]) and nxt is not None:
            cues.append(cur)
            cur = []
    if cur:
        cues.append(cur)
    out = []
    for ws in cues:
        lines = split_lines(ws, p["max_chars"], p["max_lines"]) or [ws]
        out.append({"words": ws, "lines": lines, "start": ws[0]["start"], "end": ws[-1]["end"]})
    # minimum display time, without running into the next cue
    for k, c in enumerate(out):
        nxt = out[k + 1]["start"] if k + 1 < len(out) else None
        want = max(c["end"], c["start"] + p["min_dur"])
        if nxt is not None:
            want = min(want, nxt - GAP)
        c["end"] = round(max(want, c["end"] if nxt is None else min(c["end"], nxt - GAP)), 3)
        c["start"] = round(c["start"], 3)
    return out


# ---------- writers ----------
def ts(t, sep=","):
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def ass_ts(t):
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def lines_text(c):
    return "\n".join(text_of(l) for l in c["lines"])


def write_srt(cues):
    return "".join(f"{i}\n{ts(c['start'])} --> {ts(c['end'])}\n{lines_text(c)}\n\n" for i, c in enumerate(cues, 1))


def write_vtt(cues):
    return "WEBVTT\n\n" + "".join(f"{ts(c['start'], '.')} --> {ts(c['end'], '.')}\n{lines_text(c)}\n\n" for c in cues)


def ass_escape(t):
    return t.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def write_ass(cues, width, height, karaoke, font, highlight):
    vertical = height > width
    size = round(height * (0.055 if vertical else 0.06))
    margin_v = round(height * (0.22 if vertical else 0.07))
    # ASS colours are &HAABBGGRR
    hl = highlight.lstrip("#")
    hl_ass = f"&H00{hl[4:6]}{hl[2:4]}{hl[0:2]}".upper()
    head = (
        "[Script Info]\nScriptType: v4.00+\nWrapStyle: 2\nScaledBorderAndShadow: yes\n"
        f"PlayResX: {width}\nPlayResY: {height}\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font},{size},{hl_ass if karaoke else '&H00FFFFFF'},&H00FFFFFF,&H00000000,&H80000000,"
        f"-1,0,0,0,100,100,0,0,1,{max(2, size // 12)},0,2,{round(width * 0.08)},{round(width * 0.08)},{margin_v},1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    rows = []
    for c in cues:
        parts = []
        flat = [w for line in c["lines"] for w in line]
        nxt_start = {id(w): (flat[k + 1]["start"] if k + 1 < len(flat) else w["end"]) for k, w in enumerate(flat)}
        for li, line in enumerate(c["lines"]):
            seg = []
            for w in line:
                if karaoke:
                    # each word stays lit until the next one starts, so pauses don't let the highlight run ahead
                    dur_cs = max(1, round((nxt_start[id(w)] - w["start"]) * 100))
                    seg.append(f"{{\\kf{dur_cs}}}{ass_escape(w['text'])}")
                else:
                    seg.append(ass_escape(w["text"]))
            parts.append(" ".join(seg))
        if karaoke:
            # a gap before the first word keeps the highlight in step with speech
            lead = max(0, round((c["words"][0]["start"] - c["start"]) * 100))
            body = (f"{{\\k{lead}}}" if lead else "") + "\\N".join(parts)
        else:
            body = "\\N".join(parts)
        rows.append(f"Dialogue: 0,{ass_ts(c['start'])},{ass_ts(c['end'])},Default,,0,0,0,,{body}")
    return head + "\n".join(rows) + "\n"


def write_remotion(words):
    """@remotion/captions Caption[]: one entry per word, text with its leading space (what
    createTikTokStyleCaptions expects), times in milliseconds."""
    out = []
    for i, w in enumerate(words):
        out.append({"text": (" " if i else "") + w["text"], "startMs": round(w["start"] * 1000),
                    "endMs": round(w["end"] * 1000), "timestampMs": round((w["start"] + w["end"]) * 500),
                    "confidence": w.get("score")})
    return json.dumps(out, indent=1, ensure_ascii=False) + "\n"


# ---------- check ----------
def parse_srt_vtt(text):
    cues = []
    for block in re.split(r"\n\s*\n", text.replace("\r", "").strip()):
        m = re.search(r"(\d+:\d{2}:\d{2}[,.]\d{3})\s+-->\s+(\d+:\d{2}:\d{2}[,.]\d{3})", block)
        if not m:
            continue
        lines = block[m.end():].strip("\n").split("\n")
        cues.append({"start": parse_ts(m.group(1)), "end": parse_ts(m.group(2)), "text_lines": [l.strip() for l in lines if l.strip()]})
    return cues


def parse_ts(s):
    h, m, rest = s.replace(",", ".").split(":")
    return int(h) * 3600 + int(m) * 60 + float(rest)


def check(cues, p, fps=None):
    issues = []
    for i, c in enumerate(cues, 1):
        lines = c.get("text_lines") or [text_of(l) for l in c["lines"]]
        dur = c["end"] - c["start"]
        chars = sum(len(l) for l in lines)
        if dur <= 0:
            issues.append((i, "error", f"ends before it starts ({dur:.2f} s)"))
            continue
        if len(lines) > p["max_lines"]:
            issues.append((i, "warn", f"{len(lines)} lines (max {p['max_lines']})"))
        for l in lines:
            if len(l) > p["max_chars"]:
                issues.append((i, "warn", f"line of {len(l)} characters (max {p['max_chars']}): {l[:40]}"))
        if dur < p["min_dur"] - 0.01:
            issues.append((i, "warn", f"on screen {dur:.2f} s (min {p['min_dur']})"))
        if chars / dur > p["cps"] * 1.15:
            issues.append((i, "warn", f"{chars / dur:.0f} characters a second (aim for {p['cps']} or fewer)"))
        if i < len(cues) and cues[i]["start"] < c["end"]:
            issues.append((i, "error", f"overlaps the next caption by {c['end'] - cues[i]['start']:.2f} s"))
    return issues


# ---------- commands ----------
def cmd_build(a):
    p = dict(PRESETS[a.preset])
    for k in ("max_chars", "max_lines", "max_dur", "min_dur", "pause", "cps", "max_words"):
        v = getattr(a, k)
        if v is not None:
            p[k] = v
    words = load_words(a.input)
    if not words:
        raise SystemExit("captions.py: no words in the input")
    fmt = a.format or (Path(a.out).suffix.lstrip(".").lower() if a.out else "srt")
    if fmt == "json":
        text = write_remotion(words)
        n = len(words)
    else:
        cues = group(words, p)
        n = len(cues)
        if fmt == "srt":
            text = write_srt(cues)
        elif fmt == "vtt":
            text = write_vtt(cues)
        elif fmt == "ass":
            w, h = (int(x) for x in a.size.lower().split("x"))
            text = write_ass(cues, w, h, a.preset == "karaoke" or a.karaoke, a.font, a.highlight)
        else:
            raise SystemExit(f"captions.py: unknown format {fmt}")
        issues = check(cues, p)
        for i, lvl, msg in issues:
            print(f"cue {i}: {lvl}: {msg}", file=sys.stderr)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
        print(f"wrote {a.out}: {n} {'words' if fmt == 'json' else 'captions'} from {len(words)} words")
    else:
        sys.stdout.write(text)


def cmd_check(a):
    p = PRESETS[a.preset]
    path = Path(a.input)
    if path.suffix.lower() in (".srt", ".vtt"):
        cues = parse_srt_vtt(path.read_text(encoding="utf-8"))
    else:
        cues = group(load_words(path), p)
    issues = check(cues, p)
    for i, lvl, msg in issues:
        print(f"cue {i}: {lvl}: {msg}")
    errs = sum(1 for _, lvl, _m in issues if lvl == "error")
    warns = len(issues) - errs
    print(f"{len(cues)} captions, {errs} error(s), {warns} warning(s)")
    sys.exit(1 if errs or (a.fail_on == "warn" and warns) else 0)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("input")
    b.add_argument("--out")
    b.add_argument("--format", choices=["srt", "vtt", "ass", "json"])
    b.add_argument("--preset", choices=PRESETS, default="subtitle")
    b.add_argument("--karaoke", action="store_true", help="word highlight in ASS output with any preset")
    b.add_argument("--size", default="1080x1920", help="video size for ASS (default 1080x1920)")
    b.add_argument("--font", default="Arial")
    b.add_argument("--highlight", default="#FFD400", help="karaoke colour, #RRGGBB")
    for k, t in (("max_chars", int), ("max_lines", int), ("max_dur", float), ("min_dur", float),
                 ("pause", float), ("cps", float), ("max_words", int)):
        b.add_argument("--" + k.replace("_", "-"), dest=k, type=t)
    b.set_defaults(fn=cmd_build)
    c = sub.add_parser("check")
    c.add_argument("input")
    c.add_argument("--preset", choices=PRESETS, default="subtitle")
    c.add_argument("--fail-on", choices=["error", "warn"], default="error")
    c.set_defaults(fn=cmd_check)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
