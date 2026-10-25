#!/usr/bin/env bash
# Claude plugins kit — installs any of the 30 plugins with their official commands.
# Generated from catalog.json by scripts/kit.py render. Do not edit by hand.
# Usage:
#   ./install.sh                 interactive menu
#   ./install.sh 1 5 30          install items by number
#   ./install.sh row 3           install a whole row
#   ./install.sh --list          list everything
#   ./install.sh --status        health of every item from the last daily check
#   ./install.sh --dry-run 3 17  show commands without running them
#   ./install.sh --yes 30        skip the per-item confirmation
# Works with macOS's default bash 3.2. Nothing runs without showing you the commands first.
set -u
DRY=0; YES=0; SEL=""
ROW_NAMES=('Code like a senior' 'Research and understanding' 'Big projects, fewer tokens' 'Design and visuals' 'Writing and video')
NAMES=('Karpathy Skills' 'Matt Pocock Skills' 'ECC (Everything Claude Code)' 'Agent Skills (Addy Osmani)' Superpowers Ponytail 'Career Ops' 'REA (Reverse Engineer Anything)' Graphify 'Understand Anything' 'Last 30 Days' 'Agent Reach' Headroom 'BMAD Method' Claude-Mem gstack Caveman 'GSD (Get Shit Done)' Taste Archify 'Diagram Design' Impeccable 'UI UX Pro Max' 'PPT Master' 'Marketing Skills' 'Skills by Anthropic' OpenMontage Humanizer HyperFrames 'I Have ADHD')
REPOS=(multica-ai/andrej-karpathy-skills mattpocock/skills affaan-m/ECC addyosmani/agent-skills obra/superpowers DietrichGebert/ponytail career-ops-hq/career-ops morluto/rea Graphify-Labs/graphify Egonex-AI/Understand-Anything mvanhorn/last30days-skill Panniantong/Agent-Reach headroomlabs-ai/headroom bmad-code-org/BMAD-METHOD thedotmack/claude-mem garrytan/gstack JuliusBrussee/caveman open-gsd/gsd-core Leonxlnx/taste-skill tt-a1i/archify cathrynlavery/diagram-design pbakaus/impeccable nextlevelbuilder/ui-ux-pro-max-skill hugohe3/ppt-master coreyhaines31/marketingskills anthropics/skills calesthio/OpenMontage blader/humanizer heygen-com/hyperframes ayghri/i-have-adhd)
ROWS=(1 1 1 1 1 1 2 2 2 2 2 2 3 3 3 3 3 3 4 4 4 4 4 4 5 5 5 5 5 5)
NEEDS=(claude claude claude claude claude claude 'claude node git' node python claude 'claude python' python 'python claude' node 'claude bun' 'git bun' claude node claude node claude claude 'claude python' 'claude python git' claude claude 'git python node ffmpeg' claude 'claude node ffmpeg' claude)
NOTES=('' '' 'Heaviest by far: ~47.6k tokens added to every session. Only download from github.com/affaan-m/ECC or npm ecc-universal.' '' '' '' 'Works as a project folder. Draft-only: never submits applications.' 'Setup targets macOS (installs Homebrew + Hopper). Fake trojan '"'"'REA.exe'"'"' copies exist: only use github.com/morluto/rea, rea.tools or npm rea-agents.' 'PyPI name is graphifyy (double y).' 'First /understand on a big repo burns a lot of tokens; later runs are incremental.' 'More sources unlock with keys in ~/.config/last30days/.env. Runs take 2-8 minutes.' 'Many guides still show '"'"'agent-reach install --env=auto'"'"'; v1.6 replaced it with '"'"'agent-reach setup'"'"'. X/Reddit need a login (agent-reach login <channel>); cookies stay local.' 'README itself says 15-20% savings for coding agents (60-95% is for JSON-heavy data).' 'Installs per project (run it in the project folder).' 'Runs a background worker (Bun). Data lives in ~/.claude-mem.' 'Its setup asks you to add CLAUDE.md lines telling Claude to use gstack'"'"'s /browse instead of Claude in Chrome.' 'An independent placebo test (skill-placebo) found no significant output-token saving and ~14% higher cost on Opus 5.5.' 'gsd-build/get-shit-done moved to open-gsd/gsd-core. gsd-core declares Node 24+ (worked on 22 with a warning).' '' '' '' '' '' 'Repo is ~110 MB. If pip refuses (macOS '"'"'externally-managed'"'"'), create a venv in ~/ppt-master first.' '~15.7k tokens per session for all 52. Installing only the skills you need is much lighter.' 'The Claude app already has these built in; this is for Claude Code.' 'AGPL-3.0. Generation providers (Veo, Kling, ElevenLabs...) need your own API keys; stock/archive and FFmpeg paths are free.' '' '' '')
USES=('Automatic once installed.' 'Run /setup-matt-pocock-skills once per repo, then /grill-me.' '/plugin configure ecc@ecc to set hook options.' '/spec then /plan then /build.' 'Automatic; starts with brainstorming before code.' '/ponytail:ponytail ultra, /ponytail:ponytail-review' 'cd ~/career-ops, add cv.md, run claude, then /career-ops <job URL>.' 'Ask: '"'"'Use REA to explain how search works in the Notes app.'"'"'' '/graphify . in Claude Code, or graphify update <path> (code-only, no LLM).' '/understand then /understand-dashboard' '/last30days <topic>; run /last30days setup to add API keys.' 'Ask the agent to read a tweet, Reddit thread or YouTube video.' 'headroom perf to see savings; headroom unwrap claude to undo.' 'Run inside a project folder, then /bmad-help.' 'Automatic; search with the mem-search skill.' '/office-hours, /plan-ceo-review, /review, /ship' '/caveman, /caveman-compress CLAUDE.md' '/gsd-help, then /gsd-new-project' 'Automatic on landing pages and redesigns.' ''"'"'Use archify to draw a high-level architecture of this repo.'"'"'' 'Ask for a diagram; it asks for brand tokens first.' '/impeccable init once, then /impeccable critique <target>' 'Automatic on UI work.' ''"'"'Make a deck from this PDF.'"'"'' 'Start with the product-marketing-context skill.' 'Automatic when you ask for a .docx/.xlsx/.pptx/.pdf.' 'Open Claude Code in ~/OpenMontage and describe the video.' '/humanizer <paste text>' '/hyperframes '"'"'Make a 10-second product intro.'"'"'' '/i-have-adhd once per session; '"'"'stop adhd mode'"'"' to turn off.')
COST=('~66' '~1,169' '~33,456' '~2,903' '~706' '~430' '~116' 'n/a (MCP)' 'n/a (CLI skill)' '~870' '~67' 'n/a (CLI skill)' '~0' 'per project' '~2,060' 'n/a (skills dir)' '~1,366' 'n/a (commands)' '~246' 'n/a (skill)' '~378' '~312' '~709' '~139' '~10,604' '~759 + ~939' 'per project' '~90' '~551' '~67')
PROBLEMS=('' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '')
VERIFIED=('pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25')
CATALOG_DATE=2026-10-25

