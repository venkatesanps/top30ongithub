#!/usr/bin/env python3
"""Set up Claude-Mem (thedotmack/claude-mem) so nothing leaves the machine without approval.

  cmem_private.py plan  [options]   show what apply would change (writes nothing)
  cmem_private.py apply [options]   write the private settings (backs up each file first)
  cmem_private.py audit [--json]    check the current settings; exit 1 if anything sends data out

Options:
  --provider ollama|claude   who writes the memory notes (the "observer"). Default: ollama,
                             a local model, so tool activity never leaves the machine.
                             'claude' uses your own Anthropic plan (the vendor Claude Code
                             already talks to). Choose it only with the user's approval.
  --model NAME               Ollama model for the observer (what `ollama list` shows). Default: qwen3:8b
  --exclude GLOB             a project path claude-mem must never record (repeatable), e.g. ~/work/**
  --data-dir PATH            claude-mem data folder (default: $CLAUDE_MEM_DATA_DIR or ~/.claude-mem)
  --claude-settings PATH     Claude Code user settings (default: ~/.claude/settings.json)

What "private" means here, from claude-mem's own settings (src/shared/SettingsDefaultsManager.ts):
  telemetry off           DO_NOT_TRACK=1 + CLAUDE_MEM_TELEMETRY=0 + telemetry.json enabled:false
  no cloud sync           CLAUDE_MEM_CLOUD_SYNC_HUB_URL/TOKEN/USER_ID empty, TeamBrain URL empty
  no online sign-in       CLAUDE_MEM_ONLINE_OPTIN=false (skips the cmem.ai trial / email step)
  local observer          openai-compatible provider on Ollama at localhost, no fallback to a cloud model
  no screenshots kept     CLAUDE_MEM_MEDIA_CAPTURE_ENABLED=false
  no update checks        CLAUDE_MEM_AUTO_UPDATE=false (update on purpose, with the plugin manager)
  local search only       Chroma local on 127.0.0.1 with its default local embeddings
  worker on loopback      CLAUDE_MEM_WORKER_HOST=127.0.0.1, no extra allowed origins or public URL
  secrets redacted        CLAUDE_MEM_REDACT_ENABLED + CLAUDE_MEM_REDACT_GENERIC_ENABLED = true

Standard library only. No network.
"""
import argparse
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

LOCAL = re.compile(r"^(localhost|127(\.\d{1,3}){3}|::1|0\.0\.0\.0|host\.docker\.internal)$", re.I)
OUTSIDE_PROVIDERS = {"gemini", "openrouter", "codex", "cmem", "cmem-gateway"}

PRIVATE = {
    "CLAUDE_MEM_CLOUD_SYNC_HUB_URL": "",
    "CLAUDE_MEM_CLOUD_SYNC_TOKEN": "",
    "CLAUDE_MEM_CLOUD_SYNC_USER_ID": "",
    "CLAUDE_MEM_CLOUD_SYNC_KEEP_PULLING": "false",
    "CLAUDE_MEM_TEAMBRAIN_URL": "",
    "CLAUDE_MEM_MEDIA_CAPTURE_ENABLED": "false",
    "CLAUDE_MEM_AUTO_UPDATE": "false",
    "CLAUDE_MEM_WORKER_HOST": "127.0.0.1",
    "CLAUDE_MEM_ALLOWED_ORIGINS": "",
    "CLAUDE_MEM_PUBLIC_URL": "",
    "CLAUDE_MEM_CHROMA_MODE": "local",
    "CLAUDE_MEM_CHROMA_HOST": "127.0.0.1",
    "CLAUDE_MEM_CHROMA_EMBEDDING_FUNCTION": "default",
    "CLAUDE_MEM_WORK_VIEW_COPY_PROVIDER": "off",
    "CLAUDE_MEM_REDACT_ENABLED": "true",
    "CLAUDE_MEM_REDACT_GENERIC_ENABLED": "true",
}
PROVIDERS = {
    "ollama": {
        "CLAUDE_MEM_PROVIDER": "openai-compatible",
        "CLAUDE_MEM_OPENAI_COMPAT_PRESET": "ollama",
        "CLAUDE_MEM_OPENAI_COMPAT_BASE_URL": "http://localhost:11434/v1",
        "CLAUDE_MEM_OPENAI_COMPAT_API_KEY": "",
        "CLAUDE_MEM_QUOTA_FALLBACK_PROVIDER": "off",
        "CLAUDE_MEM_PROVIDER_BY_SOURCE": "",
    },
    "claude": {
        "CLAUDE_MEM_PROVIDER": "claude",
        "CLAUDE_MEM_QUOTA_FALLBACK_PROVIDER": "off",
        "CLAUDE_MEM_PROVIDER_BY_SOURCE": "",
        "CLAUDE_MEM_OPENROUTER_BASE_URL": "",
    },
}
ENV = {
    "DO_NOT_TRACK": "1",
    "CLAUDE_MEM_TELEMETRY": "0",
    "CLAUDE_MEM_TELEMETRY_ERRORS": "0",
    "CLAUDE_MEM_ONLINE_OPTIN": "false",
}


