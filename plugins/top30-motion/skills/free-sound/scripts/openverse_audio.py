#!/usr/bin/env python3
"""Find music and sound effects you may use, download them, and keep the credits straight.

  openverse_audio.py search "calm piano" --use commercial --category music --min-sec 20 --max-sec 90
  openverse_audio.py fetch <id> [<id> ...] --use commercial --dir audio/
  openverse_audio.py credits --dir audio/            rebuild CREDITS.md from audio/credits.json
  openverse_audio.py license by-nc-sa                what a licence allows

Searches Openverse (api.openverse.org), WordPress's index of openly licensed media. Works
without a key at a low anonymous rate; set OPENVERSE_TOKEN to an access token for more.
--use decides what is allowed: commercial (no NC), modify (no ND: you will cut, loop or
mix it, which a film always does), any. The default is commercial,modify. fetch refuses a
file whose licence doesn't allow your use, and every download is recorded with its
title, creator, source and licence for the credits. Standard library only.
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = os.environ.get("OPENVERSE_API", "https://api.openverse.org/v1").rstrip("/")
UA = "top30-motion-free-sound/0.1 (+https://github.com/venkatesanps/top30ongithub)"

LICENSES = {
    "cc0": "CC0 (public domain dedication)",
    "pdm": "Public Domain Mark",
    "by": "CC BY", "by-sa": "CC BY-SA", "by-nd": "CC BY-ND", "by-nc": "CC BY-NC",
    "by-nc-sa": "CC BY-NC-SA", "by-nc-nd": "CC BY-NC-ND",
    "sampling+": "CC Sampling+", "nc-sampling+": "CC NC Sampling+",
}


def allows(code):
    code = code.lower()
    sampling = "sampling" in code
    return {
        "commercial": "nc" not in code.split("-") and not code.startswith("nc-"),
        "modify": "nd" not in code.split("-"),
        "credit": code not in ("cc0", "pdm"),
        "share_alike": "sa" in code.split("-"),
        "check": sampling,  # retired Sampling licences: read the deed before using
    }


def permitted(code, use):
    a = allows(code)
    reasons = []
    if "commercial" in use and not a["commercial"]:
        reasons.append("non-commercial only (NC)")
    if "modify" in use and not a["modify"]:
        reasons.append("no edits allowed (ND), and a film cuts, loops or mixes its audio")
    if a["check"]:
        reasons.append("a retired Sampling licence: read the deed before using")
    return (not reasons), reasons


def get(url, binary=False):
    headers = {"User-Agent": UA}
    tok = os.environ.get("OPENVERSE_TOKEN")
    if tok and url.startswith(API):
        headers["Authorization"] = f"Bearer {tok}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        if e.code == 429:
            sys.exit("Openverse rate limit reached (anonymous requests are limited). Wait, or set OPENVERSE_TOKEN.")
        sys.exit(f"HTTP {e.code} from {url}: {e.read()[:300]!r}")
    except urllib.error.URLError as e:
        sys.exit(f"could not reach {url}: {e.reason}")
    return data if binary else json.loads(data)


def use_set(s):
    return {"any": set(), "": set()}.get(s, set(x.strip() for x in s.split(",") if x.strip()))


def search(q, use, category=None, length=None, ext=None, min_sec=None, max_sec=None, page_size=20, source=None):
    params = {"q": q, "page_size": page_size, "mature": "false"}
    lt = (["commercial"] if "commercial" in use else []) + (["modification"] if "modify" in use else [])
    if lt:
        params["license_type"] = ",".join(lt)
    if category:
        params["category"] = category
    if length:
        params["length"] = length
    if ext:
        params["extension"] = ext
    if source:
        params["source"] = source
    data = get(f"{API}/audio/?{urllib.parse.urlencode(params)}")
    rows = []
    for r in data.get("results", []):
        sec = (r.get("duration") or 0) / 1000.0  # Openverse gives milliseconds
        if min_sec is not None and sec and sec < min_sec:
            continue
        if max_sec is not None and sec and sec > max_sec:
            continue
        ok, why = permitted(r.get("license", ""), use)
        if not ok:
            continue
        rows.append({"id": r["id"], "title": r.get("title") or "(untitled)", "creator": r.get("creator") or "unknown",
                     "license": r.get("license"), "license_version": r.get("license_version"),
                     "seconds": round(sec, 1), "filetype": r.get("filetype"), "source": r.get("source"),
                     "page": r.get("foreign_landing_url"), "url": r.get("url")})
    return rows, data.get("result_count")


def slug(s, n=40):
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s or "").strip("-").lower()
    return (s[:n].rstrip("-") or "audio")


def attribution(e):
    """TASL: title, author, source, licence."""
    lic = LICENSES.get(e["license"], e["license"].upper())
    ver = f" {e['license_version']}" if e.get("license_version") and e["license"] not in ("cc0", "pdm") else ""
    who = f" by {e['creator']}" if e.get("creator") and e["creator"] != "unknown" else ""
    return f"\"{e['title']}\"{who}, from {e.get('source') or 'Openverse'} ({e.get('page') or e.get('url')}), {lic}{ver}" + \
        (f" ({e['license_url']})" if e.get("license_url") else "")


def write_credits(d):
    d = Path(d)
    db = d / "credits.json"
    entries = json.loads(db.read_text()) if db.exists() else []
    lines = ["# Audio credits", "",
             "Generated by openverse_audio.py from credits.json. Put the lines marked 'credit required' in the",
             "video description or end card. Licences are per file; keep this file with the project.", ""]
    for e in entries:
        a = allows(e["license"])
        tag = "credit required" if a["credit"] else "no credit required (credit anyway if you can)"
        sa = "; share-alike: a work that adapts it must use the same licence" if a["share_alike"] else ""
        lines.append(f"- `{e['file']}`: {attribution(e)}. {tag}{sa}.")
    (d / "CREDITS.md").write_text("\n".join(lines) + "\n")
    return entries


def fetch(ids, use, d):
    d = Path(d)
    d.mkdir(parents=True, exist_ok=True)
    db = d / "credits.json"
    entries = json.loads(db.read_text()) if db.exists() else []
    have = {e["id"] for e in entries}
    done, refused = [], []
    for i in ids:
        r = get(f"{API}/audio/{urllib.parse.quote(i)}/")
        ok, why = permitted(r.get("license", ""), use)
        if not ok:
            refused.append((i, r.get("title"), why))
            continue
        ext = (r.get("filetype") or Path(urllib.parse.urlparse(r["url"]).path).suffix.lstrip(".") or "mp3").lower()
        name = f"{slug(r.get('title'))}-{i[:8]}.{ext}"
        (d / name).write_bytes(get(r["url"], binary=True))
        e = {"id": i, "file": name, "title": r.get("title") or "(untitled)", "creator": r.get("creator") or "unknown",
             "creator_url": r.get("creator_url"), "license": r.get("license"), "license_version": r.get("license_version"),
             "license_url": r.get("license_url"), "source": r.get("source"), "page": r.get("foreign_landing_url"),
             "url": r.get("url"), "seconds": round((r.get("duration") or 0) / 1000.0, 1),
             "openverse_attribution": r.get("attribution")}
        entries = [x for x in entries if x["id"] != i] + [e]
        done.append(e)
    db.write_text(json.dumps(entries, indent=1, ensure_ascii=False) + "\n")
    write_credits(d)
    return done, refused, have


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search")
    s.add_argument("query")
    s.add_argument("--use", default="commercial,modify", help="commercial, modify, both comma-separated, or any")
    s.add_argument("--category", choices=["music", "sound_effect", "podcast", "audiobook", "news", "pronunciation"])
    s.add_argument("--length", choices=["shortest", "short", "medium", "long"])
    s.add_argument("--ext", help="e.g. mp3,wav,flac,ogg")
    s.add_argument("--source", help="e.g. freesound,jamendo,wikimedia_audio,ccmixter")
    s.add_argument("--min-sec", type=float)
    s.add_argument("--max-sec", type=float)
    s.add_argument("--page-size", type=int, default=20)
    s.add_argument("--json", action="store_true")
    f = sub.add_parser("fetch")
    f.add_argument("ids", nargs="+")
    f.add_argument("--use", default="commercial,modify")
    f.add_argument("--dir", default="audio")
    c = sub.add_parser("credits")
    c.add_argument("--dir", default="audio")
    li = sub.add_parser("license")
    li.add_argument("code")
    o = ap.parse_args(argv)

    if o.cmd == "search":
        use = use_set(o.use)
        rows, total = search(o.query, use, o.category, o.length, o.ext, o.min_sec, o.max_sec, o.page_size, o.source)
        if o.json:
            print(json.dumps(rows, indent=1, ensure_ascii=False))
            return
        if not rows:
            print("nothing that fits; try other words, drop --length or widen --min-sec/--max-sec")
            return
        print(f"{len(rows)} usable for {o.use} (of {total} matching):")
        for r in rows:
            lic = (r["license"] or "?").upper() + (f" {r['license_version']}" if r.get("license_version") else "")
            print(f"{r['id']}  {r['seconds']:>6}s  {lic:14s} {r['title'][:46]:46s} {r['creator'][:24]:24s} {r['source']}")
        print("listen first at each page link (--json shows them), then: openverse_audio.py fetch <id> ...")
    elif o.cmd == "fetch":
        done, refused, _ = fetch(o.ids, use_set(o.use), o.dir)
        for e in done:
            print(f"saved {Path(o.dir) / e['file']}  [{e['license']}]")
        for i, t, why in refused:
            print(f"refused {i} ({t}): {'; '.join(why)}", file=sys.stderr)
        print(f"credits: {Path(o.dir) / 'CREDITS.md'}")
        if refused:
            sys.exit(1)
    elif o.cmd == "credits":
        n = len(write_credits(o.dir))
        print(f"wrote {Path(o.dir) / 'CREDITS.md'} ({n} file(s))")
    elif o.cmd == "license":
        a = allows(o.code)
        print(f"{LICENSES.get(o.code.lower(), o.code)}: commercial use {'yes' if a['commercial'] else 'NO'}, "
              f"edits {'yes' if a['modify'] else 'NO'}, credit {'required' if a['credit'] else 'not required'}"
              f"{', share-alike' if a['share_alike'] else ''}{', retired licence: read the deed' if a['check'] else ''}")


if __name__ == "__main__":
    main()