cmds_for() {  # prints one command per line for item $1
  case "$1" in
    1) printf '%b\n' 'claude plugin marketplace add multica-ai/andrej-karpathy-skills\nclaude plugin install andrej-karpathy-skills@karpathy-skills' ;;
    2) printf '%b\n' 'claude plugin marketplace add mattpocock/skills\nclaude plugin install mattpocock-skills@mattpocock' ;;
    3) printf '%b\n' 'claude plugin marketplace add affaan-m/ECC\nclaude plugin install ecc@ecc' ;;
    4) printf '%b\n' 'claude plugin marketplace add addyosmani/agent-skills\nclaude plugin install agent-skills@addy-agent-skills' ;;
    5) printf '%b\n' 'claude plugin marketplace add obra/superpowers-marketplace\nclaude plugin install superpowers@superpowers-marketplace' ;;
    6) printf '%b\n' 'claude plugin marketplace add DietrichGebert/ponytail\nclaude plugin install ponytail@ponytail' ;;
    7) printf '%b\n' 'git clone --depth 1 https://github.com/career-ops-hq/career-ops.git ~/career-ops\ncd ~/career-ops && npm install' ;;
    8) printf '%b\n' 'npm install --global rea-agents\nrea setup' ;;
    9) printf '%b\n' 'pipx install graphifyy || python3 -m pip install --user graphifyy\ngraphify install' ;;
    10) printf '%b\n' 'claude plugin marketplace add Egonex-AI/Understand-Anything\nclaude plugin install understand-anything@understand-anything' ;;
    11) printf '%b\n' 'claude plugin marketplace add mvanhorn/last30days-skill\nclaude plugin install last30days@last30days-skill' ;;
    12) printf '%b\n' 'pipx install git+https://github.com/Panniantong/Agent-Reach.git || python3 -m pip install --user git+https://github.com/Panniantong/Agent-Reach.git\nagent-reach setup' ;;
    13) printf '%b\n' 'pipx install headroom-ai || python3 -m pip install --user headroom-ai\nclaude plugin marketplace add headroomlabs-ai/headroom\nclaude plugin install headroom@headroom-marketplace' ;;
    14) printf '%b\n' 'npx bmad-method install' ;;
    15) printf '%b\n' 'claude plugin marketplace add thedotmack/claude-mem\nclaude plugin install claude-mem@thedotmack' ;;
    16) printf '%b\n' 'git clone --depth 1 https://github.com/garrytan/gstack.git ~/.claude/skills/gstack\ncd ~/.claude/skills/gstack && ./setup' ;;
    17) printf '%b\n' 'claude plugin marketplace add JuliusBrussee/caveman\nclaude plugin install caveman@caveman' ;;
    18) printf '%b\n' 'npx @opengsd/gsd-core@latest --claude --global' ;;
    19) printf '%b\n' 'claude plugin marketplace add Leonxlnx/taste-skill\nclaude plugin install taste-skill@taste-skill' ;;
    20) printf '%b\n' 'npx -y skills add tt-a1i/archify -g -a claude-code --yes' ;;
    21) printf '%b\n' 'claude plugin marketplace add cathrynlavery/diagram-design\nclaude plugin install diagram-design@diagram-design' ;;
    22) printf '%b\n' 'claude plugin marketplace add pbakaus/impeccable\nclaude plugin install impeccable@impeccable' ;;
    23) printf '%b\n' 'claude plugin marketplace add nextlevelbuilder/ui-ux-pro-max-skill\nclaude plugin install ui-ux-pro-max@ui-ux-pro-max-skill' ;;
    24) printf '%b\n' 'git clone --depth 1 https://github.com/hugohe3/ppt-master.git ~/ppt-master\npython3 -m pip install --user -r ~/ppt-master/requirements.txt\nclaude plugin marketplace add hugohe3/ppt-master\nclaude plugin install ppt-master@ppt-master' ;;
    25) printf '%b\n' 'claude plugin marketplace add coreyhaines31/marketingskills\nclaude plugin install marketing-skills@marketingskills' ;;
    26) printf '%b\n' 'claude plugin marketplace add anthropics/skills\nclaude plugin install document-skills@anthropic-agent-skills\nclaude plugin install example-skills@anthropic-agent-skills' ;;
    27) printf '%b\n' 'git clone --depth 1 https://github.com/calesthio/OpenMontage.git ~/OpenMontage\ncd ~/OpenMontage && make setup' ;;
    28) printf '%b\n' 'claude plugin marketplace add blader/humanizer\nclaude plugin install humanizer@humanizer' ;;
    29) printf '%b\n' 'claude plugin marketplace add heygen-com/hyperframes\nclaude plugin install hyperframes@hyperframes\nnpx -y hyperframes browser ensure' ;;
    30) printf '%b\n' 'claude plugin marketplace add ayghri/i-have-adhd\nclaude plugin install i-have-adhd@i-have-adhd' ;;
  esac
}

