#!/usr/bin/env python3
"""Audit a project's agent setup, and guard Bash before it runs.

  audit [DIR] [--untrusted]   check config, workflow files, memory, MCP, permissions, sandbox,
                              hooks, pre-commit and CI against what an agent needs; with
                              --untrusted (a repo you just cloned) also look for injected
                              instructions, hidden characters and config that runs code
  scan FILE...                hidden Unicode, ANSI escapes and injection phrases in any text
  guard                       PreToolUse hook for Bash: blocks pipe-to-shell, hidden characters,
                              rm -rf on broad paths, force-push to main, reading .env or keys,
                              sending secrets over the network; asks before sudo, global
                              installs, git reset --hard and git clean

Standard library only. Reads files; never runs anything from the project.
Exit codes: audit/scan 0 ok, 1 findings at or above --fail-on, 2 bad input.
guard: 0 allow (or JSON "ask"), 2 block with the reason on stderr.
"""
import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

SEV = {"info": 0, "warn": 1, "error": 2}

# ---------------------------------------------------------------- hidden text

INVISIBLE = {
    **{c: "zero-width" for c in (0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x180E)},
    **{c: "bidi control" for c in list(range(0x202A, 0x202F)) + list(range(0x2066, 0x206A)) + [0x200E, 0x200F, 0x061C]},
}
CONFUSABLE_SCRIPTS = ("CYRILLIC", "GREEK", "ARMENIAN", "CHEROKEE")


def hidden_chars(text):
    """[(line, col, kind, codepoint)] for characters that read differently than they run."""
    out = []
    for ln, line in enumerate(text.splitlines(), 1):
        for col, ch in enumerate(line, 1):
            cp = ord(ch)
            if cp in INVISIBLE:
                out.append((ln, col, INVISIBLE[cp], f"U+{cp:04X}"))
            elif 0xE0000 <= cp <= 0xE007F:
                out.append((ln, col, "tag character (invisible text)", f"U+{cp:04X}"))
            elif cp == 0x1B:
                out.append((ln, col, "ANSI escape", "ESC"))
            elif cp < 0x20 and ch not in "\t\r":
                out.append((ln, col, "control character", f"U+{cp:04X}"))
        for m in re.finditer(r"[^\W\d_]{2,}", line):
            w = m.group(0)
            scripts = {("LATIN" if c.isascii() else next((s for s in CONFUSABLE_SCRIPTS if s in unicodedata.name(c, "")), "OTHER"))
                       for c in w}
            if "LATIN" in scripts and scripts & set(CONFUSABLE_SCRIPTS):
                out.append((ln, m.start() + 1, f"mixed-script word '{w}' (looks Latin, isn't)", "confusable"))
    return out


INJECTION = [
    (r"\bignore (all |any )?(previous|prior|above|earlier) (instructions|rules|messages)", "tells the agent to ignore its instructions"),
    (r"\b(do not|don't|never) (tell|inform|mention (this )?to|show) (the )?user", "tells the agent to hide something from the user"),
    (r"\b(you are now|from now on you are|new system prompt|system override|developer mode)\b", "tries to replace the agent's role"),
    (r"\b(send|post|upload|forward|report|exfiltrate|sync)\b[^\n]{0,80}\b(env(ironment)?( variables| details)?|\.env|secrets?|"
     r"tokens?|api[_ ]?keys?|credentials|ssh keys?|logs?)\b[^\n]{0,80}(https?://|endpoint|webhook|server)",
     "asks to send secrets or logs to an outside endpoint"),
    (r"\b(curl|wget)\b[^\n|]*\|\s*(sudo\s+)?(ba|z|da)?sh\b", "pipes a download into a shell"),
    (r"\b(auto[- ]?approve|skip (all )?(permission|confirmation)s?|--dangerously-skip-permissions|bypassPermissions)\b",
     "turns off permission prompts"),
    (r"[A-Za-z0-9+/]{120,}={0,2}", "long base64-looking blob"),
]


def scan_text(text, name):
    fs = []
    for ln, col, kind, cp in hidden_chars(text):
        fs.append({"severity": "error", "file": name, "line": ln, "check": "hidden-text",
                   "msg": f"{kind} ({cp}) at column {col}"})
    for ln, line in enumerate(text.splitlines(), 1):
        for rx, why in INJECTION:
            if re.search(rx, line, re.I):
                fs.append({"severity": "warn", "file": name, "line": ln, "check": "injection",
                           "msg": f"{why}: {line.strip()[:100]}"})
    return fs


