#!/usr/bin/env python3
"""Set up ECC (affaan-m/ECC, "Everything Claude Code") so it sends nothing outside without approval.

  ecc_private.py plan  [options]   show what apply would change (writes nothing)
  ecc_private.py apply [options]   write the private settings (backs up the file first)
  ecc_private.py audit [--json]    check the current setup; exit 1 if something sends data out unasked

Options:
  --profile minimal|standard|strict   ECC hook profile to pin (ECC_HOOK_PROFILE). Default: leave as is.
                                      minimal also skips continuous-learning capture.
  --claude-settings PATH              Claude Code user settings (default: ~/.claude/settings.json)
  --claude-json PATH                  Claude Code state with MCP servers (default: ~/.claude.json)
  --plugins-file PATH                 installed plugins list (default: ~/.claude/plugins/installed_plugins.json)

ECC's own hooks run locally. What ECC can send out, from its v2.2.3 source:
  /astra-review and codex     your diff goes to OpenAI through the Codex CLI ("invoking it is consent")
  multi-* workflows           work goes to other model providers through ccg-workflow
  ecc ito ... / ito-* skills  live, authenticated requests to an external compute service
  social-publisher, x-api,    posts and emails on your behalf
  email-ops, mailtrap-*
  mcp-configs/                34 sample MCP servers, many hosted (Vercel, Cloudflare, Exa,
                              browser-use...). Not enabled by the plugin; added by hand.

apply adds Claude Code "ask" rules for the shell forms of these (codex, ecc ito), so each one
needs a yes. The skills are gated by the egress gate hook in this plugin. Standard library only.
"""
import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

ASK_RULES = [
    "Bash(codex exec:*)",
    "Bash(codex review:*)",
    "Bash(codex e:*)",
    "Bash(ecc ito:*)",
    "Bash(npx ecc-universal ito:*)",
    "Bash(npx -y ecc-universal ito:*)",
]
LOCAL = ("localhost", "127.0.0.1", "::1", "0.0.0.0", "host.docker.internal")


def read_json(p):
    try:
        return json.loads(Path(p).read_text())
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as e:
        sys.exit(f"{p} is not valid JSON ({e}); fix or move it, then run again")


def write_json(p, data):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        shutil.copy2(p, p.with_name(f"{p.name}.bak-{time.strftime('%Y%m%d-%H%M%S')}"))
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    os.replace(tmp, p)


def ex(p):
    return Path(os.path.expanduser(p))


def changes(a):
    cp = ex(a.claude_settings)
    c = read_json(cp) or {}
    have = set(((c.get("permissions") or {}).get("ask")) or [])
    add_rules = [r for r in ASK_RULES if r not in have]
    env_diff = {}
    if a.profile and (c.get("env") or {}).get("ECC_HOOK_PROFILE") != a.profile:
        env_diff["ECC_HOOK_PROFILE"] = a.profile
    return cp, c, add_rules, env_diff


def cmd_plan(a):
    cp, c, rules, env = changes(a)
    if not rules and not env:
        print("Already private: nothing to change.")
        return 0
    print(f"{cp}:")
    for r in rules:
        print(f"  permissions.ask += {r}")
    for k, v in env.items():
        print(f"  env.{k}: {(c.get('env') or {}).get(k, '<unset>')!r} -> {v!r}")
    print("\nRun again with 'apply' to write these (the file is backed up first).")
    return 0


def cmd_apply(a):
    cp, c, rules, env = changes(a)
    if rules:
        c.setdefault("permissions", {}).setdefault("ask", []).extend(rules)
    if env:
        c.setdefault("env", {}).update(env)
    if rules or env:
        write_json(cp, c)
        print(f"Wrote {len(rules)} ask rule(s) and {len(env)} env setting(s). Restart Claude Code to load them.")
    else:
        print("Already private: nothing to change.")
    return cmd_audit(a)


def installed(plugins_file):
    d = read_json(ex(plugins_file)) or {}
    return d.get("plugins") or {}


def find_plugin(plugs, name):
    for key, entries in plugs.items():
        if key.split("@")[0] == name:
            e = entries[0] if isinstance(entries, list) and entries else (entries if isinstance(entries, dict) else {})
            return key, e
    return None, {}


