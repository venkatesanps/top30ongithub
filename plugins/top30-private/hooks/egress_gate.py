#!/usr/bin/env python3
"""egress gate: a PreToolUse hook that stops for approval before anything leaves the machine.

The rule it enforces: nothing is sent to an outside service without the user's approval,
and no personal data (PII) goes out at all unless the user approves that specific call.

  Bash / PowerShell   commands that upload, post, push, publish, mail or copy to a remote
                      host -> "ask" (with the reason). Plain downloads (curl/wget GET) pass,
                      unless the URL itself carries personal data.
  Skill               skills known to send work to another provider or post publicly
                      (ECC's astra-review, social-publisher, x-api, email-ops, ito-*, ...) -> "ask".
  WebFetch / WebSearch / mcp__*
                      "ask" only when the request carries personal data or a secret
                      (emails, SSNs, card numbers, phone numbers, cloud keys, private keys).

It never blocks outright and never sends anything itself: a person decides. Standard library
only, no network, finishes in milliseconds.

Controls (all optional):
  TOP30_EGRESS_GATE=off                     switch the gate off for one session
  ~/.config/top30-private/allow.txt         one regex per line; a Bash command that matches
                                            is treated as pre-approved (e.g. ^git push origin )
  ~/.config/top30-private/pii-allow.txt     one regex per line; matching strings are not PII
                                            (e.g. your own git email)

Usage:
  egress_gate.py hook           read the hook JSON on stdin (what hooks.json runs)
  egress_gate.py check "<cmd>"  explain the decision for a shell command (for testing)
"""
import json
import os
import re
import sys
from pathlib import Path

CONFIG = Path(os.environ.get("TOP30_PRIVATE_CONFIG", Path.home() / ".config" / "top30-private"))

LOCAL_HOST = re.compile(
    r"^(localhost|127(\.\d{1,3}){3}|0\.0\.0\.0|\[?::1\]?|host\.docker\.internal|[a-z0-9-]+\.local|[a-z0-9-]+\.localhost)$",
    re.I,
)

# ---------- personal data and secrets ----------