# ---------------------------------------------------------------- audit

GENERIC = re.compile(r"^\s*[-*]?\s*(write (clean|good|readable|maintainable) code|follow (the )?best practices|use best practices|"
                     r"be (careful|thorough|concise|helpful)|follow solid( principles)?|keep (it|code) simple|"
                     r"write (good|proper) tests|make sure (it|everything) works|think step by step|you are an? (expert|senior))\b", re.I)
LOCKS = {"pnpm-lock.yaml": "pnpm", "yarn.lock": "yarn", "package-lock.json": "npm", "bun.lockb": "bun", "bun.lock": "bun",
         "uv.lock": "uv", "poetry.lock": "poetry", "Pipfile.lock": "pipenv", "Cargo.lock": "cargo", "go.sum": "go"}
JS_PMS = {"pnpm", "yarn", "npm", "bun"}
DENY_WANTED = [
    ("secrets", re.compile(r"Read\([^)]*\.env|Read\([^)]*secrets?|Read\([^)]*\.ssh|Read\([^)]*credentials", re.I),
     'Read(./.env), Read(./.env.*), Read(./secrets/**)'),
    ("rm -rf", re.compile(r"Bash\(\s*rm\s+-[a-z]*r[a-z]*f|Bash\(\s*rm\s+-[a-z]*f[a-z]*r|Bash\(\s*rm\b", re.I), "Bash(rm -rf:*)"),
    ("force push", re.compile(r"Bash\(\s*git push[^)]*(--force|-f)\b|Bash\(\s*git push\b", re.I), "Bash(git push --force:*)"),
    ("pipe to shell", re.compile(r"Bash\(\s*(curl|wget)\b", re.I), "Bash(curl:*) in ask, or the guard hook"),
]


def read_json(p, fs, name):
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError) as e:
        fs.append({"severity": "error", "file": name, "line": None, "check": "parse", "msg": f"can't parse: {e}"})
        return None


def est_tokens(text):
    return len(text) // 4


