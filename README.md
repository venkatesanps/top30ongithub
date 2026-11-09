# Top 30 Claude plugins, a data & ops toolkit, the 20 to open first, Anthropic's build repos and the 27-skill list, kept current

Six collections, each traced to its real repository, with one installer, a verifier, a field
guide, and upload-ready skill zips for the Claude app:

- **Top 30 from the post** (items 1–30, rows 1–5): coding, research, token savers, design, writing.
- **Data & ops toolkit** (items 31–56, rows 6–9): Snowflake, dbt, Airflow and data quality; AWS,
  Oracle and migrations; manager and team productivity (Jira/Confluence, DORA dashboards, AI
  adoption); production monitoring for leadership, app developers and SRE / L2 / L3.
- **[20 to open first](#20-github-projects-to-open-first)** (items 58–66, rows 10–12, plus 11 already
  here): agent harnesses, memory, token savers, product and everyday tools, with a script to test
  each one before and after.
- **[Anthropic's 6 to build with](#anthropics-6-repos-to-build-with)** (items 67–71, row 13, plus 26):
  the prompt tutorial, quickstarts, Agent SDK, Claude Code and Claude Code Action, with a working
  Snowflake SQL review agent and GitHub workflows (including Amazon Bedrock) you can copy.
- **[27 skills, one at a time](#27-skills-one-at-a-time)** (items 72–78, row 14, plus 25 and 28): notes
  and research, writing, marketing, n8n automation, and build & ship, mapped skill by skill to the
  repos they come from.
- **Picked since the posts** (items 79–81): EasyUI's animated component registry and the
  Interfaces skills its author builds with (row 4), and Busabase, a shared, reviewable memory for
  agents (row 10).

**Playbooks** for putting them to work: [manager](playbooks/manager.md),
[lead data engineer](playbooks/lead-data-engineer.md), [team rollout](playbooks/team-rollout.md),
[production & SRE](playbooks/production-and-sre.md), and
[Claude features worth setting up](playbooks/claude-features.md) (fact-checked, with prompts for work), and
[loops and graphs](playbooks/loops-and-graphs.md) (agent work you approve once, not step by step), and
[15 Claude Code commands, fact-checked](playbooks/claude-commands.md). Read
[Before you try this at work](playbooks/before-you-try-at-work.md) first.

**Field guide:** https://venkatesanps.github.io/top30ongithub/ (refreshed daily)

A GitHub Action re-checks everything every day:

- **New upstream commits** are re-pinned under `sources/`, and affected skill zips are rebuilt.
- **Breakage** is caught early: repos that moved, were archived or renamed; marketplace or plugin
  names that no longer match our install commands; packages that vanished from npm/PyPI.
- **Install tests** run on a fresh Linux machine for anything that changed or is untested, and for
  everything every Monday. Dashboards are tested by pulling their images and validating their
  compose files; a few items that need your own account (marked "manual") are only checked upstream.
- **Token cost per session** is re-measured with `claude plugin details`.
- Results go to the status table below, [CHANGELOG.md](CHANGELOG.md), the field guide
  (GitHub Pages), and one open issue labelled `upstream-attention` that closes itself when all is well.

## Quick start (Claude Code on your Mac/PC)

```bash
git clone https://github.com/venkatesanps/top30ongithub.git && cd top30ongithub
./install.sh --list            # everything, with GitHub links and per-session token cost
./install.sh --status          # health from the last daily check
./install.sh --dry-run 5 30    # show the exact commands first
./install.sh 5 30              # install Superpowers + I Have ADHD (asks before running each)
./install.sh row 4             # or a whole row
./install.sh 41 42 45          # SQLGlot + SQLFluff + Jira/Confluence MCP (data & ops toolkit)
./verify.sh 5 30               # check they work
git pull                       # later: pick up fixes from the daily check
```

Restart Claude Code after installing plugins. Prerequisites only for items that need them:
Claude Code, Node 22+ (24+ for GSD), Python 3.10+ (pipx recommended), uv (MCP servers),
Docker (dashboards), Java 17+ (SQLcl), Bun (gstack, Claude-Mem), git, FFmpeg (video tools).

## 20 GitHub projects to open first

The "20 GitHub projects you should open first" list, in its own order. Eleven were already in
this kit; the other nine are items 58–66. Every one is pinned, install-tested and checked daily.
`./install.sh --show open20` prints the list, and the field guide has a "20 to open first" filter.

<!-- list:open20:start -->
| Post # | Catalog # | Name | Repo | Tokens/session | Install test |
|---|---|---|---|---|---|
| 1 | [3](#status) | ECC (Everything Claude Code) | [affaan-m/ECC](https://github.com/affaan-m/ECC) | ~33,844 | pass |
| 2 | [4](#status) | Agent Skills (Addy Osmani) | [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) | ~2,999 | pass |
| 3 | [58](#status) | Ruflo (agent swarms) | [ruvnet/ruflo](https://github.com/ruvnet/ruflo) | ~417 | pass |
| 4 | [59](#status) | wshobson agents (plugin packs) | [wshobson/agents](https://github.com/wshobson/agents) | ~492 + ~903 + ~111 | pass |
| 5 | [15](#status) | Claude-Mem | [thedotmack/claude-mem](https://github.com/thedotmack/claude-mem) | ~2,141 | pass |
| 6 | [60](#status) | planning-with-files | [OthmanAdi/planning-with-files](https://github.com/OthmanAdi/planning-with-files) | ~736 | pass |
| 7 | [9](#status) | Graphify | [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify) | n/a (CLI skill) | pass |
| 8 | [10](#status) | Understand Anything | [Egonex-AI/Understand-Anything](https://github.com/Egonex-AI/Understand-Anything) | ~870 | pass |
| 9 | [6](#status) | Ponytail | [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail) | ~430 | pass |
| 10 | [61](#status) | rtk (OSS edition) | [rtk-ai/rtk](https://github.com/rtk-ai/rtk) | n/a | pass |
| 11 | [13](#status) | Headroom | [headroomlabs-ai/headroom](https://github.com/headroomlabs-ai/headroom) | ~0 | pass |
| 12 | [62](#status) | context-mode | [mksglu/context-mode](https://github.com/mksglu/context-mode) | ~60 | pass |
| 13 | [23](#status) | UI UX Pro Max | [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | ~709 | pass |
| 14 | [19](#status) | Taste | [Leonxlnx/taste-skill](https://github.com/Leonxlnx/taste-skill) | ~235 | pass |
| 15 | [63](#status) | video-shotcraft | [Vincentwei1021/video-shotcraft](https://github.com/Vincentwei1021/video-shotcraft) | n/a | pass |
| 16 | [12](#status) | Agent Reach | [Panniantong/Agent-Reach](https://github.com/Panniantong/Agent-Reach) | n/a (CLI skill) | pass |
| 17 | [64](#status) | CC Switch (desktop) | [farion1231/cc-switch](https://github.com/farion1231/cc-switch) | n/a | manual |
| 18 | [65](#status) | pm-skills | [phuryn/pm-skills](https://github.com/phuryn/pm-skills) | ~1,693 | pass |
| 19 | [66](#status) | claude-skills (380+ skills) | [alirezarezvani/claude-skills](https://github.com/alirezarezvani/claude-skills) | ~2,618 + ~66 + ~69 | pass |
| 20 | [7](#status) | Career Ops | [career-ops-hq/career-ops](https://github.com/career-ops-hq/career-ops) | ~116 | pass |
<!-- list:open20:end -->

**The post's advice, which this kit agrees with:**

1. **Start with 3, not 20:** one for memory, one for tokens, one for your actual job. For a
   manager and lead data engineer, a reasonable first three:
   - *Memory:* **15** Claude-Mem (remembers across sessions; ~2.1k tokens/session and a background
     worker), or the lighter **60** planning-with-files for long, multi-day tasks.
   - *Tokens:* **61** rtk (OSS) compresses command output before Claude reads it and adds almost
     nothing to context; **13** Headroom is the alternative.
   - *Your job:* **59** wshobson `data-engineering` as a lead data engineer, or **66** `vpe-advisor`
     (DORA and cycle-time analysis) / **65** `pm-execution` as a manager.
2. **Run the same task before and after.** Keep only what makes the result better or cheaper.
   `scripts/ab.py` does this for you: it copies a sandbox repo, runs the same prompt headless with
   the plugin off and on, and compares cost, tokens, turns and whether your check passed:

   ```bash
   ./install.sh 65
   python3 scripts/ab.py --plugin pm-execution@pm-skills --runs 3 \
     --prompt "Write a one-page PRD for a Snowflake cost dashboard into PRD.md" \
     --repo ~/sandbox --check "test -s PRD.md"
   ```

   Three runs show a direction, not proof. For a careful, placebo-controlled comparison see
   [skill-placebo](https://github.com/simonether/skill-placebo): in its September 2026 run on
   Opus 5.5, 2 of 9 popular skills beat a same-length placebo (Ponytail and Agent Skills), and
   none was measurably cheaper than no skill at all. The notes on items 4, 6 and 60 say what it found.
3. **Every plugin you add loads into context, so more isn't free.** The "Tokens/session" column
   is measured daily with `claude plugin details`. ECC (**3**) alone adds about 33k tokens to every
   session. Disable what you aren't using with `claude plugin disable <name>`.

## Anthropic's 6 repos to build with

Anthropic's own repos for learning to prompt, building an agent and running it where your team
works, in the post's order. Skills (item 26) was already here; the other five are items 67–71.
`./install.sh --show anthropic6` prints the list.

<!-- list:anthropic6:start -->
| Post # | Catalog # | Name | Repo | Tokens/session | Install test |
|---|---|---|---|---|---|
| 1 | [67](#status) | Prompt engineering tutorial | [anthropics/prompt-eng-interactive-tutorial](https://github.com/anthropics/prompt-eng-interactive-tutorial) | n/a | pass |
| 2 | [68](#status) | Claude quickstarts | [anthropics/claude-quickstarts](https://github.com/anthropics/claude-quickstarts) | n/a | pass |
| 3 | [26](#status) | Skills by Anthropic | [anthropics/skills](https://github.com/anthropics/skills) | ~759 + ~939 | pass |
| 4 | [69](#status) | Claude Agent SDK (Python) | [anthropics/claude-agent-sdk-python](https://github.com/anthropics/claude-agent-sdk-python) | n/a | pass |
| 5 | [70](#status) | Claude Code (the CLI) | [anthropics/claude-code](https://github.com/anthropics/claude-code) | n/a | pass |
| 6 | [71](#status) | Claude Code Action (GitHub) | [anthropics/claude-code-action](https://github.com/anthropics/claude-code-action) | n/a | pass |
<!-- list:anthropic6:end -->

The post's pitch: build one agent with these and you become the person your team brings AI
projects to. To make that concrete for a data team, this kit includes one:

- **[examples/sql-review-agent](examples/sql-review-agent/)**: a read-only Snowflake SQL reviewer
  built on the Agent SDK. A custom tool runs sqlglot checks, a hook blocks every write and any
  path outside the folder, and a budget cap stops runaway cost. On the samples it found all seven
  planted problems for about $0.10 with Sonnet.
- **[templates/claude-code-action](templates/claude-code-action/)**: `claude.yml` (tag @claude on
  issues and PRs) and `sql-review-bedrock.yml` (reviews every PR that touches `.sql`, on Amazon
  Bedrock through GitHub OIDC, so there's no Anthropic API key and traffic stays in your AWS account).

Two things that changed upstream since these repos were written:

- **The tutorial's model was retired.** The notebooks call Claude 3 Haiku, which Anthropic
  retired on April 20, 2026. `./install.sh 67` switches them to Claude Haiku 4.5. Newer
  models (4.6 and later) reject the `temperature` and prefill settings the lessons use.
- **npm install of Claude Code is deprecated.** Item 70 uses the native installer.

## 27 skills, one at a time

A post listing 27 skills in five folders, with one piece of advice: don't install them all tonight.
The 27 skills come from nine repos. Two were already here (**25** Marketing Skills, **28** Humanizer);
the other seven are items 72–78. `./install.sh --show skills27` prints the list.

<!-- list:skills27:start -->
| Post # | Catalog # | Name | Repo | Tokens/session | Install test |
|---|---|---|---|---|---|
| 1 | [73](#status) | NotebookLM skill | [PleasePrompto/notebooklm-skill](https://github.com/PleasePrompto/notebooklm-skill) | ~75 (est., skills dir) | pass |
| 2 | [72](#status) | Obsidian Skills | [kepano/obsidian-skills](https://github.com/kepano/obsidian-skills) | ~403 | pass |
| 3 | [74](#status) | Hugging Face skills | [huggingface/skills](https://github.com/huggingface/skills) | ~200 (est., skills dir) | pass |
| 4 | [28](#status) | Humanizer | [blader/humanizer](https://github.com/blader/humanizer) | ~90 | pass |
| 5 | [25](#status) | Marketing Skills | [coreyhaines31/marketingskills](https://github.com/coreyhaines31/marketingskills) | ~5,059 | pass |
| 6 | [75](#status) | n8n skills | [czlonkowski/n8n-skills](https://github.com/czlonkowski/n8n-skills) | ~2,817 | pass |
| 7 | [76](#status) | Vercel agent skills | [vercel-labs/agent-skills](https://github.com/vercel-labs/agent-skills) | ~250 (est., skills dir) | pass |
| 8 | [77](#status) | Trail of Bits skills | [trailofbits/skills](https://github.com/trailofbits/skills) | ~47 | pass |
| 9 | [78](#status) | Context engineering skills | [muratcankoylan/Agent-Skills-for-Context-Engineering](https://github.com/muratcankoylan/Agent-Skills-for-Context-Engineering) | ~1,992 | pass |
<!-- list:skills27:end -->

| Folder | Skills from the post | Item |
|---|---|---|
| Notes & research | notebooklm | **73** NotebookLM skill |
| | json-canvas, defuddle, obsidian-markdown | **72** Obsidian Skills |
| | huggingface-papers | **74** Hugging Face skills |
| Writing | humanizer | **28** Humanizer |
| | emails, copy-editing, social, copywriting, content-strategy | **25** Marketing Skills |
| Marketing | ai-seo, pricing, launch, seo-audit, marketing-psychology | **25** Marketing Skills |
| Automate | n8n-validation-expert, n8n-workflow-patterns, n8n-node-configuration, n8n-expression-syntax | **75** n8n skills |
| Build & ship | deploy-to-vercel, react-best-practices, web-design-guidelines | **76** Vercel agent skills |
| | modern-python | **77** Trail of Bits skills |
| | huggingface-gradio, huggingface-local-models | **74** Hugging Face skills |
| | context-fundamentals | **78** Context engineering skills |

**The post's advice, which this kit agrees with:** pick the folder closest to your daily work and
add one skill from it; use it on real tasks for a week; keep it only if it saved time, then add the
next. Three you use every day beat 27 you never open. The `skill-trial` skill (plugin `top30-coach`,
below) keeps that score for you.

Three notes before installing:

- **73** NotebookLM drives a Chrome window signed in to your Google account. Keep it to personal notebooks.
- **76** Vercel's repo has no license file, so it installs from upstream but has no Claude app zips here.
- **75** n8n skills assume the n8n-mcp server pointed at your own n8n instance, and add edit-checking hooks.

## Skills built here

This repo is also a Claude Code plugin marketplace with five plugins of its own:

```bash
claude plugin marketplace add venkatesanps/top30ongithub
claude plugin install top30-data@top30ongithub    # Oracle → Snowflake, Snowflake cost, pipeline triage
claude plugin install top30-ops@top30ongithub     # Datadog app investigator
claude plugin install top30-coach@top30ongithub   # skill-trial: adopt one skill at a time
claude plugin install top30-agents@top30ongithub  # loops, graphs, /goal writer + goal gate, /batch scout
claude plugin install top30-ui@top30ongithub      # motion components, your own shadcn registry, motion forensics
```

| Plugin | Skill / agent | What it does | Always-on cost |
|---|---|---|---|
| `top30-data` | `oracle-to-snowflake` | Translates Oracle SQL with SQLGlot (`ora2sf.py`) and flags what a translator can't know: ROWNUM, `''` vs NULL, `NUMBER` losing decimals, SYSDATE timezone, date arithmetic, db links, triggers, packages, row-by-row loops. Keeps PL/SQL for a set-based rewrite, writes a per-file effort report, and `--fail-on error` blocks merges in CI. Tests: `tests/ora2sf/`. | ~150 |
| `top30-data` | `snowflake-cost-investigator` | Read-only `ACCOUNT_USAGE` queries (`sf_cost.py`) run through your MCP, CLI, a named connector connection or Snowsight exports, then a report: idle and never-suspending warehouses, costliest query patterns, remote spill, full partition scans, queuing, serverless share and storage kept only for time travel, each with the fix and the credits behind it. Hides literals in query text. Tests: `tests/sf_cost/`. | ~160 |
| `top30-data` | `pipeline-failure-triage` (agent) | Read-only subagent for a failed or slow Airflow, dbt, Snowflake task, Glue or refiner run: first real error, what changed, root cause, smallest safe fix, whether a re-run is safe, and the test that would have caught it. | ~160 |
| `top30-ops` | `datadog-app-investigator` | Signs in through Datadog's official plugin (OAuth) and collects one service's error logs, slow and failing endpoints, alerting monitors, SLOs, deploys, incidents and error-tracking issues into an investigation report. Read-only, masks personal data. Has a key-based fallback script (`dd_collect.py`) and a test suite (`tests/datadog/`). Install with item **57**. | ~455 + ~94 |
| `top30-coach` | `skill-trial` | The "don't install all of them tonight" rule as a skill: one skill for a week on real work, log minutes saved (`trial.py`), then keep, extend or drop on evidence, and get the next three for your role from `catalog.json`. Tests: `tests/skill_trial/`. | ~150 |
| `top30-agents` | `agent-graph-designer` | Turns a pipeline described in prose into a checked graph: a four-line contract per step, arrows that must name the variable they carry (the rest are cut so steps run in parallel), model vs code per step, a real check per step, bounded loops, failure handling and human gates placed by how hard a mistake is to undo. `graph_check.py` reports parallel waves, minutes in a line vs. as a graph, and a Mermaid diagram. Tests: `tests/graph_check/`. | ~150 |
| `top30-agents` | `agent-loop` | `agent_loop.py` runs Claude Code headless in a loop you don't watch. `repair` fixes one scoped unit until a command exits 0, with a round limit, a budget, memory of past attempts, out-of-scope edit detection, early escalation when two rounds fail the same way, and a rules file of lessons learned. `hunt` finds things round by round and stops after two rounds with nothing new, remembering rejected findings too. Tests: `tests/agent_loop/` with a fake agent. | ~140 |
| `top30-agents` | `goal-writer` + goal gate (hook) | `goal_lint.py` scores a `/goal` condition (stated check, measurable end state, constraints, bound, no self-judged or irreversible steps) and has recipes for pytest, dbt, sqlfluff, `ora2sf`, reconciliation and mypy. Goal gate is a Stop hook that runs a real command and keeps Claude working until it exits 0, with a round limit and same-failure stop. It does nothing until switched on, and its settings live outside the repo. Tests: `tests/goal_tools/`. | ~180 |
| `top30-agents` | `which-command` | Matches a situation to the right built-in command (`/plan`, `/goal`, `/loop`, `/schedule`, `/batch`, `/subtask`, `/fork`, `/branch`, `/rewind`, `/compact`, `/simplify`, `/code-review`, ...) with the catch each one has. | ~170 |
| `top30-agents` | `batch-scout` (agent) | Read-only prep for `/batch`: checks the repo, splits the work into units that don't share files, assigns shared files an owner, finds a check per unit, keeps irreversible steps out, and returns the `/batch` line to paste. | ~160 |
| `top30-ui` | `component-registry` | EasyUI's registry pipeline, reverse-engineered for any repo. `registry_kit.py` scaffolds components (meta + test), builds a shadcn `registry.json` from imports (followed all the way down), validates it against the code, audits accessibility and reduced motion, and writes `llms.txt`. Rebuilds EasyUI's own 132 items with matching dependencies and metadata. Tests: `tests/registry_kit/`. | ~160 |
| `top30-ui` | `motion-component-builder` | The standard behind those components: shared spring tokens (template adapted from EasyUI, MIT notice kept), every state designed, real elements, focus-visible rings, reduced motion, transform/opacity only, metadata and a test per component. | ~180 |
| `top30-ui` | `ui-reverse-engineer` (agent) | Point it at a live component, recording or open-source code: it writes a behavior spec (anatomy, states, motion, keyboard, screen reader), rebuilds an original in your stack, and packages it for your registry. Copies behavior, not code or branding, unless the license allows and the notice is kept. | ~130 |
| `top30-ui` | `motion-forensics` | Diagnoses how a site's motion is really built before anyone tries to copy it. `motion_probe.js` runs in the page (or `probe_page.py` in headless Chromium) and `motion_report.py` names the architecture (procedural canvas, WebGL, library timelines, smooth scroll, CSS keyframes, scroll-driven CSS, Lottie, video), why DOM copying fails, and the numbers to reuse. Ships `scroll-scene.js`, a dependency-free engine for scroll-driven canvas scenes, with a demo. Built from zeromark.io, whose motion is ~2,150 lines of hand-written Canvas 2D. Tests: `tests/motion_forensics/`. | ~180 |
| `top30-ui` | `motion-detective` (agent) | Probes a live page, explains why earlier reverse-engineering failed, writes a motion spec, rebuilds an original with the matching technique, and proves it with side-by-side scroll strips. | ~170 |

Always-on costs measured with `claude plugin details` on 2026-11-04.

## Using them in the Claude app (claude.ai, desktop, mobile)

`claude-ai-skills/` holds ready-to-upload skill zips from 22 of the repos, including dbt and
Airflow skills. Upload in
Settings → Capabilities → Skills, one zip per skill. Each zip includes its project's license;
see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Start small: each enabled skill adds its
description to every chat.

## Status

<!-- status:start -->
_Checked 2026-11-09: 81 repos, 79 of 79 install-tested items passing, 1 needing attention. Token costs measured with 2.1.321 (Claude Code) on 2026-11-09._

**Top 30 from the post**

| # | Name | Repo | Stars | Upstream updated | Install test | Tokens/session | Status |
|---|---|---|---|---|---|---|---|
| 1 | Karpathy Skills | [multica-ai/andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills) | 231.3k | 2026-04-20 | pass (2026-11-09) | ~66 | OK |
| 2 | Matt Pocock Skills | [mattpocock/skills](https://github.com/mattpocock/skills) | 319.6k | 2026-11-09 | pass (2026-11-09) | ~1,169 | OK |
| 3 | ECC (Everything Claude Code) | [affaan-m/ECC](https://github.com/affaan-m/ECC) | 300.2k | 2026-11-09 | pass (2026-11-09) | ~33,844 | OK |
| 4 | Agent Skills (Addy Osmani) | [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) | 114.5k | 2026-11-01 | pass (2026-11-09) | ~2,999 | OK |
| 5 | Superpowers | [obra/superpowers](https://github.com/obra/superpowers) | 315.1k | 2026-11-03 | pass (2026-11-09) | ~706 | OK |
| 6 | Ponytail | [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail) | 187.6k | 2026-10-29 | pass (2026-11-09) | ~430 | OK |
| 7 | Career Ops | [career-ops-hq/career-ops](https://github.com/career-ops-hq/career-ops) | 81.5k | 2026-11-09 | pass (2026-11-09) | ~116 | OK |
| 8 | REA (Reverse Engineer Anything) | [morluto/rea](https://github.com/morluto/rea) | 446.6k | 2026-11-09 | pass (2026-11-09) | n/a (MCP) | OK |
| 9 | Graphify | [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify) | 145k | 2026-11-09 | pass (2026-11-09) | n/a (CLI skill) | OK |
| 10 | Understand Anything | [Egonex-AI/Understand-Anything](https://github.com/Egonex-AI/Understand-Anything) | 91.7k | 2026-11-09 | pass (2026-11-09) | ~870 | OK |
| 11 | Last 30 Days | [mvanhorn/last30days-skill](https://github.com/mvanhorn/last30days-skill) | 67.1k | 2026-11-09 | pass (2026-11-09) | ~67 | OK |
| 12 | Agent Reach | [Panniantong/Agent-Reach](https://github.com/Panniantong/Agent-Reach) | 110.6k | 2026-11-08 | pass (2026-11-09) | n/a (CLI skill) | OK |
| 13 | Headroom | [headroomlabs-ai/headroom](https://github.com/headroomlabs-ai/headroom) | 79.2k | 2026-11-09 | pass (2026-11-09) | ~0 | OK |
| 14 | BMAD Method | [bmad-code-org/BMAD-METHOD](https://github.com/bmad-code-org/BMAD-METHOD) | 55.2k | 2026-11-08 | pass (2026-11-09) | per project | OK |
| 15 | Claude-Mem | [thedotmack/claude-mem](https://github.com/thedotmack/claude-mem) | 115.4k | 2026-11-09 | pass (2026-11-09) | ~2,141 | OK |
| 16 | gstack | [garrytan/gstack](https://github.com/garrytan/gstack) | 140.9k | 2026-11-09 | pass (2026-11-09) | n/a (skills dir) | OK |
| 17 | Caveman | [JuliusBrussee/caveman](https://github.com/JuliusBrussee/caveman) | 118.6k | 2026-11-09 | pass (2026-11-09) | ~1,366 | OK |
| 18 | GSD (Get Shit Done) | [open-gsd/gsd-core](https://github.com/open-gsd/gsd-core) | 11.4k | 2026-11-09 | pass (2026-11-09) | n/a (commands) | OK |
| 19 | Taste | [Leonxlnx/taste-skill](https://github.com/Leonxlnx/taste-skill) | 112.5k | 2026-11-08 | pass (2026-11-09) | ~235 | OK |
| 20 | Archify | [tt-a1i/archify](https://github.com/tt-a1i/archify) | 95k | 2026-11-09 | pass (2026-11-09) | n/a (skill) | OK |
| 21 | Diagram Design | [cathrynlavery/diagram-design](https://github.com/cathrynlavery/diagram-design) | 66.1k | 2026-11-09 | pass (2026-11-09) | ~384 | OK |
| 22 | Impeccable | [pbakaus/impeccable](https://github.com/pbakaus/impeccable) | 106.8k | 2026-11-09 | pass (2026-11-09) | ~212 | OK |
| 23 | UI UX Pro Max | [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | 147.3k | 2026-11-07 | pass (2026-11-09) | ~709 | OK |
| 24 | PPT Master | [hugohe3/ppt-master](https://github.com/hugohe3/ppt-master) | 75.2k | 2026-11-09 | pass (2026-11-09) | ~139 | OK |
| 25 | Marketing Skills | [coreyhaines31/marketingskills](https://github.com/coreyhaines31/marketingskills) | 59.4k | 2026-11-09 | pass (2026-11-09) | ~5,059 | OK |
| 26 | Skills by Anthropic | [anthropics/skills](https://github.com/anthropics/skills) | 190.8k | 2026-11-06 | pass (2026-11-09) | ~759 + ~939 | OK |
| 27 | OpenMontage | [OpenMontageInc/OpenMontage](https://github.com/OpenMontageInc/OpenMontage) | 79.1k | 2026-11-09 | pass (2026-11-09) | per project | OK |
| 28 | Humanizer | [blader/humanizer](https://github.com/blader/humanizer) | 67.1k | 2026-10-28 | pass (2026-11-09) | ~90 | OK |
| 29 | HyperFrames | [heygen-com/hyperframes](https://github.com/heygen-com/hyperframes) | 81.6k | 2026-11-09 | pass (2026-11-09) | ~702 | OK |
| 30 | I Have ADHD | [ayghri/i-have-adhd](https://github.com/ayghri/i-have-adhd) | 60.6k | 2026-10-19 | pass (2026-11-09) | ~67 | OK |

**Data & ops toolkit**

| # | Name | Repo | Stars | Upstream updated | Install test | Tokens/session | Status |
|---|---|---|---|---|---|---|---|
| 31 | Snowflake AI Kit (Cortex Code) | [Snowflake-Labs/snowflake-ai-kit](https://github.com/Snowflake-Labs/snowflake-ai-kit) | 42 | 2026-11-06 | pass (2026-11-09) | ~187 | OK |
| 32 | dbt Agent Skills | [dbt-labs/dbt-agent-skills](https://github.com/dbt-labs/dbt-agent-skills) | 759 | 2026-11-06 | pass (2026-11-09) | ~1,136 + ~305 | OK |
| 33 | dbt MCP server | [dbt-labs/dbt-mcp](https://github.com/dbt-labs/dbt-mcp) | 618 | 2026-11-05 | pass (2026-11-09) | n/a | OK |
| 34 | Astronomer Airflow agents | [astronomer/agents](https://github.com/astronomer/agents) | 459 | 2026-11-02 | pass (2026-11-09) | ~3,961 | OK |
| 35 | Snowflake cost monitoring (dbt) | [get-select/dbt-snowflake-monitoring](https://github.com/get-select/dbt-snowflake-monitoring) | 264 | 2026-03-18 | manual (2026-10-25) | n/a | OK |
| 36 | Elementary (data observability) | [elementary-data/elementary](https://github.com/elementary-data/elementary) | 2.4k | 2026-11-05 | pass (2026-11-09) | n/a | OK |
| 37 | Great Expectations | [fivetran/great_expectations](https://github.com/fivetran/great_expectations) | 11.9k | 2026-11-09 | pass (2026-11-09) | n/a | OK |
| 38 | Agent Toolkit for AWS | [aws/agent-toolkit-for-aws](https://github.com/aws/agent-toolkit-for-aws) | 3.4k | 2026-11-09 | pass (2026-11-09) | ~5,018 + ~3,855 | OK |
| 39 | AWS MCP servers (data & ops) | [awslabs/mcp](https://github.com/awslabs/mcp) | 9.9k | 2026-11-09 | pass (2026-11-09) | n/a | OK |
| 40 | Oracle SQLcl MCP server | [oracle/mcp](https://github.com/oracle/mcp) | 476 | 2026-11-04 | pass (2026-11-09) | n/a | OK |
| 41 | SQLGlot | [tobymao/sqlglot](https://github.com/tobymao/sqlglot) | 9.8k | 2026-11-09 | pass (2026-11-09) | n/a | OK |
| 42 | SQLFluff | [sqlfluff/sqlfluff](https://github.com/sqlfluff/sqlfluff) | 10k | 2026-11-09 | pass (2026-11-09) | n/a | OK |
| 43 | Informatica for Claude (IDMC) | [forcedotcom/informatica-claude-plugins](https://github.com/forcedotcom/informatica-claude-plugins) | 1 | 2026-09-15 | pass (2026-11-09) | ~234 | OK |
| 44 | Anthropic knowledge-work plugins | [anthropics/knowledge-work-plugins](https://github.com/anthropics/knowledge-work-plugins) | 35.3k | 2026-11-07 | pass (2026-11-09) | ~695 + ~868 + ~675 | OK |
| 45 | Jira & Confluence MCP (Data Center) | [sooperset/mcp-atlassian](https://github.com/sooperset/mcp-atlassian) | 6.1k | 2026-11-08 | pass (2026-11-09) | n/a | OK |
| 46 | Apache DevLake (DORA dashboards) | [apache/devlake](https://github.com/apache/devlake) | 3.2k | 2026-11-09 | pass (2026-11-09) | n/a | OK |
| 47 | Middleware (DORA metrics) | [middlewarehq/middleware](https://github.com/middlewarehq/middleware) | 1.6k | 2026-08-03 | pass (2026-11-09) | n/a | OK |
| 48 | Claude Code ROI monitoring | [anthropics/claude-code-monitoring-guide](https://github.com/anthropics/claude-code-monitoring-guide) | 388 | 2025-07-29 | pass (2026-11-09) | n/a | OK |
| 49 | ccusage | [ccusage/ccusage](https://github.com/ccusage/ccusage) | 19.4k | 2026-11-09 | pass (2026-11-09) | n/a | OK |
| 50 | Grafana OTel LGTM (all-in-one) | [grafana/docker-otel-lgtm](https://github.com/grafana/docker-otel-lgtm) | 2.1k | 2026-11-09 | pass (2026-11-09) | n/a | OK |
| 51 | Grafana MCP server | [grafana/mcp-grafana](https://github.com/grafana/mcp-grafana) | 3.7k | 2026-11-09 | pass (2026-11-09) | n/a | OK |
| 52 | Keep (alert hub & AIOps) | [keephq/keep](https://github.com/keephq/keep) | 12.5k | 2026-11-09 | pass (2026-11-09) | n/a | OK |
| 53 | HolmesGPT (AI SRE agent) | [HolmesGPT/holmesgpt](https://github.com/HolmesGPT/holmesgpt) | 3.8k | 2026-11-09 | pass (2026-11-09) | n/a | OK |
| 54 | Uptime Kuma (status pages) | [louislam/uptime-kuma](https://github.com/louislam/uptime-kuma) | 93.4k | 2026-11-09 | pass (2026-11-09) | n/a | OK |
| 55 | Dynatrace for AI (plugin + MCP) | [Dynatrace/dynatrace-for-ai](https://github.com/Dynatrace/dynatrace-for-ai) | 177 | 2026-11-09 | pass (2026-11-09) | ~6,364 | OK |
| 56 | PagerDuty MCP server (hosted) | [PagerDuty/pagerduty-mcp-server](https://github.com/PagerDuty/pagerduty-mcp-server) | 79 | 2026-09-04 | pass (2026-11-09) | n/a | OK |
| 57 | Datadog app investigator | [datadog-labs/claude-code-plugin](https://github.com/datadog-labs/claude-code-plugin) | 19 | 2026-11-03 | pass (2026-11-09) | ~455 + ~94 | OK |

**From '20 projects to open first'**

| # | Name | Repo | Stars | Upstream updated | Install test | Tokens/session | Status |
|---|---|---|---|---|---|---|---|
| 58 | Ruflo (agent swarms) | [ruvnet/ruflo](https://github.com/ruvnet/ruflo) | 81.4k | 2026-11-09 | pass (2026-11-09) | ~417 | OK |
| 59 | wshobson agents (plugin packs) | [wshobson/agents](https://github.com/wshobson/agents) | 42.4k | 2026-11-09 | pass (2026-11-09) | ~492 + ~903 + ~111 | OK |
| 60 | planning-with-files | [OthmanAdi/planning-with-files](https://github.com/OthmanAdi/planning-with-files) | 28k | 2026-11-07 | pass (2026-11-09) | ~736 | OK |
| 61 | rtk (OSS edition) | [rtk-ai/rtk](https://github.com/rtk-ai/rtk) | 86k | 2026-11-09 | pass (2026-11-09) | n/a | OK |
| 62 | context-mode | [mksglu/context-mode](https://github.com/mksglu/context-mode) | 33.8k | 2026-11-09 | pass (2026-11-09) | ~60 | OK |
| 63 | video-shotcraft | [Vincentwei1021/video-shotcraft](https://github.com/Vincentwei1021/video-shotcraft) | 18.2k | 2026-11-09 | pass (2026-11-09) | n/a | OK |
| 64 | CC Switch (desktop) | [farion1231/cc-switch](https://github.com/farion1231/cc-switch) | 153.1k | 2026-11-09 | manual (2026-10-26) | n/a | OK |
| 65 | pm-skills | [phuryn/pm-skills](https://github.com/phuryn/pm-skills) | 27.8k | 2026-11-08 | pass (2026-11-09) | ~1,693 | OK |
| 66 | claude-skills (380+ skills) | [alirezarezvani/claude-skills](https://github.com/alirezarezvani/claude-skills) | 29.5k | 2026-11-05 | pass (2026-11-09) | ~2,618 + ~66 + ~69 | OK |

**Anthropic's repos to build with**

| # | Name | Repo | Stars | Upstream updated | Install test | Tokens/session | Status |
|---|---|---|---|---|---|---|---|
| 67 | Prompt engineering tutorial | [anthropics/prompt-eng-interactive-tutorial](https://github.com/anthropics/prompt-eng-interactive-tutorial) | 39.2k | 2026-08-28 | pass (2026-11-09) | n/a | OK |
| 68 | Claude quickstarts | [anthropics/claude-quickstarts](https://github.com/anthropics/claude-quickstarts) | 20k | 2026-11-06 | pass (2026-11-09) | n/a | OK |
| 69 | Claude Agent SDK (Python) | [anthropics/claude-agent-sdk-python](https://github.com/anthropics/claude-agent-sdk-python) | 8.5k | 2026-11-09 | pass (2026-11-09) | n/a | OK |
| 70 | Claude Code (the CLI) | [anthropics/claude-code](https://github.com/anthropics/claude-code) | 155.1k | 2026-11-09 | pass (2026-11-09) | n/a | OK |
| 71 | Claude Code Action (GitHub) | [anthropics/claude-code-action](https://github.com/anthropics/claude-code-action) | 9.9k | 2026-11-09 | pass (2026-11-09) | n/a | OK |

**From the '27 skills, one at a time' post**

| # | Name | Repo | Stars | Upstream updated | Install test | Tokens/session | Status |
|---|---|---|---|---|---|---|---|
| 72 | Obsidian Skills | [kepano/obsidian-skills](https://github.com/kepano/obsidian-skills) | 51.3k | 2026-09-15 | pass (2026-11-09) | ~403 | OK |
| 73 | NotebookLM skill | [PleasePrompto/notebooklm-skill](https://github.com/PleasePrompto/notebooklm-skill) | 7.8k | 2026-09-10 | pass (2026-11-09) | ~75 (est., skills dir) | ⚠ Upstream repo is archived (read-only). |
| 74 | Hugging Face skills | [huggingface/skills](https://github.com/huggingface/skills) | 11.3k | 2026-10-30 | pass (2026-11-09) | ~200 (est., skills dir) | OK |
| 75 | n8n skills | [czlonkowski/n8n-skills](https://github.com/czlonkowski/n8n-skills) | 6.6k | 2026-10-24 | pass (2026-11-09) | ~2,817 | OK |
| 76 | Vercel agent skills | [vercel-labs/agent-skills](https://github.com/vercel-labs/agent-skills) | 33.8k | 2026-10-28 | pass (2026-11-09) | ~250 (est., skills dir) | OK |
| 77 | Trail of Bits skills | [trailofbits/skills](https://github.com/trailofbits/skills) | 8.1k | 2026-11-06 | pass (2026-11-09) | ~47 | OK |
| 78 | Context engineering skills | [muratcankoylan/Agent-Skills-for-Context-Engineering](https://github.com/muratcankoylan/Agent-Skills-for-Context-Engineering) | 18.3k | 2026-10-12 | pass (2026-11-09) | ~1,992 | OK |

**Picked since the posts**

| # | Name | Repo | Stars | Upstream updated | Install test | Tokens/session | Status |
|---|---|---|---|---|---|---|---|
| 79 | EasyUI | [Surajmaurya1/easyui](https://github.com/Surajmaurya1/easyui) | 282 | 2026-11-04 | pass (2026-11-09) | n/a (copied source) | OK |
| 80 | Interfaces skills | [jakubkrehel/skills](https://github.com/jakubkrehel/skills) | 11.9k | 2026-11-09 | pass (2026-11-09) | ~601 | OK |
| 81 | Busabase | [busabase/busabase](https://github.com/busabase/busabase) | 760 | 2026-11-07 | pass (2026-11-09) | ~470 (est., skills dir) | OK |
<!-- status:end -->

## Things worth knowing before you pick

- **Token cost**: ECC and Marketing Skills are by far the heaviest (see the table); most single-skill plugins add under 1k tokens per session. The figures are Claude Code's own estimates and shift between CLI versions.
- **GSD moved**: `gsd-build/get-shit-done` was archived; it continues as `open-gsd/gsd-core` (Node 24+).
- **Caveman**: an independent placebo test (skill-placebo) found no significant output-token saving on Opus 5.5.
- **REA**: fake "REA.exe" copies circulate. Use only github.com/morluto/rea, rea.tools, or npm `rea-agents`.
- **gstack** asks you to add CLAUDE.md lines making Claude use its own /browse instead of Claude in Chrome.
- **OpenMontage** is AGPL-3.0; its AI generation providers need your own API keys.
- **Claude-Mem** fails Claude Code's plugin-name policy check (names can't start with "claude-") but installs and runs.
- **Licences in the "20 to open first" additions**: context-mode is Elastic License 2.0 (source-available, not open source); rtk's default download adds a BUSL-1.1 engine, so the installer uses the Apache-2.0 OSS edition. Everything else added there is MIT or Apache-2.0.
- **rtk** says its 60–90% figure is smaller bash output, not an equally smaller bill. `rtk init -g` adds a hook and edits your global CLAUDE.md.
- **CC Switch** is a desktop app that stores your provider API keys locally; at work, use only providers your firm approves.
- **Skills by Anthropic** (docx/xlsx/pptx/pdf) are already built into the Claude app; install them only for Claude Code.

## How it's put together

| Path | What |
|---|---|
| `catalog.json` | Single source of truth: repo, install/verify commands, notes, zip config, upstream status. |
| `install.sh`, `verify.sh` | Generated from the catalog. Bash 3.2 compatible. |
| `claude-ai-skills/` | Skill zips + `_manifest.json` (skill, source path, upstream commit, license). |
| `playbooks/` | Role playbooks and the at-work guardrails page. |
| `guide/` | Field guide page (`index.html` is generated from `template.html`). Published to GitHub Pages. |
| `sources/` | Upstream repos as submodules, pinned to the last checked commit. `git submodule update --init --depth 1 sources/30-i-have-adhd` fetches one. |
| `plugins/`, `.claude-plugin/` | This repo's own plugin marketplace (`top30-data`, `top30-ops`, `top30-coach`). |
| `examples/sql-review-agent/` | A working Agent SDK agent: read-only Snowflake SQL review with a custom tool, guard hook and budget cap. |
| `templates/claude-code-action/` | GitHub workflows to copy: @claude mentions, and SQL review on Amazon Bedrock. `sql_checks.py` there is a copy of the agent's `checks.py` (CI keeps them identical). |
| `examples/prompt-caching/` | Measures what prompt caching saves on your own document, from the API's usage numbers (write premium included). |
| `scripts/ab.py` | Before/after test for one plugin: same task with it off and on, cost, tokens and pass rate compared. |
| `tests/` | Tests for the skills and scripts built here (run in CI, no network). |
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
