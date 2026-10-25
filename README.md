# Claude plugins kit — the 30 from the "top 30 on GitHub (by job)" post

Every repo below was located, cloned and installed on 2026-10-24 (25 re-verified end to end with this exact install.sh). 23 install as Claude Code
plugins; the other 7 are CLIs or project installers, all built and health-checked.

## Quick start (Claude Code on your Mac/PC)

```bash
git clone https://github.com/venkatesanps/top30ongithub.git && cd top30ongithub
# (or: unzip claude-plugins-kit.zip && cd claude-plugins-kit)
./install.sh --list            # see all 30 with GitHub links and per-session token cost
./install.sh --dry-run 5 30    # show the exact commands first
./install.sh 5 30              # install Superpowers + I Have ADHD (asks before running each)
./install.sh row 4             # or a whole row
./verify.sh 5 30               # check they work
```

Restart Claude Code after installing plugins.

Prerequisites, only for the items that need them: Claude Code, Node 22+ (24+ for GSD),
Python 3.10+ (pipx recommended), Bun (gstack, Claude-Mem), git, FFmpeg (video tools).

## Using them in the Claude app instead (claude.ai, desktop, mobile)

`claude-ai-skills/` holds 88 ready-to-upload skill zips from 14 of the repos — the ones that
work without Claude Code's CLI. Upload in Settings → Capabilities → Skills (one zip per skill).
Start small; each enabled skill adds its description to every chat.

| Folder | Skills |
|---|---|
| 01-karpathy | karpathy-guidelines |
| 02-mattpocock | grill-me, tdd, to-spec, diagnosing-bugs, code-review, domain-modeling, handoff, teach |
| 04-agent-skills | spec-driven-development, planning-and-task-breakdown, code-review-and-quality, debugging-and-error-recovery, security-and-hardening, api-and-interface-design, documentation-and-adrs, idea-refine, interview-me |
| 05-superpowers | brainstorming, writing-plans, executing-plans, systematic-debugging, test-driven-development, verification-before-completion, requesting/receiving-code-review |
| 06-ponytail | ponytail, ponytail-review |
| 17-caveman | caveman |
| 19-taste | design-taste-frontend |
| 20-archify | archify |
| 21-diagram-design | diagram-design |
| 22-impeccable | impeccable |
| 23-ui-ux-pro-max | ui-ux-pro-max |
| 25-marketing | all 52 marketing skills |
| 28-humanizer | humanizer |
| 30-i-have-adhd | i-have-adhd |

## Things worth knowing before you pick

- **Token cost per session** (measured with `claude plugin details`): ECC ~47.6k, Marketing Skills ~15.7k,
  Agent Skills ~3.7k, Claude-Mem ~2.8k, Caveman ~2.0k. Most single-skill plugins are 100–850.
- **GSD moved**: `gsd-build/get-shit-done` was archived in May 2026; it continues as `open-gsd/gsd-core` (needs Node 24+).
- **Caveman**: an independent placebo test (skill-placebo) found no significant output-token saving on Opus 5.5.
- **REA**: fake "REA.exe" copies are circulating. Use only github.com/morluto/rea, rea.tools, or npm `rea-agents`.
- **gstack** asks you to add CLAUDE.md lines that make Claude use its own /browse instead of Claude in Chrome.
- **OpenMontage** is AGPL-3.0; its AI generation providers need your own API keys.
- **Claude-Mem** fails Claude Code's plugin-name policy check (names can't start with "claude-") but installs and runs.
- **Skills by Anthropic** (docx/xlsx/pptx/pdf) are already built into the Claude app; install them only for Claude Code.

## Files

- `guide/index.html` — the field guide page (open it in a browser).
- `scripts/` — how the kit was generated and tested; see scripts/README.md.
- `sources/` — the upstream repos as submodules pinned to the tested commits (`git submodule update --init --depth 1`).

- `install.sh` / `verify.sh` — generated from `catalog.json` (the single source of truth: repo, commands, checks, notes).
- `catalog.json` — all 30 entries.
- `claude-ai-skills/` — upload-ready zips + `_manifest.json`.