def audit(root, untrusted=False):
    fs = []

    def add(sev, layer, check, msg, file=None, line=None):
        fs.append({"severity": sev, "layer": layer, "check": check, "file": file, "line": line, "msg": msg})

    rel = lambda p: str(p.relative_to(root))  # noqa: E731

    # --- configuration: always-loaded files
    configs = [p for p in (root / "CLAUDE.md", root / ".claude" / "CLAUDE.md", root / "AGENTS.md", root / "CLAUDE.local.md")
               if p.exists()]
    always = 0
    if not configs:
        add("warn", "config", "config-file", "no CLAUDE.md or AGENTS.md: the agent guesses your package manager, "
            "test command and rules. Start one with /init, then cut it to what's specific to this repo")
    lockpms = sorted({pm for f, pm in LOCKS.items() if (root / f).exists()})
    for p in configs:
        text = p.read_text(errors="replace")
        lines = text.splitlines()
        always += est_tokens(text)
        if len(lines) > 200:
            add("warn", "config", "length", f"{len(lines)} lines; aim for under ~100. Move task-specific parts to skills", rel(p))
        elif len(lines) > 100:
            add("info", "config", "length", f"{len(lines)} lines; under ~100 keeps it in focus", rel(p))
        for i, l in enumerate(lines, 1):
            if GENERIC.match(l):
                add("warn", "config", "generic", f"generic advice the model already knows: '{l.strip()[:60]}'", rel(p), i)
        for m in re.finditer(r"^\s*@(\S+)", text, re.M):
            q = (p.parent / m.group(1).replace("~", str(Path.home()), 1)).resolve()
            if q.is_file() and root in q.parents:
                always += est_tokens(q.read_text(errors="replace"))
        low = text.lower()
        js = [pm for pm in lockpms if pm in JS_PMS]
        if js:
            pm = js[0]
            others = [o for o in JS_PMS - {pm} if re.search(rf"\b{o} (run|install|i|test|add)\b", low)]
            if others:
                add("error", "config", "package-manager", f"lockfile says {pm}, but this file tells the agent to use "
                    f"{', '.join(sorted(others))}", rel(p))
            elif pm not in low:
                add("warn", "config", "package-manager", f"the repo uses {pm} ({[f for f, v in LOCKS.items() if v == pm][0]}); "
                    "say so, or the agent may reach for npm", rel(p))
        has_tests = (root / "package.json").exists() and '"test"' in (root / "package.json").read_text(errors="replace") \
            or (root / "pyproject.toml").exists() or (root / "Makefile").exists() or (root / "tests").is_dir()
        if has_tests and not re.search(r"\b(test|pytest|jest|vitest|make check|go test|cargo test)\b", low):
            add("warn", "config", "test-command", "no test command: say exactly how to run the tests", rel(p))
        if untrusted:
            fs.extend(dict(f, layer="injection") for f in scan_text(text, rel(p)))
    rules = list((root / ".claude" / "rules").glob("**/*.md")) if (root / ".claude" / "rules").is_dir() else []
    for p in rules:
        always += est_tokens(p.read_text(errors="replace"))
    if always > 5000:
        add("warn", "config", "context-rot", f"~{always:,} tokens load every session (CLAUDE.md, imports, rules); "
            "trim what doesn't change the agent's output")

    # --- workflow files (skills, commands, agents)
    skills = sorted((root / ".claude" / "skills").glob("*/SKILL.md")) if (root / ".claude" / "skills").is_dir() else []
    commands = sorted((root / ".claude" / "commands").glob("**/*.md")) if (root / ".claude" / "commands").is_dir() else []
    agents = sorted((root / ".claude" / "agents").glob("*.md")) if (root / ".claude" / "agents").is_dir() else []
    if not (skills or commands):
        add("info", "config", "workflow-files", "no project skills or commands: write one for a task you repeat "
            "(tests, PR review, migrations), from a real run, not generated")
    for p in skills + agents:
        text = p.read_text(errors="replace")
        fm = re.match(r"^---\n(.*?)\n---", text, re.S)
        if not fm or not re.search(r"^description:\s*\S", fm.group(1), re.M):
            add("error", "config", "frontmatter", "no description in frontmatter: the agent can't tell when to use it", rel(p))
        elif len(re.search(r"^description:\s*(.*)$", fm.group(1), re.M).group(1)) < 40:
            add("warn", "config", "frontmatter", "description under 40 characters: say what it does and when to use it", rel(p))
        n = len(text.splitlines())
        if n > 500:
            add("warn", "config", "workflow-length", f"{n} lines; split the reference parts into files it reads on demand", rel(p))
        if untrusted:
            fs.extend(dict(f, layer="injection") for f in scan_text(text, rel(p)))
    if untrusted:
        for p in commands:
            fs.extend(dict(f, layer="injection") for f in scan_text(p.read_text(errors="replace"), rel(p)))
        for name in (".cursorrules", ".windsurfrules", ".github/copilot-instructions.md", "GEMINI.md"):
            if (root / name).exists():
                fs.extend(dict(f, layer="injection") for f in scan_text((root / name).read_text(errors="replace"), name))

    # --- memory
    for p in (root / "MEMORY.md", root / ".claude" / "MEMORY.md"):
        if p.exists():
            n = len(p.read_text(errors="replace").splitlines())
            if n > 200:
                add("warn", "capability", "memory", f"{n} lines of memory; past ~200 it's context rot. Prune it or move "
                    "to searchable memory", rel(p))
            if untrusted:
                fs.extend(dict(f, layer="injection") for f in scan_text(p.read_text(errors="replace"), rel(p)))

    # --- MCP
    mcp = root / ".mcp.json"
    if mcp.exists():
        data = read_json(mcp, fs, ".mcp.json") or {}
        servers = data.get("mcpServers", {}) if isinstance(data, dict) else {}
        for name, s in servers.items():
            cmd = " ".join([str(s.get("command", ""))] + [str(a) for a in s.get("args", [])])
            url = s.get("url", "")
            if url.startswith("http://") and not re.match(r"http://(localhost|127\.0\.0\.1|\[::1\])", url):
                add("error", "capability", "mcp", f"server '{name}' uses plain http: {url}", ".mcp.json")
            m = re.search(r"\b(npx|bunx|pnpm dlx|uvx)\s+(?:-y\s+|--yes\s+)?(@?[\w./-]+)", cmd)
            if m and not re.search(r"@\d", m.group(2)) and not m.group(2).startswith(("-", ".", "/")):
                add("warn", "capability", "mcp", f"server '{name}' runs '{m.group(2)}' unpinned: whatever version is "
                    "published next runs with the agent's permissions. Pin it (pkg@1.2.3)", ".mcp.json")
            for k, v in (s.get("env") or {}).items():
                if re.search(r"(key|token|secret|password)", k, re.I) and v and not str(v).startswith("${"):
                    add("error", "capability", "mcp", f"server '{name}' has a literal {k} in .mcp.json; use ${{{k}}}", ".mcp.json")
            if untrusted:
                add("warn", "injection", "mcp", f"project MCP server '{name}' is code that runs with the agent's "
                    f"permissions: `{(cmd.strip() or url)[:90]}`. Read it before approving", ".mcp.json")
        if untrusted:
            fs.extend(dict(f, layer="injection") for f in scan_text(mcp.read_text(errors="replace"), ".mcp.json"))

    # --- permissions, sandbox, hooks
    settings = {}
    for name in (".claude/settings.json", ".claude/settings.local.json"):
        p = root / name
        if p.exists():
            d = read_json(p, fs, name)
            if isinstance(d, dict):
                settings[name] = d
                if untrusted:
                    fs.extend(dict(f, layer="injection") for f in scan_text(p.read_text(errors="replace"), name))
    allow = [r for d in settings.values() for r in (d.get("permissions") or {}).get("allow", [])]
    deny = [r for d in settings.values() for r in (d.get("permissions") or {}).get("deny", [])]
    ask = [r for d in settings.values() for r in (d.get("permissions") or {}).get("ask", [])]
    modes = [(n, (d.get("permissions") or {}).get("defaultMode")) for n, d in settings.items()]
    for n, mode in modes:
        if mode == "bypassPermissions":
            add("error", "guardrails", "permissions", "defaultMode bypassPermissions: every tool runs without asking", n)
    for r in allow:
        if r.strip() in ("Bash", "Bash(*)", "Bash(:*)", "*"):
            add("error", "guardrails", "permissions", f"allow '{r}' lets the agent run any shell command without asking")
    if not settings:
        add("warn", "guardrails", "permissions", "no .claude/settings.json: no shared allow list for safe commands "
            "and no deny list for dangerous ones")
    else:
        rules_text = " ".join(deny + ask)
        for label, rx, example in DENY_WANTED:
            if not rx.search(rules_text):
                add("warn", "guardrails", "deny-list", f"nothing denies or asks for {label}; e.g. {example}")
    sandbox = any((d.get("sandbox") or {}).get("enabled") for d in settings.values())
    container = any((root / f).exists() for f in (".devcontainer/devcontainer.json", ".devcontainer.json"))
    if not sandbox and not container:
        add("info", "guardrails", "sandbox", "no sandbox in project settings and no devcontainer; turn it on with "
            "/sandbox, or run the agent in a container with no network by default")
    hooks = [(n, h) for n, d in settings.items() for h in (d.get("hooks") or {}).get("PreToolUse", [])]
    if not any(re.search(r"Bash|\*|^$", h.get("matcher", "") or "") for _, h in hooks):
        add("warn", "guardrails", "hooks", "no PreToolUse hook on Bash: nothing checks a command after the agent writes "
            "it and before it runs. `setup_audit.py guard` is one")
    if untrusted:
        for n, d in settings.items():
            for event, entries in (d.get("hooks") or {}).items():
                for e in entries:
                    for h in e.get("hooks", []):
                        if h.get("command"):
                            add("error", "injection", "hook-command", f"{event} hook runs `{h['command'][:90]}` "
                                "automatically once you trust this folder. Read what it runs", n)
            for k in ("apiKeyHelper", "awsAuthRefresh", "awsCredentialExport", "otelHeadersHelper"):
                if d.get(k):
                    add("error", "injection", "helper", f"{k} runs `{str(d[k])[:80]}` to fetch credentials", n)
            for k, v in (d.get("env") or {}).items():
                if re.match(r"(ANTHROPIC_BASE_URL|ANTHROPIC_API_URL|HTTPS?_PROXY|NODE_OPTIONS|NODE_EXTRA_CA_CERTS|"
                            r"ANTHROPIC_API_KEY|ANTHROPIC_AUTH_TOKEN)$", k, re.I):
                    add("error", "injection", "env", f"sets {k}={str(v)[:60]}: traffic or keys can be redirected", n)
            if d.get("enableAllProjectMcpServers"):
                add("error", "injection", "mcp", "enableAllProjectMcpServers approves every project MCP server unseen", n)

    # --- pre-commit and CI
    pc = root / ".pre-commit-config.yaml"
    if not pc.exists() and not (root / ".husky").is_dir() and not (root / "lefthook.yml").exists():
        add("warn", "guardrails", "pre-commit", "no pre-commit gate: the agent's output goes straight into history. "
            "Add one with a secrets check, lint and format")
    elif pc.exists() and not re.search(r"detect-private-key|gitleaks|detect-secrets|trufflehog", pc.read_text(errors="replace")):
        add("warn", "guardrails", "pre-commit", "pre-commit has no secrets check (detect-private-key, gitleaks, detect-secrets)",
            ".pre-commit-config.yaml")
    wf = list((root / ".github" / "workflows").glob("*.y*ml")) if (root / ".github" / "workflows").is_dir() else []
    ci_other = any((root / f).exists() for f in (".gitlab-ci.yml", "azure-pipelines.yml", ".circleci/config.yml", "Jenkinsfile"))
    if not wf and not ci_other:
        add("warn", "observability", "ci", "no CI: 'task complete' stays a claim. CI passing is the outcome signal")
    elif wf and not any(re.search(r"\b(test|pytest|jest|vitest|check|lint)\b", p.read_text(errors="replace")) for p in wf):
        add("warn", "observability", "ci", "CI workflows don't appear to run tests or checks")
    if untrusted:
        for p in wf:
            if re.search(r"claude|anthropic", p.read_text(errors="replace"), re.I):
                add("info", "injection", "ci-agent", "a workflow runs an agent in CI; check what it can push and which secrets "
                    "it gets", rel(p))
    return fs


