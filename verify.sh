#!/usr/bin/env bash
# Checks that installed plugins work. ./verify.sh (all)  or  ./verify.sh 5 30
set -u
verify_cmd() {
  case "$1" in
    1) echo 'claude plugin list | grep -q andrej-karpathy-skills' ;;
    2) echo 'claude plugin list | grep -q mattpocock-skills' ;;
    3) echo 'claude plugin list | grep -q '\''ecc@ecc'\''' ;;
    4) echo 'claude plugin list | grep -q agent-skills@addy-agent-skills' ;;
    5) echo 'claude plugin list | grep -q superpowers@' ;;
    6) echo 'claude plugin list | grep -q ponytail@ponytail' ;;
    7) echo 'test -f ~/career-ops/package.json && test -d ~/career-ops/node_modules' ;;
    8) echo 'rea --version && rea doctor' ;;
    9) echo 'graphify --version' ;;
    10) echo 'claude plugin list | grep -q understand-anything' ;;
    11) echo 'claude plugin list | grep -q last30days' ;;
    12) echo 'agent-reach doctor' ;;
    13) echo 'headroom --version' ;;
    14) echo 'test -d .claude && ls .claude' ;;
    15) echo 'claude plugin list | grep -q claude-mem@thedotmack' ;;
    16) echo 'test -f ~/.claude/skills/gstack/SKILL.md' ;;
    17) echo 'claude plugin list | grep -q caveman@caveman' ;;
    18) echo 'ls ~/.claude/skills | grep -q gsd-help' ;;
    19) echo 'claude plugin list | grep -q taste-skill' ;;
    20) echo 'node ~/.claude/skills/archify/bin/archify.mjs doctor' ;;
    21) echo 'claude plugin list | grep -q diagram-design' ;;
    22) echo 'claude plugin list | grep -q impeccable@impeccable' ;;
    23) echo 'claude plugin list | grep -q ui-ux-pro-max' ;;
    24) echo 'claude plugin list | grep -q ppt-master' ;;
    25) echo 'claude plugin list | grep -q marketing-skills' ;;
    26) echo 'claude plugin list | grep -q document-skills' ;;
    27) echo 'cd ~/OpenMontage && make preflight' ;;
    28) echo 'claude plugin list | grep -q humanizer@humanizer' ;;
    29) echo 'npx -y hyperframes doctor' ;;
    30) echo 'claude plugin list | grep -q i-have-adhd' ;;
  esac
}
NAMES=('Karpathy Skills' 'Matt Pocock Skills' 'ECC (Everything Claude Code)' 'Agent Skills (Addy Osmani)' Superpowers Ponytail 'Career Ops' 'REA (Reverse Engineer Anything)' Graphify 'Understand Anything' 'Last 30 Days' 'Agent Reach' Headroom 'BMAD Method' Claude-Mem gstack Caveman 'GSD (Get Shit Done)' Taste Archify 'Diagram Design' Impeccable 'UI UX Pro Max' 'PPT Master' 'Marketing Skills' 'Skills by Anthropic' OpenMontage Humanizer HyperFrames 'I Have ADHD')
SEL="$*"; [ -z "$SEL" ] && SEL=$(seq 1 30)
pass=0; fail=0
for n in $SEL; do
  c=$(verify_cmd "$n"); [ -z "$c" ] && continue
  if ( eval "$c" ) >/dev/null 2>&1; then printf '  \033[32mPASS\033[0m %2d %s\n' "$n" "${NAMES[$((n-1))]}"; pass=$((pass+1))
  else printf '  \033[90m----\033[0m %2d %s  (not installed or check failed: %s)\n' "$n" "${NAMES[$((n-1))]}" "$c"; fail=$((fail+1)); fi
done
echo "$pass passed, $fail not detected."
