#!/usr/bin/env python3
"""artifact-app: plan, lint and budget a Claude artifact meant to be installed as a desktop app.

Standard library only. No network. Never installs anything.

  appkit.py plan "<what the app does>" [--json]
  appkit.py lint APP.html [--json] [--strict]
  appkit.py budget --every-min N [--claude-calls K] [--hours H] [--json]

lint exits 1 on errors (2 with --strict when there are warnings).
"""
import argparse
import json
import re
import sys
from pathlib import Path

# ------------------------------------------------------------------ plan

TIERS = ["default", "app-permissions", "full-access"]

NEEDS = [
    # (capability, tier, regex, note)
    ("notifications", "app-permissions",
     r"\b(remind\w*|alert\w*|notif\w*|deadline|due|overdue|ping|nudge|expir\w*)\b",
     "ask when the user turns reminders on, not at launch; dedupe so one event sends one notification"),
    ("menu-bar-or-tray", "app-permissions",
     r"\b(menu ?bar|tray|status item|glance|peek|at a glance|ticker)\b",
     "keep the menu bar view to one number or one line; the window holds the detail"),
    ("global-shortcut", "app-permissions",
     r"\b(shortcut|hot ?key|quick (capture|add|note)|keyboard launcher)\b",
     "pick an unusual chord and show it in the UI so the user can change it"),
    ("always-on-top", "app-permissions",
     r"\b(always on top|float\w*|overlay|pinned window|timer|stopwatch|teleprompter)\b",
     "offer a toggle; an always-on-top window that can't be unpinned is a bug"),
    ("connectors", "default",
     r"\b(calendar|e-?mail|gmail|outlook|slack|drive|docs|jira|linear|github|crm|salesforce|hubspot|notion|connector\w*)\b",
     "connector data is the user's private data; show where each number came from and when it was fetched"),
    ("claude-requests", "default",
     r"\b(summar\w*|draft\w*|classif\w*|ask claude|ai\b|explain\w*|rewrite|triage|categori[sz]\w*)\b",
     "each request counts toward the user's plan limits; run on demand or on a slow schedule, not per keystroke"),
    ("files-or-programs", "full-access",
     r"\b(files?|folders?|disk|directory|rename|delete|move files|run (a )?(program|script|command)|terminal|shell|launch apps?)\b",
     "full access can only be granted to apps you or your org made; try a file picker or drag-and-drop first, which needs no extra permission"),
]


def plan(desc):
    d = desc.lower()
    caps = []
    for name, tier, rx, note in NEEDS:
        if re.search(rx, d):
            caps.append({"capability": name, "tier": tier, "note": note})
    tier = max((c["tier"] for c in caps), key=TIERS.index, default="default")
    advice = []
    if tier == "full-access":
        advice.append("Full computer access is the highest tier. Re-scope: can the user pick files with "
                      "<input type=file> or drag-and-drop instead? If yes, stay at app-permissions or default.")
    if any(c["capability"] == "claude-requests" for c in caps):
        advice.append("Run `appkit.py budget` with your refresh interval before shipping.")
    advice.append("Every permission is granted per version; the user is asked again after each edit, so keep "
                  "requests few and explain each one in the UI.")
    advice.append("Installed apps need to be online and signed in; show a clear offline state.")
    return {"description": desc, "tier": tier, "capabilities": caps, "advice": advice}


# ------------------------------------------------------------------ lint

ALLOWED_SCRIPT_HOSTS = ("cdnjs.cloudflare.com", "cdn.jsdelivr.net", "unpkg.com", "cdn.tailwindcss.com", "code.jquery.com")
SECRET_RE = re.compile(r"(sk-[A-Za-z0-9_-]{16,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}|xox[abpr]-[A-Za-z0-9-]{10,}|"
                       r"\b(api[_-]?key|secret|password|token)\s*[:=]\s*['\"][^'\"]{8,}['\"])", re.I)