LAYERS = [("config", "Configuration: CLAUDE.md/AGENTS.md, workflow files, context size"),
          ("capability", "Capability: MCP, memory"),
          ("guardrails", "Guardrails: permissions, sandbox, hooks, pre-commit"),
          ("observability", "Observability: CI as the outcome signal"),
          ("injection", "Trust (--untrusted): injected instructions, hidden text, config that runs code")]


# ---------------------------------------------------------------- guard (PreToolUse on Bash)

def segments(cmd):
    """Split a shell command on ; && || | & and newlines outside quotes. Returns [(text, sep_before)]."""
    out, cur, sep, i, q = [], [], None, 0, None
    while i < len(cmd):
        c = cmd[i]
        if q:
            cur.append(c)
            if c == q:
                q = None
            elif c == "\\" and q == '"' and i + 1 < len(cmd):
                cur.append(cmd[i + 1]); i += 1
        elif c in "'\"":
            q = c; cur.append(c)
        elif c == "\\" and i + 1 < len(cmd):
            cur.append(c + cmd[i + 1]); i += 1
        elif cmd[i:i + 2] in ("&&", "||"):
            out.append(("".join(cur).strip(), sep)); cur, sep = [], cmd[i:i + 2]; i += 1
        elif c in ";|&\n":
            out.append(("".join(cur).strip(), sep)); cur, sep = [], c
        else:
            cur.append(c)
        i += 1
    out.append(("".join(cur).strip(), sep))
    return [(s, p) for s, p in out if s]