def read_json(p):
    try:
        return json.loads(Path(p).read_text())
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as e:
        sys.exit(f"{p} is not valid JSON ({e}); fix or move it, then run again")


def write_json(p, data, stamp):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        shutil.copy2(p, p.with_name(f"{p.name}.bak-{stamp}"))
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    os.replace(tmp, p)


def paths(a):
    data = Path(os.path.expanduser(a.data_dir or os.environ.get("CLAUDE_MEM_DATA_DIR") or "~/.claude-mem"))
    return data / "settings.json", data / "telemetry.json", Path(os.path.expanduser(a.claude_settings))


def wanted(a, current):
    want = dict(PRIVATE)
    want.update(PROVIDERS[a.provider])
    if a.provider == "ollama":
        want["CLAUDE_MEM_OPENAI_COMPAT_MODEL"] = a.model
    if "cmem.ai" in str(current.get("CLAUDE_MEM_OPENROUTER_BASE_URL", "")):
        want["CLAUDE_MEM_OPENROUTER_BASE_URL"] = ""  # the hosted trial's gateway
        want["CLAUDE_MEM_OPENROUTER_API_KEY"] = ""
    if a.exclude:
        have = [x for x in str(current.get("CLAUDE_MEM_EXCLUDED_PROJECTS", "")).split(",") if x.strip()]
        for g in a.exclude:
            if g not in have:
                have.append(g)
        want["CLAUDE_MEM_EXCLUDED_PROJECTS"] = ",".join(have)
    return want


def changes(a):
    s_path, t_path, c_path = paths(a)
    s = read_json(s_path) or {}
    t = read_json(t_path) or {}
    c = read_json(c_path) or {}
    want = wanted(a, s)
    s_diff = {k: v for k, v in want.items() if str(s.get(k, "<unset>")) != v}
    env = c.get("env") or {}
    c_diff = {k: v for k, v in ENV.items() if str(env.get(k, "<unset>")) != v}
    t_diff = t.get("enabled") is not False
    return (s_path, s, s_diff), (t_path, t, t_diff), (c_path, c, c_diff)


def cmd_plan(a):
    (sp, s, sd), (tp, t, td), (cp, c, cd) = changes(a)
    if not (sd or td or cd):
        print("Already private: nothing to change.")
        return 0
    if sd:
        print(f"{sp}:")
        for k, v in sd.items():
            print(f"  {k}: {s.get(k, '<unset>')!r} -> {v!r}")
    if td:
        print(f"{tp}:\n  enabled: {t.get('enabled', '<unset>')!r} -> False")
    if cd:
        print(f"{cp} (env, inherited by claude-mem's hooks and worker):")
        for k, v in cd.items():
            print(f"  {k}: {(c.get('env') or {}).get(k, '<unset>')!r} -> {v!r}")
    print("\nRun again with 'apply' to write these (each file is backed up first).")
    return 0