STORAGE_RE = re.compile(r"\b(localStorage|sessionStorage|indexedDB)\b")
TIMER_RE = re.compile(r"\b(setInterval|setTimeout)\s*\([^;]*?,\s*([\d_*\s]+)\)")
CLAUDE_RE = re.compile(r"\bwindow\.claude\b")


def line_of(text, pos):
    return text.count("\n", 0, pos) + 1


def pinned(url):
    host = re.sub(r"^https?://", "", url).split("/")[0]
    path = url.split(host, 1)[1] if host in url else ""
    if host == "cdnjs.cloudflare.com":
        return bool(re.search(r"/ajax/libs/[^/]+/\d+\.\d+(\.\d+)?[^/]*/", path))
    if host in ("cdn.jsdelivr.net", "unpkg.com"):
        return bool(re.search(r"@\d+\.\d+\.\d+", path))
    if host == "code.jquery.com":
        return bool(re.search(r"\d+\.\d+\.\d+", path))
    if host == "cdn.tailwindcss.com":
        return bool(re.search(r"/\d+\.\d+\.\d+", path))
    return False


def inside_try(js, pos):
    """True if pos sits inside a `try { ... }` block (brace scan from the nearest preceding try)."""
    for m in reversed(list(re.finditer(r"\btry\s*\{", js[:pos]))):
        depth = 0
        for ch in js[m.end() - 1:pos]:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
        if depth > 0:
            return True
    return False


def guarded(js, pos):
    """window.claude use is guarded by optional chaining or a nearby existence check."""
    after = js[pos:pos + 16]
    if after.startswith("window.claude?."):
        return True
    window = js[max(0, pos - 400):pos]
    if re.search(r"(if\s*\(\s*!?\s*|typeof\s+|\(\s*)$", window) and re.match(r"window\.claude\s*(\)|&&|\?\?|\|\||===|!==)", js[pos:pos + 24]):
        return True  # this occurrence is the check itself
    return bool(re.search(r"(if\s*\(\s*!?\s*window\.claude|typeof\s+window\.claude|window\.claude\s*&&|\"claude\"\s+in\s+window|'claude'\s+in\s+window)", window))


def css_blocks(html):
    return "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", html, re.S | re.I))


def js_blocks(html):
    return [(m.start(1), m.group(1)) for m in re.finditer(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S | re.I)]