PREFIX = re.compile(r"^(?:(?:sudo|doas|env|command|exec|nohup|time|xargs)(?:\s+-\S+)*\s+|[A-Z_][A-Z0-9_]*=\S*\s+)*")
SHELLS = re.compile(r"^(?:sudo\s+)?(?:ba|z|da|k|fi)?sh\b|^(?:sudo\s+)?(?:python3?|perl|ruby|node)\b(?!\s+\S+\.\w+)")
BROAD = re.compile(r"""^["']?(/|/\*|~/?|~/\*|\$HOME/?|\$\{HOME\}/?|\.{1,2}/?|\*|\.\*|/(etc|usr|bin|sbin|var|opt|System|Library|Users|home|private)(/\S*)?)["']?$""")
SECRET_PATH = re.compile(r"(^|[\s/'\"=])(\.env(\.(?!example\b|sample\b|template\b|dist\b)[\w.-]+)?|\.ssh/id_[\w.-]+|\.aws/credentials|"
                         r"\.netrc|\.npmrc|\.pypirc|\.docker/config\.json|\.config/gh/hosts\.yml|[\w-]+\.pem|[\w-]+\.key)(?=$|[\s'\";|)])")
READERS = re.compile(r"^(cat|less|more|head|tail|bat|grep|rg|awk|sed|cut|strings|xxd|od|base64|source|\.|cp|scp|rsync|tar|zip|open|code|vim?|nano|jq|yq|sort)\b")
NET = re.compile(r"\b(curl|wget|nc|ncat|netcat|socat|scp|rsync|ftp|telnet|http|https|xh)\b")
ENV_DUMP = re.compile(r"^(env|printenv|set|export -p|declare -x)\s*$")