have() { command -v "$1" >/dev/null 2>&1; }
check_needs() {
  local miss=""
  for t in $1; do
    case "$t" in
      claude) have claude || miss="$miss claude(Claude Code: https://docs.claude.com/en/docs/claude-code)";;
      node)   have node && have npx || miss="$miss node(>=22)";;
      python) have python3 || miss="$miss python3(>=3.10)";;
      bun)    have bun || miss="$miss bun(https://bun.sh)";;
      git)    have git || miss="$miss git";;
      ffmpeg) have ffmpeg || miss="$miss ffmpeg";;
    esac
  done
  echo "$miss"
}

flag() { [ -n "${PROBLEMS[$1]}" ] && printf ' \033[33m⚠\033[0m' || true; }

list_all() {
  local r i
  for r in 1 2 3 4 5; do
    printf '\n\033[1mRow %s — %s\033[0m\n' "$r" "${ROW_NAMES[$((r-1))]}"
    for i in $(seq 0 29); do
      [ "${ROWS[$i]}" = "$r" ] || continue
      printf '  %2d. %-32s %-40s ~tokens/session: %s%s\n' "$((i+1))" "${NAMES[$i]}" "github.com/${REPOS[$i]}" "${COST[$i]}" "$(flag $i)"
    done
  done
  printf '\nCatalog checked %s. ⚠ = needs attention, see ./install.sh --status\n\n' "$CATALOG_DATE"
}

