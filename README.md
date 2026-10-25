# Top 30 Claude plugins, kept current

The 30 plugins from the "top 30 on GitHub (by job)" post, each traced to its real repository,
with one installer, a verifier, a field guide, and upload-ready skill zips for the Claude app.

A GitHub Action re-checks everything every day:

- **New upstream commits** are re-pinned under `sources/`, and affected skill zips are rebuilt.
- **Breakage** is caught early: repos that moved, were archived or renamed; marketplace or plugin
  names that no longer match our install commands; packages that vanished from npm/PyPI.
- **Install tests** run on a fresh Linux machine for anything that changed, and for all 30 every Monday.
- **Token cost per session** is re-measured with `claude plugin details`.
- Results go to the status table below, [CHANGELOG.md](CHANGELOG.md), the field guide
  (GitHub Pages), and one open issue labelled `upstream-attention` that closes itself when all is well.

## Quick start (Claude Code on your Mac/PC)

```bash
git clone https://github.com/venkatesanps/top30ongithub.git && cd top30ongithub
./install.sh --list            # all 30 with GitHub links and per-session token cost
./install.sh --status          # health from the last daily check
./install.sh --dry-run 5 30    # show the exact commands first
./install.sh 5 30              # install Superpowers + I Have ADHD (asks before running each)
./install.sh row 4             # or a whole row
./verify.sh 5 30               # check they work
git pull                       # later: pick up fixes from the daily check
```

Restart Claude Code after installing plugins. Prerequisites only for items that need them:
Claude Code, Node 22+ (24+ for GSD), Python 3.10+ (pipx recommended), Bun (gstack, Claude-Mem),
git, FFmpeg (video tools).

## Using them in the Claude app (claude.ai, desktop, mobile)

`claude-ai-skills/` holds ready-to-upload skill zips from 14 of the repos. Upload in
Settings → Capabilities → Skills, one zip per skill. Each zip includes its project's license;
see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Start small: each enabled skill adds its
description to every chat.

## Status

<!-- status:start -->
_Checked 2026-10-25: 30 repos, 30 passing install tests, 0 needing attention. Token costs measured with Claude Code._