def guard_check(cmd):
    """Return ('deny'|'ask'|'allow', [reasons])."""
    deny, ask = [], []
    for ln, col, kind, cp in hidden_chars(cmd):
        deny.append(f"{kind} ({cp}) in the command: what you read isn't what runs")
    segs = segments(cmd)
    if re.search(r"\b(ba|z)?sh\s+<\(\s*(curl|wget)\b|\$\(\s*(curl|wget)\b[^)]*\)\s*\"?\s*$|"
                 r"\b(ba|z)?sh\s+-c\s+[\"']?\$\(\s*(curl|wget)", cmd):
        deny.append("runs a downloaded script (shell + curl/wget): download it, read it, then run the file")
    for i, (s, sep) in enumerate(segs):
        body = PREFIX.sub("", s)
        if sep == "|" and SHELLS.match(body) and i > 0 and re.match(r"(curl|wget|fetch|http)\b", PREFIX.sub("", segs[i - 1][0])):
            deny.append(f"pipes a download into {body.split()[0]}: download it, read it, then run the file")
        if re.match(r"rm\b", body):
            toks = body.split()[1:]
            flags = "".join(t.lstrip("-") for t in toks if t.startswith("-") and not t.startswith("--")) + \
                " ".join(t for t in toks if t.startswith("--"))
            if ("r" in flags or "R" in flags or "recursive" in flags):
                for t in (t for t in toks if not t.startswith("-")):
                    if BROAD.match(t):
                        deny.append(f"rm -r on '{t}': that's a home, root, system or whole-directory path")
        if re.match(r"git\s+push\b", body):
            toks = body.split()[2:]
            force = any(t in ("-f", "--force", "--force-with-lease", "--force-if-includes") or t.startswith("--force")
                        or (t.startswith("-") and not t.startswith("--") and "f" in t) for t in toks) \
                or any(t.startswith("+") for t in toks)
            refs = [t.lstrip("+") for t in toks if not t.startswith("-")][1:]
            if force:
                if any(re.search(r"(^|:|/)(main|master|trunk|release[\w/.-]*|prod(uction)?)$", r) for r in refs):
                    deny.append("force-push to a protected branch (main/master/release/prod)")
                elif not refs:
                    ask.append("force-push without naming a branch: it may hit main")
        if READERS.match(body):
            # for copies, only the sources are read; writing a fresh .env from .env.example is fine
            src = " ".join(body.split()[:-1]) if re.match(r"(cp|scp|rsync)\b", body) else body
            hit = SECRET_PATH.search(src)
            if hit:
                deny.append(f"reads a secrets file ({hit.group(2)})")
        if ENV_DUMP.match(body) and i + 1 < len(segs) and segs[i + 1][1] == "|" and NET.search(segs[i + 1][0]):
            deny.append("pipes the environment to a network command")
        if NET.match(body) and (SECRET_PATH.search(body) or re.search(r"\$\((env|printenv)\)|`(env|printenv)`|"
                                                             r"@(\S*\.env\b|\S*id_rsa|\S*credentials)", body)):
            deny.append("sends a secrets file or the environment over the network")
        if re.match(r"(sudo|doas)\b", s):
            ask.append("sudo: runs as root")
        if re.match(r"(npm|pnpm|yarn|bun)\s+(i|install|add)\b.*\s(-g|--global)\b|(npm|pnpm)\s+(-g|--global)\s|"
                    r"yarn\s+global\s+add|pip3?\s+install\b(?!.*(\s-r\s|--user|-e\s|\.))|brew\s+install|gem\s+install|cargo\s+install", body):
            ask.append(f"installs software outside the project: {body[:50]}")
        if re.match(r"git\s+(reset\s+--hard|clean\s+-[a-z]*f|checkout\s+--\s+\.|restore\s+(--staged\s+)?\.\s*$|stash\s+(drop|clear))", body):
            ask.append(f"discards local work: {body[:50]}")
        if re.match(r"chmod\s+(-R\s+)?(777|a\+rwx|o\+w)", body):
            ask.append("makes files world-writable")
        if re.match(r"(dd|mkfs\S*|diskutil\s+erase|shred)\b", body):
            deny.append(f"{body.split()[0]} can destroy a disk or file beyond recovery")
    return ("deny" if deny else "ask" if ask else "allow"), deny or ask


