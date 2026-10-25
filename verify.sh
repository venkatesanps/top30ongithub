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
    31) echo 'claude plugin list | grep -q snowflake-cortex-code' ;;
    32) echo 'claude plugin list | grep -q '\''dbt@dbt-agent-marketplace'\''' ;;
    33) echo 'command -v dbt-mcp' ;;
    34) echo 'claude plugin list | grep -q astronomer-data' ;;
    35) echo 'grep -q dbt_snowflake_monitoring packages.yml' ;;
    36) echo 'edr --help >/dev/null' ;;
    37) echo 'python3 -c '\''import great_expectations'\''' ;;
    38) echo 'claude plugin list | grep -q aws-data-analytics' ;;
    39) echo 'command -v awslabs.cloudwatch-mcp-server' ;;
    40) echo '~/sqlcl/bin/sql -V' ;;
    41) echo 'python3 -c "import sqlglot; print(sqlglot.transpile('\''SELECT NVL(a, 0), SYSDATE FROM dual'\'', read='\''oracle'\'', write='\''snowflake'\'')[0])"' ;;
    42) echo 'sqlfluff version' ;;
    43) echo 'claude plugin list | grep -q informatica-for-claude-platform' ;;
    44) echo 'claude plugin list | grep -q '\''engineering@knowledge-work-plugins'\''' ;;
    45) echo 'mcp-atlassian --help >/dev/null' ;;
    46) echo 'cd ~/devlake && docker compose ps --status running | grep -q devlake' ;;
    47) echo 'docker ps --filter name=middleware --filter status=running | grep -q middleware' ;;
    48) echo 'test -f ~/claude-code-monitoring-guide/claude_code_roi_full.md' ;;
    49) echo 'ccusage --help >/dev/null' ;;
    50) echo 'docker ps --filter name=lgtm --filter status=running | grep -q lgtm' ;;
    51) echo 'command -v mcp-grafana' ;;
    52) echo 'cd ~/keep && docker compose ps --status running | grep -q keep' ;;
    53) echo 'holmes version' ;;
    54) echo 'docker ps --filter name=uptime-kuma --filter status=running | grep -q uptime-kuma' ;;
    55) echo 'claude plugin list | grep -q '\''dynatrace@dynatrace-for-ai'\''' ;;
    56) echo 'claude mcp get pagerduty >/dev/null' ;;
  esac
}
NAMES=('Karpathy Skills' 'Matt Pocock Skills' 'ECC (Everything Claude Code)' 'Agent Skills (Addy Osmani)' Superpowers Ponytail 'Career Ops' 'REA (Reverse Engineer Anything)' Graphify 'Understand Anything' 'Last 30 Days' 'Agent Reach' Headroom 'BMAD Method' Claude-Mem gstack Caveman 'GSD (Get Shit Done)' Taste Archify 'Diagram Design' Impeccable 'UI UX Pro Max' 'PPT Master' 'Marketing Skills' 'Skills by Anthropic' OpenMontage Humanizer HyperFrames 'I Have ADHD' 'Snowflake AI Kit (Cortex Code)' 'dbt Agent Skills' 'dbt MCP server' 'Astronomer Airflow agents' 'Snowflake cost monitoring (dbt)' 'Elementary (data observability)' 'Great Expectations' 'Agent Toolkit for AWS' 'AWS MCP servers (data & ops)' 'Oracle SQLcl MCP server' SQLGlot SQLFluff 'Informatica for Claude (IDMC)' 'Anthropic knowledge-work plugins' 'Jira & Confluence MCP (Data Center)' 'Apache DevLake (DORA dashboards)' 'Middleware (DORA metrics)' 'Claude Code ROI monitoring' ccusage 'Grafana OTel LGTM (all-in-one)' 'Grafana MCP server' 'Keep (alert hub & AIOps)' 'HolmesGPT (AI SRE agent)' 'Uptime Kuma (status pages)' 'Dynatrace for AI (plugin + MCP)' 'PagerDuty MCP server (hosted)')
SEL="$*"; [ -z "$SEL" ] && SEL=$(seq 1 ${#NAMES[@]})
pass=0; fail=0
for n in $SEL; do
  c=$(verify_cmd "$n"); [ -z "$c" ] && continue
  if ( eval "$c" ) >/dev/null 2>&1; then printf '  \033[32mPASS\033[0m %2d %s\n' "$n" "${NAMES[$((n-1))]}"; pass=$((pass+1))
  else printf '  \033[90m----\033[0m %2d %s  (not installed or check failed: %s)\n' "$n" "${NAMES[$((n-1))]}" "$c"; fail=$((fail+1)); fi
done
echo "$pass passed, $fail not detected."