show_status() {
  local i
  printf 'Catalog checked %s\n\n' "$CATALOG_DATE"
  for i in $(seq 0 29); do
    if [ -n "${PROBLEMS[$i]}" ]; then
      printf '  \033[33m⚠\033[0m %2d %-32s %s\n       %s\n' "$((i+1))" "${NAMES[$i]}" "install test: ${VERIFIED[$i]}" "${PROBLEMS[$i]}"
    else
      printf '  \033[32m✓\033[0m %2d %-32s %s\n' "$((i+1))" "${NAMES[$i]}" "install test: ${VERIFIED[$i]}"
    fi
  done
}

install_one() {
  local n=$1 i=$(( $1 - 1 ))
  if [ "$n" -lt 1 ] || [ "$n" -gt 30 ]; then echo "Skip: $n is not 1-30"; return 1; fi
  printf '\n\033[1m[%d] %s\033[0m  (github.com/%s)\n' "$n" "${NAMES[$i]}" "${REPOS[$i]}"
  [ -n "${NOTES[$i]}" ] && printf '  Note: %s\n' "${NOTES[$i]}"
  [ -n "${PROBLEMS[$i]}" ] && printf '  \033[33mNeeds attention (daily check %s): %s\033[0m\n' "$CATALOG_DATE" "${PROBLEMS[$i]}"
  local miss; miss=$(check_needs "${NEEDS[$i]}")
  if [ -n "$miss" ]; then printf '  \033[33mMissing prerequisites:%s\033[0m\n' "$miss"; [ "$DRY" = 1 ] || { echo "  Install those first, then re-run."; FAILED="$FAILED $n"; return 1; }; fi
  echo "  Commands:"; cmds_for "$n" | sed 's/^/    $ /'
  [ "$DRY" = 1 ] && return 0
  if [ "$YES" != 1 ]; then printf '  Run these? [y/N] '; read -r a </dev/tty; case "$a" in y|Y|yes) ;; *) echo "  Skipped."; return 0;; esac; fi
  local line rc=0
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    echo "  > $line"
    ( eval "$line" ) || { rc=$?; break; }
  done <<EOF
$(cmds_for "$n")
EOF
  if [ $rc = 0 ]; then printf '  \033[32mDone.\033[0m Use: %s\n' "${USES[$i]}"; OK="$OK $n"; else printf '  \033[31mFailed (exit %s).\033[0m\n' "$rc"; FAILED="$FAILED $n"; fi
}

OK=""; FAILED=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1;;
    --yes|-y) YES=1;;
    --list|-l) list_all; exit 0;;
    --status|-s) show_status; exit 0;;
    -h|--help) sed -n '2,13p' "$0"; exit 0;;
    row) shift; for i in $(seq 0 29); do [ "${ROWS[$i]}" = "${1:-0}" ] && SEL="$SEL $((i+1))"; done;;
    *) SEL="$SEL $1";;
  esac
  shift
done

if [ -z "$SEL" ]; then
  list_all
  echo "Tip from the post: don't install all 30. Pick the row that matches your week, then one plugin from it."
  printf 'Enter numbers (e.g. 5 30) or "row 3": '; read -r ans </dev/tty
  set -- $ans
  if [ "${1:-}" = "row" ]; then for i in $(seq 0 29); do [ "${ROWS[$i]}" = "${2:-0}" ] && SEL="$SEL $((i+1))"; done; else SEL="$*"; fi
fi

for n in $SEL; do install_one "$n"; done
echo
[ "$DRY" = 1 ] && { echo "Dry run only — nothing was installed."; exit 0; }
[ -n "$OK" ] && echo "Installed:$OK   (restart Claude Code to load new plugins; check with ./verify.sh$OK)"
[ -n "$FAILED" ] && { echo "Failed or blocked:$FAILED"; exit 1; }
exit 0