PII_PATTERNS = [
    ("email address", re.compile(r"(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}(?![\w-])")),
    ("US Social Security number", re.compile(r"(?<!\d)(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}(?!\d)")),
    ("phone number", re.compile(r"(?<![\w-])(\+1[ .-]?)?\(?[2-9]\d{2}\)?[ .-]\d{3}[ .-]\d{4}(?![\w-])")),
    ("AWS access key", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("API token", re.compile(r"\b(sk-(ant-)?[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|xox[abpr]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{35})\b")),
]
CARD = re.compile(r"(?<![\d-])(?:\d[ -]?){13,19}(?![\d-])")
# Addresses that identify a service or a placeholder, not a person.
NOT_PERSONAL_EMAIL = re.compile(
    r"(^|[.@])(example\.(com|org|net)|users\.noreply\.github\.com|noreply\.[a-z.]+|localhost)$|^(noreply|no-reply|git|user|you|me|name)@",
    re.I,
)


def _luhn(digits):
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
        alt = not alt
    return total % 10 == 0


def _allow_patterns(name):
    p = CONFIG / name
    out = []
    try:
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                try:
                    out.append(re.compile(line))
                except re.error:
                    pass
    except OSError:
        pass
    return out


def find_pii(text):
    """Return a sorted list of the kinds of personal data or secrets found in text."""
    if not text:
        return []
    allow = _allow_patterns("pii-allow.txt")
    found = set()
    for kind, rx in PII_PATTERNS:
        for m in rx.finditer(text):
            s = m.group(0)
            if any(a.search(s) for a in allow):
                continue
            if kind == "email address" and NOT_PERSONAL_EMAIL.search(s):
                continue
            found.add(kind)
            break
    for m in CARD.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and len(set(digits)) > 1 and _luhn(digits):
            found.add("payment card number")
            break
    return sorted(found)


# ---------- outbound shell commands ----------

def _hosts(cmd):
    return [h.lower() for h in re.findall(r"\b(?:https?|ftp|wss?)://([^/\s:'\"?#]+)", cmd)]


def _remote(hosts):
    return [h for h in hosts if not LOCAL_HOST.match(h)]


# A program name in command position: start of a segment, after env assignments, sudo, env, time...
CMD = r"^(?:\w+=\S*\s+|sudo\s+(?:-\S+\s+)*|env\s+|time\s+|nohup\s+|exec\s+)*"

SEND_RULES = [
    # (reason, regex). Each regex is searched against one shell segment.
    ("uploads data with curl", re.compile(
        r"\bcurl\b.*(\s(-d|--data(-raw|-binary|-urlencode)?|-F|--form|-T|--upload-file|--json)(\s|=)|\s-X\s*(POST|PUT|PATCH|DELETE)\b|--request\s+(POST|PUT|PATCH|DELETE)\b)", re.I)),
    ("uploads data with wget", re.compile(r"\bwget\b.*--(post-data|post-file|body-data|body-file|method=(POST|PUT|PATCH))", re.I)),
    ("sends an HTTP request with a body", re.compile(r"\b(http|https|xh|httpie)\s+(POST|PUT|PATCH|DELETE)\b", re.I)),
    ("posts from a script (requests/httpx/fetch)", re.compile(
        r"\b(requests|httpx|session|client)\.(post|put|patch)\(|\bmethod\s*[:=]\s*['\"](POST|PUT|PATCH)['\"]", re.I)),
    ("pushes code to a remote", re.compile(r"\bgit\s+(-C\s+\S+\s+)?push\b")),
    ("creates or changes something on GitHub", re.compile(
        r"\bgh\s+((pr|issue)\s+(create|comment|edit|close|merge|review)|gist\s+create|release\s+(create|upload)|repo\s+(create|edit)|api\b.*(-X\s*(POST|PUT|PATCH|DELETE)|--method\s+(POST|PUT|PATCH|DELETE)|\s-[fF]\s))")),
    ("publishes a package", re.compile(r"\b(npm|pnpm|yarn|bun)\s+publish\b|\btwine\s+upload\b|\b(uv|poetry|hatch)\s+publish\b|\bgem\s+push\b|\bcargo\s+publish\b")),
    ("pushes a container image", re.compile(r"\b(docker|podman|buildah)\s+push\b")),
    ("copies files to cloud storage", re.compile(
        r"\baws\s+s3\s+(cp|sync|mv)\b.*\ss3://|\bgsutil\s+(-m\s+)?(cp|rsync|mv)\b.*\sgs://|\bgcloud\s+storage\s+(cp|rsync)\b.*\sgs://|\baz\s+storage\s+blob\s+upload|\brclone\s+(copy|sync|move)\b")),
    ("copies files to another machine", re.compile(CMD + r"((scp|rsync)\b.*\s[\w.-]+@?[\w.-]+:\S*|(sftp|ftp)\s)")),
    ("opens a remote shell", re.compile(CMD + r"ssh\s+(-\S+\s+)*[\w.-]+@[\w.-]+")),
    ("opens a raw network connection", re.compile(CMD + r"(nc|ncat|netcat|socat|telnet)\s+(?!-l)")),
    ("sends email", re.compile(CMD + r"(sendmail|mailx?|mutt|msmtp|swaks)\b")),
    ("sends work to OpenAI through the Codex CLI", re.compile(r"\bcodex\s+(exec|review|e\b|-p\b|--prompt\b)|\bcodex\s+\"")),
    ("uses ECC's external compute service (Ito)", re.compile(r"\b(ecc|ecc-universal)\b.*\bito\b")),
    ("signs in to or syncs with cmem.ai", re.compile(
        r"\bclaude-mem\b.*\b(login|signin|sign-in|cloud|sync|teambrain|pro|connect)\b|\bclaude-mem\b.*\btelemetry\s+enable\b")),
    ("installs claude-mem with its online sign-in", re.compile(r"\bclaude-mem(@\S+)?\s+install\b(?!.*(--provider|CLAUDE_MEM_ONLINE_OPTIN=false))")),
    ("switches claude-mem telemetry on", re.compile(r"\bCLAUDE_MEM_TELEMETRY=(1|true|on)\b", re.I)),
]

SPLIT = re.compile(r"\s*(?:&&|\|\||;|\n|\|(?!\|))\s*")


def check_command(cmd):
    """Return (reasons, pii) for a shell command. Empty reasons and pii means it may run."""
    cmd = cmd or ""
    for rx in _allow_patterns("allow.txt"):
        if rx.search(cmd):
            return [], []
    reasons = []
    for seg in SPLIT.split(cmd):
        if not seg:
            continue
        for why, rx in SEND_RULES:
            if rx.search(seg):
                # A curl/wget that only talks to localhost isn't leaving the machine.
                if why.startswith(("uploads data", "sends an HTTP", "posts from")):
                    hosts = _hosts(seg)
                    if hosts and not _remote(hosts):
                        continue
                if why not in reasons:
                    reasons.append(why)
    pii = []
    remote = _remote(_hosts(cmd))
    if reasons or remote:
        pii = find_pii(cmd)
    return reasons, pii


# ---------- skills ----------

OUTBOUND_SKILLS = {
    "astra-review": "sends your diff to OpenAI (GPT via the Codex CLI)",
    "council-multi-model": "sends the prompt to several outside model providers",
    "social-publisher": "posts to social networks",
    "x-api": "posts to X (Twitter)",
    "email-ops": "sends email",
    "mailtrap-email-integration": "sends email through Mailtrap",
}
OUTBOUND_SKILL_PREFIXES = {
    "ito-": "uses ECC's external compute service (Ito)",
    "multi-": "sends work to other model providers (ECC multi-* workflow)",
}


def check_skill(name):
    base = (name or "").split(":")[-1].strip().lstrip("/")
    if base in OUTBOUND_SKILLS:
        return OUTBOUND_SKILLS[base]
    for pre, why in OUTBOUND_SKILL_PREFIXES.items():
        if base.startswith(pre):
            return why
    return None


# ---------- hook ----------

def decide(event):
    """Return (decision, reason) for a PreToolUse event. decision is None (allow) or 'ask'."""
    tool = event.get("tool_name", "")
    ti = event.get("tool_input") or {}
    if tool in ("Bash", "PowerShell"):
        reasons, pii = check_command(ti.get("command", ""))
        if pii:
            return "ask", (f"egress gate: this command would send personal data or secrets outside ({', '.join(pii)})"
                           + (f" and {'; '.join(reasons)}" if reasons else "") + ". Approve only if that is intended.")
        if reasons:
            return "ask", f"egress gate: this command {'; '.join(reasons)}. Nothing leaves the machine without your approval."
        return None, ""
    if tool == "Skill":
        why = check_skill(ti.get("skill") or ti.get("command") or ti.get("name") or "")
        if why:
            return "ask", f"egress gate: this skill {why}. Approve to continue."
        return None, ""
    if tool in ("WebFetch", "WebSearch") or tool.startswith("mcp__"):
        pii = find_pii(json.dumps(ti, ensure_ascii=False))
        if pii:
            where = {"WebFetch": "a web request", "WebSearch": "a web search"}.get(tool, f"the {tool.split('__')[1] if '__' in tool else tool} connector")
            return "ask", f"egress gate: {where} would carry personal data or secrets ({', '.join(pii)}). Approve only if that is intended."
    return None, ""


def hook():
    if os.environ.get("TOP30_EGRESS_GATE", "").lower() in ("off", "0", "false"):
        return 0
    try:
        event = json.load(sys.stdin)
    except Exception:
        return 0  # never break a session over unreadable input
    decision, reason = decide(event)
    if decision:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }}))
    return 0


def main(argv):
    if not argv or argv[0] == "hook":
        return hook()
    if argv[0] == "check" and len(argv) > 1:
        reasons, pii = check_command(" ".join(argv[1:]))
        print(json.dumps({"ask": bool(reasons or pii), "reasons": reasons, "pii": pii}))
        return 0
    if argv[0] == "pii" and len(argv) > 1:
        print(json.dumps(find_pii(" ".join(argv[1:]))))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