def lint_html(html, size_bytes=None):
    f = []

    def add(rule, sev, line, msg, fix):
        f.append({"rule": rule, "severity": sev, "line": line, "message": msg, "fix": fix})

    size = size_bytes if size_bytes is not None else len(html.encode("utf-8"))
    css = css_blocks(html)

    # A01 title
    m = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
    if not m or not m.group(1).strip():
        add("A01", "error", 1, "no <title>; it becomes the app's name", "add a 2-4 word name, e.g. <title>Chargeback Clock</title>")
    else:
        t = m.group(1).strip()
        n = len(t.split())
        if n > 4 or n < 2 and len(t) > 18 or ":" in t:
            add("A01", "warning", line_of(html, m.start()), f"title '{t}' is not a short app name",
                "use a 2-4 word name with no subtitle; put the explanation in the description")
    # A02 viewport
    if not re.search(r"<meta[^>]+name=[\"']viewport", html, re.I):
        add("A02", "warning", 1, "no viewport meta", "add <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">")
    # A03-A05 theming
    if not re.search(r":root\s*\{[^}]*--[\w-]+\s*:", css):
        add("A03", "warning", 1, "no color tokens on :root", "define --bg, --ink, --accent etc. on :root and use var() everywhere")
    if "prefers-color-scheme" not in css:
        add("A04", "warning", 1, "no dark mode", "redefine the tokens under @media (prefers-color-scheme: dark) and :root[data-theme=\"dark\"]")
    elif "data-theme" not in css:
        add("A04", "info", 1, "dark mode follows the OS only", "also support :root[data-theme=\"dark\"] and [data-theme=\"light\"] overrides")
    if not re.search(r"\bbody\s*\{[^}]*background", css):
        add("A05", "warning", 1, "body has no explicit background", "set body{background:var(--bg)}; a window has no page behind it")

    # A06/A07 scripts
    for m in re.finditer(r"<script[^>]+src=[\"']([^\"']+)[\"']", html, re.I):
        url, ln = m.group(1), line_of(html, m.start())
        host = re.sub(r"^https?://", "", url).split("/")[0]
        if url.startswith(("http://", "https://", "//")):
            if host not in ALLOWED_SCRIPT_HOSTS:
                add("A06", "error", ln, f"script from {host}", "load scripts only from cdnjs, jsdelivr, unpkg, tailwind or jquery CDNs, or inline them")
            elif not pinned(url):
                add("A07", "error", ln, f"script version not pinned: {url}", "use an exact version, e.g. react@18.3.1; a floating version can change the installed app without a new permission prompt")
    # A08 stylesheets
    for m in re.finditer(r"<link[^>]+rel=[\"']stylesheet[\"'][^>]*>", html, re.I):
        href = re.search(r"href=[\"']([^\"']+)", m.group(0))
        if href and href.group(1).startswith(("http", "//")) and "fonts.googleapis.com" not in href.group(1):
            add("A08", "error", line_of(html, m.start()), f"external stylesheet {href.group(1)}", "inline the CSS; only Google Fonts stylesheets may load from outside")
    # A16 remote frames and fetches
    for m in re.finditer(r"<iframe[^>]+src=[\"'](https?://[^\"']+)", html, re.I):
        add("A16", "warning", line_of(html, m.start()), f"embeds {m.group(1)}",
            "parts loaded from other sites can change without a new permission prompt; inline or drop it")

    for off, js in js_blocks(html):
        base = line_of(html, off) - 1
        L = lambda p: base + line_of(js, p)
        for m in STORAGE_RE.finditer(js):
            if not inside_try(js, m.start()):
                add("A09", "warning", L(m.start()), f"{m.group(1)} used outside try/catch",
                    "wrap every storage read and write in try/catch and render correctly when it's empty or throws")
                break
        for m in CLAUDE_RE.finditer(js):
            if not guarded(js, m.start()):
                add("A10", "warning", L(m.start()), "runtime call without a guard",
                    "check the capability exists (window.claude?.x or if (window.claude)) and show a fallback when it is missing or denied")
                break
        if re.search(r"\bnew\s+Notification\b", js) and not re.search(r"Notification\.(permission|requestPermission)", js):
            add("A11", "warning", 1 + base, "sends notifications without checking permission",
                "check Notification.permission, ask from a user click, and keep working if it's denied")
        for m in re.finditer(r"\beval\s*\(|\bnew\s+Function\s*\(|document\.write\s*\(", js):
            add("A12", "error", L(m.start()), "dynamic code execution", "remove eval/new Function/document.write")
        for m in re.finditer(r"\.innerHTML\s*[+]?=\s*`[^`]*\$\{", js):
            add("A13", "warning", L(m.start()), "innerHTML built from interpolated data",
                "escape values (textContent, or an esc() helper); connector data and Claude output are untrusted")
            break
        claude_used = bool(CLAUDE_RE.search(js)) or "fetch(" in js
        for m in TIMER_RE.finditer(js):
            parts = [x for x in m.group(2).replace("_", "").replace(" ", "").split("*") if x]
            if not parts or not all(x.isdigit() for x in parts):
                continue
            ms = 1
            for x in parts:
                ms *= int(x)
            if m.group(1) == "setInterval" and isinstance(ms, (int, float)) and ms < 60000 and claude_used:
                add("A14", "warning", L(m.start()), f"polls every {ms / 1000:g}s and the app makes requests",
                    "refresh on focus or every 5-15 minutes; Claude requests count toward plan limits")
        if ("fetch(" in js or CLAUDE_RE.search(js)) and not re.search(r"\bcatch\b", js):
            add("A15", "warning", base + 1, "requests with no error handling",
                "catch failures and show an offline or retry state; installed apps need to be online")
        if not re.search(r"navigator\.onLine|['\"]offline['\"]", js) and ("fetch(" in js or CLAUDE_RE.search(js)):
            add("A15b", "info", base + 1, "no offline state", "listen for the 'offline' event and say so in the window")

    # A17 secrets
    for m in SECRET_RE.finditer(html):
        add("A17", "error", line_of(html, m.start()), "literal secret in the app", "remove it; installed apps use your Claude account and connectors, no keys")
    # A18 size
    data_uri = sum(len(x) for x in re.findall(r"data:[\w/+.-]+;base64,[A-Za-z0-9+/=]+", html))
    if size > 16 * 1024 * 1024:
        add("A18", "error", 1, f"page is {size / 1048576:.1f} MB (limit 16 MB)", "move media to the artifact's asset store or shrink it")
    elif data_uri > 5 * 1024 * 1024:
        add("A18", "warning", 1, f"{data_uri / 1048576:.1f} MB of inline data URIs", "use uploaded assets instead of base64")
    # A19 fixed widths
    if re.search(r"(?<![-\w])(min-)?width\s*:\s*([5-9]\d\d|\d{4,})px", css) and "@media" not in css and "max-width" not in css:
        add("A19", "info", 1, "fixed width over 500px with no media query",
            "windows get resized narrow; use max-width and flex/grid so it works down to 360px")
    # A20 an app that does nothing on its own: no state at all
    if not js_blocks(html):
        add("A20", "info", 1, "no script: this is a page, not an app", "fine to install, but nothing will update or remind")

    f.sort(key=lambda x: ({"error": 0, "warning": 1, "info": 2}[x["severity"]], x["line"]))
    return f


# ------------------------------------------------------------------ budget

def budget(every_min, calls=1, hours=10):
    runs = int(hours * 60 // every_min) if every_min > 0 else 0
    per_day = runs * calls
    if per_day > 200:
        verdict = "heavy: refresh on window focus or a button instead of a timer"
    elif per_day > 50:
        verdict = "moderate: fine for one person; multiply by teammates if you share it"
    else:
        verdict = "light"
    return {"every_min": every_min, "claude_calls_per_run": calls, "hours_open": hours,
            "runs_per_day": runs, "claude_calls_per_day": per_day, "verdict": verdict}


# ------------------------------------------------------------------ cli

def main(argv=None):
    ap = argparse.ArgumentParser(prog="appkit.py", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan"); p.add_argument("description"); p.add_argument("--json", action="store_true")
    p = sub.add_parser("lint"); p.add_argument("file"); p.add_argument("--json", action="store_true"); p.add_argument("--strict", action="store_true")
    p = sub.add_parser("budget"); p.add_argument("--every-min", type=float, required=True); p.add_argument("--claude-calls", type=int, default=1)
    p.add_argument("--hours", type=float, default=10); p.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    if a.cmd == "plan":
        r = plan(a.description)
        if a.json:
            print(json.dumps(r, indent=2))
        else:
            print(f"permission tier: {r['tier']}")
            for c in r["capabilities"]:
                print(f"- {c['capability']} ({c['tier']}): {c['note']}")
            for x in r["advice"]:
                print(f"note: {x}")
        return 0

    if a.cmd == "lint":
        path = Path(a.file)
        html = path.read_text(encoding="utf-8")
        f = lint_html(html, path.stat().st_size)
        errs = sum(x["severity"] == "error" for x in f)
        warns = sum(x["severity"] == "warning" for x in f)
        if a.json:
            print(json.dumps({"file": a.file, "findings": f, "errors": errs, "warnings": warns}, indent=2))
        else:
            for x in f:
                print(f"{a.file}:{x['line']}: {x['severity']} {x['rule']} {x['message']}\n    fix: {x['fix']}")
            print(f"{errs} error(s), {warns} warning(s)")
        return 1 if errs else (2 if a.strict and warns else 0)

    if a.cmd == "budget":
        r = budget(a.every_min, a.claude_calls, a.hours)
        if a.json:
            print(json.dumps(r, indent=2))
        else:
            print(f"{r['runs_per_day']} runs/day x {r['claude_calls_per_run']} = {r['claude_calls_per_day']} Claude calls/day ({r['verdict']})")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