| # | Plugin | Repo | Stars | Upstream updated | Install test | Tokens/session | Status |
|---|---|---|---|---|---|---|---|
| 1 | Karpathy Skills | [multica-ai/andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills) | 223.7k | 2026-04-20 | pass (2026-10-25) | ~66 | OK |
| 2 | Matt Pocock Skills | [mattpocock/skills](https://github.com/mattpocock/skills) | 303.1k | 2026-10-22 | pass (2026-10-25) | ~1,169 | OK |
| 3 | ECC (Everything Claude Code) | [affaan-m/ECC](https://github.com/affaan-m/ECC) | 288.7k | 2026-10-25 | pass (2026-10-25) | ~33,456 | OK |
| 4 | Agent Skills (Addy Osmani) | [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) | 110.4k | 2026-10-13 | pass (2026-10-25) | ~2,903 | OK |
| 5 | Superpowers | [obra/superpowers](https://github.com/obra/superpowers) | 305k | 2026-10-23 | pass (2026-10-25) | ~706 | OK |
| 6 | Ponytail | [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail) | 176.1k | 2026-10-18 | pass (2026-10-25) | ~430 | OK |
| 7 | Career Ops | [career-ops-hq/career-ops](https://github.com/career-ops-hq/career-ops) | 77.2k | 2026-10-25 | pass (2026-10-25) | ~116 | OK |
| 8 | REA (Reverse Engineer Anything) | [morluto/rea](https://github.com/morluto/rea) | 383.6k | 2026-10-25 | pass (2026-10-25) | n/a (MCP) | OK |
| 9 | Graphify | [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify) | 135k | 2026-10-23 | pass (2026-10-25) | n/a (CLI skill) | OK |
| 10 | Understand Anything | [Egonex-AI/Understand-Anything](https://github.com/Egonex-AI/Understand-Anything) | 88.2k | 2026-10-22 | pass (2026-10-25) | ~870 | OK |
| 11 | Last 30 Days | [mvanhorn/last30days-skill](https://github.com/mvanhorn/last30days-skill) | 65.4k | 2026-10-25 | pass (2026-10-25) | ~67 | OK |
| 12 | Agent Reach | [Panniantong/Agent-Reach](https://github.com/Panniantong/Agent-Reach) | 102.4k | 2026-10-25 | pass (2026-10-25) | n/a (CLI skill) | OK |
| 13 | Headroom | [headroomlabs-ai/headroom](https://github.com/headroomlabs-ai/headroom) | 77.8k | 2026-10-24 | pass (2026-10-25) | ~0 | OK |
| 14 | BMAD Method | [bmad-code-org/BMAD-METHOD](https://github.com/bmad-code-org/BMAD-METHOD) | 54.5k | 2026-10-20 | pass (2026-10-25) | per project | OK |
| 15 | Claude-Mem | [thedotmack/claude-mem](https://github.com/thedotmack/claude-mem) | 103.1k | 2026-10-25 | pass (2026-10-25) | ~2,060 | OK |
| 16 | gstack | [garrytan/gstack](https://github.com/garrytan/gstack) | 137.7k | 2026-10-25 | pass (2026-10-25) | n/a (skills dir) | OK |
| 17 | Caveman | [JuliusBrussee/caveman](https://github.com/JuliusBrussee/caveman) | 115k | 2026-10-25 | pass (2026-10-25) | ~1,366 | OK |
| 18 | GSD (Get Shit Done) | [open-gsd/gsd-core](https://github.com/open-gsd/gsd-core) | 10.8k | 2026-10-25 | pass (2026-10-25) | n/a (commands) | OK |
| 19 | Taste | [Leonxlnx/taste-skill](https://github.com/Leonxlnx/taste-skill) | 102.4k | 2026-10-25 | pass (2026-10-25) | ~246 | OK |
| 20 | Archify | [tt-a1i/archify](https://github.com/tt-a1i/archify) | 89.1k | 2026-10-25 | pass (2026-10-25) | n/a (skill) | OK |
| 21 | Diagram Design | [cathrynlavery/diagram-design](https://github.com/cathrynlavery/diagram-design) | 61k | 2026-10-25 | pass (2026-10-25) | ~378 | OK |
| 22 | Impeccable | [pbakaus/impeccable](https://github.com/pbakaus/impeccable) | 87.4k | 2026-10-25 | pass (2026-10-25) | ~312 | OK |
| 23 | UI UX Pro Max | [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | 140.3k | 2026-10-23 | pass (2026-10-25) | ~709 | OK |
| 24 | PPT Master | [hugohe3/ppt-master](https://github.com/hugohe3/ppt-master) | 68.1k | 2026-10-24 | pass (2026-10-25) | ~139 | OK |
| 25 | Marketing Skills | [coreyhaines31/marketingskills](https://github.com/coreyhaines31/marketingskills) | 56.5k | 2026-10-22 | pass (2026-10-25) | ~10,604 | OK |
| 26 | Skills by Anthropic | [anthropics/skills](https://github.com/anthropics/skills) | 183.7k | 2026-10-09 | pass (2026-10-25) | ~759 + ~939 | OK |
| 27 | OpenMontage | [calesthio/OpenMontage](https://github.com/calesthio/OpenMontage) | 71.8k | 2026-10-24 | pass (2026-10-25) | per project | OK |
| 28 | Humanizer | [blader/humanizer](https://github.com/blader/humanizer) | 60.5k | 2026-10-16 | pass (2026-10-25) | ~90 | OK |
| 29 | HyperFrames | [heygen-com/hyperframes](https://github.com/heygen-com/hyperframes) | 72k | 2026-10-25 | pass (2026-10-25) | ~551 | OK |
| 30 | I Have ADHD | [ayghri/i-have-adhd](https://github.com/ayghri/i-have-adhd) | 58.7k | 2026-10-19 | pass (2026-10-25) | ~67 | OK |
<!-- status:end -->

## Things worth knowing before you pick

- **Token cost**: ECC and Marketing Skills are by far the heaviest (see the table); most single-skill plugins add under 1k tokens per session. The figures are Claude Code's own estimates and shift between CLI versions.
- **GSD moved**: `gsd-build/get-shit-done` was archived; it continues as `open-gsd/gsd-core` (Node 24+).
- **Caveman**: an independent placebo test (skill-placebo) found no significant output-token saving on Opus 5.5.
- **REA**: fake "REA.exe" copies circulate. Use only github.com/morluto/rea, rea.tools, or npm `rea-agents`.
- **gstack** asks you to add CLAUDE.md lines making Claude use its own /browse instead of Claude in Chrome.
- **OpenMontage** is AGPL-3.0; its AI generation providers need your own API keys.
- **Claude-Mem** fails Claude Code's plugin-name policy check (names can't start with "claude-") but installs and runs.
- **Skills by Anthropic** (docx/xlsx/pptx/pdf) are already built into the Claude app; install them only for Claude Code.

## How it's put together

| Path | What |
|---|---|
| `catalog.json` | Single source of truth: repo, install/verify commands, notes, zip config, upstream status. |
| `install.sh`, `verify.sh` | Generated from the catalog. Bash 3.2 compatible. |
| `claude-ai-skills/` | Skill zips + `_manifest.json` (skill, source path, upstream commit, license). |
| `guide/` | Field guide page (`index.html` is generated from `template.html`). Published to GitHub Pages. |
| `sources/` | Upstream repos as submodules, pinned to the last checked commit. `git submodule update --init --depth 1 sources/30-i-have-adhd` fetches one. |
| `scripts/kit.py` | The maintenance tool: `check`, `bump`, `pack`, `costs`, `smoke`, `render`, `report`. |
| `.github/workflows/` | `refresh.yml` (daily), `ci.yml` (on every push/PR). |

To fix something the daily check flags: edit `catalog.json`, run `python3 scripts/kit.py render`,
and push. CI checks that generated files match the catalog.

Run the daily job by hand from the Actions tab (**Refresh → Run workflow**, optionally with
"Install-test everything"), or locally:

```bash
python3 scripts/kit.py check && python3 scripts/kit.py bump && python3 scripts/kit.py pack \
  && python3 scripts/kit.py render && python3 scripts/kit.py report
```