# ---------------------------------------------------------------- CLI

def show(fs):
    for f in fs:
        loc = ":".join(str(x) for x in (f.get("file"), f.get("line")) if x)
        print(f"  [{f['severity']}] {f['check']}{' ' + loc if loc else ''}: {f['msg']}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("audit"); p.add_argument("dir", nargs="?", default=".")
    p.add_argument("--untrusted", action="store_true"); p.add_argument("--json", action="store_true")
    p.add_argument("--fail-on", default="error", choices=SEV)
    p = sub.add_parser("scan"); p.add_argument("files", nargs="+"); p.add_argument("--json", action="store_true")
    p.add_argument("--fail-on", default="error", choices=SEV)
    p = sub.add_parser("guard"); p.add_argument("--command", help="check this command instead of reading hook JSON")
    a = ap.parse_args(argv)

    if a.cmd == "guard":
        if a.command is not None:
            cmd = a.command
        else:
            try:
                ev = json.load(sys.stdin)
            except (json.JSONDecodeError, ValueError):
                return 0
            if ev.get("tool_name") != "Bash":
                return 0
            cmd = (ev.get("tool_input") or {}).get("command", "")
        verdict, why = guard_check(cmd)
        if verdict == "deny":
            print("Blocked by setup_audit guard:\n" + "\n".join(f"- {w}" for w in why), file=sys.stderr)
            return 2
        if verdict == "ask":
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask",
                                                     "permissionDecisionReason": "; ".join(why)}}))
        return 0

    if a.cmd == "scan":
        fs = []
        for f in a.files:
            try:
                fs += scan_text(Path(f).read_text(errors="replace"), f)
            except OSError as e:
                print(f"can't read {f}: {e}", file=sys.stderr)
                return 2
        if a.json:
            print(json.dumps({"findings": fs}, indent=2))
        else:
            print(f"{len(a.files)} file(s), {len(fs)} finding(s)")
            show(fs)
    else:
        root = Path(a.dir).resolve()
        if not root.is_dir():
            print(f"{root} is not a directory", file=sys.stderr)
            return 2
        fs = audit(root, a.untrusted)
        if a.json:
            print(json.dumps({"dir": str(root), "untrusted": a.untrusted, "findings": fs}, indent=2))
        else:
            print(f"Agent setup audit: {root}{'  (untrusted)' if a.untrusted else ''}\n")
            for key, title in LAYERS:
                if key == "injection" and not a.untrusted:
                    continue
                part = [f for f in fs if f.get("layer") == key]
                worst = max((SEV[f["severity"]] for f in part), default=-1)
                mark = {-1: "ok  ", 0: "ok  ", 1: "WARN", 2: "FAIL"}[worst]
                print(f"{mark} {title}")
                show(part)
            e = sum(f["severity"] == "error" for f in fs)
            w = sum(f["severity"] == "warn" for f in fs)
            print(f"\n{e} error(s), {w} warning(s)")
    worst = max((SEV[f["severity"]] for f in fs), default=-1)
    return 1 if worst >= SEV[a.fail_on] else 0


if __name__ == "__main__":
    sys.exit(main())