def mcp_servers(claude_json):
    d = read_json(ex(claude_json)) or {}
    out = []
    for name, cfg in (d.get("mcpServers") or {}).items():
        out.append(("user", name, cfg))
    for proj, pd in (d.get("projects") or {}).items():
        for name, cfg in ((pd or {}).get("mcpServers") or {}).items():
            out.append((proj, name, cfg))
    return out


def audit_rows(a):
    rows = []

    def row(state, what, why):
        rows.append({"state": state, "check": what, "detail": why})

    c = read_json(ex(a.claude_settings)) or {}
    plugs = installed(a.plugins_file)
    key, e = find_plugin(plugs, "ecc")
    if key:
        row("PASS", "ECC installed", f"{key} {e.get('version', '')}".strip())
        root = Path(e.get("installPath", "")) if e.get("installPath") else None
        cfg = read_json(root / "skills/continuous-learning-v2/config.json") if root else None
        if cfg and (cfg.get("observer") or {}).get("enabled"):
            row("WARN", "learning observer off", "continuous-learning observer is on: it runs `claude` in the background on your tool history")
        elif cfg is not None:
            row("PASS", "learning observer off", "observer.enabled is false (ECC default)")
    else:
        row("WARN", "ECC installed", "ecc not found in installed plugins (install it, then audit again)")

    have = set(((c.get("permissions") or {}).get("ask")) or [])
    deny = set(((c.get("permissions") or {}).get("deny")) or [])
    allow = set(((c.get("permissions") or {}).get("allow")) or [])
    missing = [r for r in ASK_RULES if r not in have and r not in deny]
    if missing:
        row("FAIL", "outbound commands ask first", f"missing ask rules: {', '.join(missing)}")
    else:
        row("PASS", "outbound commands ask first", f"{len(ASK_RULES)} ask/deny rules for codex and ecc ito")
    broad = [r for r in allow if r in ("Bash", "Bash(*)", "Bash(codex:*)", "Bash(ecc:*)")]
    if broad:
        row("FAIL", "no blanket allow", f"allow rules {broad} let outbound commands run without asking")

    gate, _ = find_plugin(plugs, "top30-private")
    row("PASS" if gate else "WARN", "egress gate on",
        gate or "top30-private isn't installed: ECC's outbound skills (astra-review, social-publisher...) won't ask first")
    if str((c.get("env") or {}).get("TOP30_EGRESS_GATE", "")).lower() in ("off", "0", "false"):
        row("FAIL", "egress gate on", "TOP30_EGRESS_GATE=off in settings env")

    remote = []
    for scope, name, cfg in mcp_servers(a.claude_json):
        url = (cfg or {}).get("url") or ""
        host = (urlparse(url).hostname or "") if url else ""
        if host and host not in LOCAL:
            remote.append(f"{name} ({host}{'' if scope == 'user' else ', ' + Path(scope).name})")
    if remote:
        row("WARN", "hosted MCP servers", "these send what you ask them to outside: " + "; ".join(remote))
    else:
        row("PASS", "hosted MCP servers", "none configured")
    if shutil.which("codex"):
        row("WARN", "Codex CLI present", "/astra-review can send diffs to OpenAI; it will ask first with the rules above")
    return rows


def cmd_audit(a):
    rows = audit_rows(a)
    if getattr(a, "json", False):
        print(json.dumps(rows, indent=2))
    else:
        for r in rows:
            print(f"{r['state']:<5} {r['check']:<28} {r['detail']}")
    fails = sum(r["state"] == "FAIL" for r in rows)
    print(f"\n{fails} problem(s) that let data out without asking." if fails else "\nNothing here sends data out without approval.", file=sys.stderr)
    return 1 if fails else 0


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["plan", "apply", "audit"])
    ap.add_argument("--profile", choices=["minimal", "standard", "strict"])
    ap.add_argument("--claude-settings", default="~/.claude/settings.json")
    ap.add_argument("--claude-json", default="~/.claude.json")
    ap.add_argument("--plugins-file", default="~/.claude/plugins/installed_plugins.json")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    return {"plan": cmd_plan, "apply": cmd_apply, "audit": cmd_audit}[a.action](a)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