def cmd_apply(a):
    stamp = time.strftime("%Y%m%d-%H%M%S")
    (sp, s, sd), (tp, t, td), (cp, c, cd) = changes(a)
    if sd:
        s.update(sd)
        write_json(sp, s, stamp)
    if td:
        t.update({"enabled": False, "installId": "", "decidedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        write_json(tp, t, stamp)
    if cd:
        c.setdefault("env", {}).update(cd)
        write_json(cp, c, stamp)
    n = len(sd) + int(td) + len(cd)
    print(f"Wrote {n} setting(s)." if n else "Already private: nothing to change.")
    print("Restart Claude Code (and the claude-mem worker: npx claude-mem restart) so they take effect.")
    return cmd_audit(a)


def _host(url):
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return url


def audit_rows(a):
    s_path, t_path, c_path = paths(a)
    s = read_json(s_path)
    t = read_json(t_path) or {}
    c = read_json(c_path) or {}
    env = {**(c.get("env") or {}), **{k: v for k, v in os.environ.items() if k in ENV}}
    rows = []

    def row(state, what, why):
        rows.append({"state": state, "check": what, "detail": why})

    if s is None:
        row("WARN", "settings.json", f"{s_path} not found: claude-mem isn't installed yet, or uses another data dir")
        s = {}
    g = lambda k, d="": str(s.get(k, d))

    dnt = str(env.get("DO_NOT_TRACK", "")).lower() not in ("", "0", "false")
    tel_env_off = str(env.get("CLAUDE_MEM_TELEMETRY", "")).lower() in ("0", "false", "off")
    if dnt or tel_env_off or t.get("enabled") is False:
        row("PASS", "telemetry off", "DO_NOT_TRACK / CLAUDE_MEM_TELEMETRY / telemetry.json")
    else:
        row("FAIL", "telemetry off", "anonymous usage analytics are ON by default: run apply, or `npx claude-mem telemetry disable`")
    if str(env.get("CLAUDE_MEM_TELEMETRY_ERRORS", "")).lower() not in ("0", "false", "off") and not dnt and t.get("enabled") is not False:
        row("FAIL", "error reports off", "error tracking follows telemetry consent; set CLAUDE_MEM_TELEMETRY_ERRORS=0")

    if g("CLAUDE_MEM_CLOUD_SYNC_HUB_URL") or g("CLAUDE_MEM_CLOUD_SYNC_TOKEN"):
        row("FAIL", "cloud sync off", f"sync hub set ({_host(g('CLAUDE_MEM_CLOUD_SYNC_HUB_URL')) or 'token present'}): memories upload to cmem.ai")
    else:
        row("PASS", "cloud sync off", "no sync hub URL or token")
    if g("CLAUDE_MEM_TEAMBRAIN_URL"):
        row("FAIL", "TeamBrain off", f"TeamBrain URL set ({_host(g('CLAUDE_MEM_TEAMBRAIN_URL'))})")
    if str(env.get("CLAUDE_MEM_ONLINE_OPTIN", "")).lower() != "false":
        row("WARN", "online sign-in skipped", "CLAUDE_MEM_ONLINE_OPTIN isn't false: the installer offers the cmem.ai trial and asks for an email")

    prov = g("CLAUDE_MEM_PROVIDER", "claude").lower()
    if prov == "openai-compatible":
        h = _host(g("CLAUDE_MEM_OPENAI_COMPAT_BASE_URL"))
        preset = g("CLAUDE_MEM_OPENAI_COMPAT_PRESET").lower()
        if (h and LOCAL.match(h)) or (not h and preset in ("ollama", "lmstudio", "vllm")):
            row("PASS", "observer runs locally", f"openai-compatible at {h or preset}")
        else:
            row("FAIL", "observer runs locally", f"tool activity goes to {h or 'an unset endpoint'}")
    elif prov == "claude":
        row("WARN", "observer runs locally", "observer uses your Anthropic plan: tool activity goes to Anthropic. Fine only if approved")
    elif prov in OUTSIDE_PROVIDERS:
        row("FAIL", "observer runs locally", f"provider '{prov}' sends tool activity to an outside service")
    else:
        row("WARN", "observer runs locally", f"unknown provider '{prov}'")
    if "cmem.ai" in g("CLAUDE_MEM_OPENROUTER_BASE_URL"):
        row("FAIL", "no cmem.ai gateway", "OpenRouter base URL points at the cmem.ai gateway (the hosted trial)")
    by_source = g("CLAUDE_MEM_PROVIDER_BY_SOURCE")
    if any(p in by_source.lower() for p in OUTSIDE_PROVIDERS):
        row("FAIL", "no per-source cloud provider", f"CLAUDE_MEM_PROVIDER_BY_SOURCE={by_source}")
    fb = g("CLAUDE_MEM_QUOTA_FALLBACK_PROVIDER", "claude").lower() or "claude"
    if fb != "off" and not (prov == "claude" and fb == "claude"):
        row("FAIL", "no silent fallback", f"when the observer can't serve, work falls back to '{fb}' (set it to off)")
    else:
        row("PASS", "no silent fallback", "quota fallback off")
    wv = g("CLAUDE_MEM_WORK_VIEW_COPY_PROVIDER").lower()
    if wv in ("openrouter", "openai-compatible") and prov != "openai-compatible":
        row("FAIL", "My Work copy local", f"generated My Work text uses '{wv}'")

    if g("CLAUDE_MEM_MEDIA_CAPTURE_ENABLED", "true").lower() != "false":
        row("WARN", "screenshots not kept", "tool screenshots are stored under ~/.claude-mem/media-v1 (local; upload only with Cloud Sync)")
    else:
        row("PASS", "screenshots not kept", "media capture off")
    if g("CLAUDE_MEM_AUTO_UPDATE", "true").lower() == "true":
        row("WARN", "no update checks", "auto-update contacts GitHub and installs new versions on its own")
    else:
        row("PASS", "no update checks", "auto-update off")

    wh = g("CLAUDE_MEM_WORKER_HOST", "127.0.0.1")
    if LOCAL.match(wh) and wh != "0.0.0.0":
        row("PASS", "worker on loopback", wh)
    else:
        row("FAIL", "worker on loopback", f"worker listens on {wh}: other machines can read your memory")
    if g("CLAUDE_MEM_ALLOWED_ORIGINS") or g("CLAUDE_MEM_PUBLIC_URL"):
        row("WARN", "no extra origins", "allowed origins or a public URL are set")

    cm, ch, ce = g("CLAUDE_MEM_CHROMA_MODE", "local"), g("CLAUDE_MEM_CHROMA_HOST", "127.0.0.1"), g("CLAUDE_MEM_CHROMA_EMBEDDING_FUNCTION", "default")
    if cm != "local" and not LOCAL.match(ch):
        row("FAIL", "search index local", f"Chroma is remote at {ch}")
    elif ce != "default":
        row("FAIL", "search index local", f"embeddings use '{ce}', an outside API")
    else:
        row("PASS", "search index local", "Chroma local, default local embeddings")

    if g("CLAUDE_MEM_REDACT_ENABLED", "false").lower() != "true":
        row("WARN", "secrets redacted", "auto-redaction of secret patterns is off")
    else:
        row("PASS", "secrets redacted", "on" + (" (incl. generic)" if g("CLAUDE_MEM_REDACT_GENERIC_ENABLED").lower() == "true" else ""))
    ex = g("CLAUDE_MEM_EXCLUDED_PROJECTS")
    row("PASS" if ex else "WARN", "work repos excluded", ex or "no excluded projects: every repo you open is recorded")
    return rows


def cmd_audit(a):
    rows = audit_rows(a)
    if getattr(a, "json", False):
        print(json.dumps(rows, indent=2))
    else:
        for r in rows:
            print(f"{r['state']:<5} {r['check']:<28} {r['detail']}")
    fails = sum(r["state"] == "FAIL" for r in rows)
    print(f"\n{fails} problem(s) that send data out." if fails else "\nNothing here sends data out without approval.", file=sys.stderr)
    return 1 if fails else 0


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["plan", "apply", "audit"])
    ap.add_argument("--provider", choices=sorted(PROVIDERS), default="ollama")
    ap.add_argument("--model", default="qwen3:8b")
    ap.add_argument("--exclude", action="append", default=[])
    ap.add_argument("--data-dir")
    ap.add_argument("--claude-settings", default="~/.claude/settings.json")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    return {"plan": cmd_plan, "apply": cmd_apply, "audit": cmd_audit}[a.action](a)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
