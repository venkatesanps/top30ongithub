---
name: private-setup
description: Install and lock down Claude-Mem and ECC (Everything Claude Code) so nothing leaves the machine without approval and no personal data goes out - telemetry off, no cloud sync, no online sign-in, a local observer model, outbound commands and skills that ask first - then audit it. Use when installing or reviewing claude-mem or ECC, when asked "is anything being sent out?", or to apply the rule "nothing outside without approval, no PII outside".
---

# Private setup: Claude-Mem and ECC, nothing out without a yes

The rule this skill applies, everywhere it runs:

1. **Nothing is sent to an outside service, API, tool or person without the user's approval.**
2. **No personal data (PII) goes outside at all**, unless the user approves that one call.

Installing from GitHub or npm is a download, not a send. Everything after that is checked.

## The pieces

| Piece | What it does |
|---|---|
| `claude-mem-private` (agent) | Installs claude-mem with no cmem.ai sign-in, sets it private with `cmem_private.py`, audits it. |
| `ecc-private` (agent) | Installs ECC from its own marketplace, adds ask-first rules with `ecc_private.py`, audits it. |
| egress gate (hook, on while this plugin is enabled) | Before Bash, Skill, web and connector calls: asks when a command uploads, posts, pushes, publishes, mails or copies to another machine; asks when a skill sends work to another provider; asks when any request carries personal data or secrets. Never blocks, never sends. |
| `scripts/cmem_private.py` | `plan` / `apply` / `audit` for claude-mem's `~/.claude-mem/settings.json`, `telemetry.json` and the env Claude Code passes to its hooks. |
| `scripts/ecc_private.py` | `plan` / `apply` / `audit` for ECC: ask rules for `codex` and `ecc ito`, hook profile, hosted MCP servers. |

Run either agent ("set up claude-mem privately", "install ECC privately"), or run the scripts
yourself from this skill's folder.

## Claude-Mem, private

```bash
python3 scripts/cmem_private.py plan  --provider ollama --model qwen3:8b --exclude "~/work/**"
python3 scripts/cmem_private.py apply --provider ollama --model qwen3:8b --exclude "~/work/**"
python3 scripts/cmem_private.py audit
```

| Setting | Private value | Why |
|---|---|---|
| Telemetry | `DO_NOT_TRACK=1`, `CLAUDE_MEM_TELEMETRY=0`, `CLAUDE_MEM_TELEMETRY_ERRORS=0`, `telemetry.json` `enabled:false` | Anonymous analytics are on by default. `DO_NOT_TRACK` overrides every other switch. |
| Cloud sync, TeamBrain | sync hub URL, token, user id and TeamBrain URL empty | Empty hub URL means sync is off (claude-mem's own rule). |
| Sign-in | `CLAUDE_MEM_ONLINE_OPTIN=false`, install with `--provider` | Skips the cmem.ai trial, which asks for an email and a card. |
| Observer (who writes the notes) | `openai-compatible` + `ollama` preset at `localhost:11434`, fallback `off` | The observer reads your tool activity. Local means it never leaves. `claude` (your Anthropic plan) only with approval. Never `cmem`, `openrouter`, `gemini` or `codex` without approval. |
| Screenshots | `CLAUDE_MEM_MEDIA_CAPTURE_ENABLED=false` | On by default, kept locally. Off is simpler. |
| Updates | `CLAUDE_MEM_AUTO_UPDATE=false` | Update on purpose with `claude plugin update`. |
| Search | Chroma `local`, `127.0.0.1`, embeddings `default` | The other embedding choices (openai, cohere, ...) are outside APIs. |
| Worker | `127.0.0.1`, no allowed origins, no public URL | Nothing else on the network can read memory. |
| Redaction | `CLAUDE_MEM_REDACT_ENABLED` and `..._GENERIC_ENABLED` `true` | Masks keys, tokens and passwords before they're stored. |
| Excluded projects | e.g. `~/work/**` | Work repos are never recorded. Ask the user which paths. |

## ECC, private

```bash
python3 scripts/ecc_private.py plan  --profile standard
python3 scripts/ecc_private.py apply --profile standard
python3 scripts/ecc_private.py audit
```

ECC's hooks run locally. What it can send out, and how each one is held:

| Can send out | Held by |
|---|---|
| `/astra-review`, `codex exec/review` (diff to OpenAI) | `permissions.ask` rules + the egress gate (skill and command) |
| `multi-*` workflows (other model providers) | egress gate (skill) |
| `ecc ito ...`, `ito-*` skills (external compute service) | `permissions.ask` rules + egress gate |
| `social-publisher`, `x-api`, `email-ops`, `mailtrap-email-integration` | egress gate (skill) |
| Sample MCP servers in `mcp-configs/` (Vercel, Cloudflare, Exa, browser-use...) | not added by the plugin; `audit` lists any hosted MCP server you added |

## The egress gate

```bash
python3 ../../hooks/egress_gate.py check 'curl -X POST https://api.example.org -d @notes.json'
# {"ask": true, "reasons": ["uploads data with curl"], "pii": []}
```

- `TOP30_EGRESS_GATE=off` switches it off for a session.
- `~/.config/top30-private/allow.txt`: one regex per line for commands that are pre-approved
  (`^git push origin feature/`).
- `~/.config/top30-private/pii-allow.txt`: one regex per line for strings that aren't personal
  data (your own commit email).

It asks; it doesn't decide. When it asks, say what will be sent, to whom, and why, then wait.

## When you report

Show the audit table. Name every WARN and say what it would take to clear it. Never call
the setup private while `audit` shows a FAIL.
