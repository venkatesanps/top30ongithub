#!/usr/bin/env bash
# Claude plugins kit — installs the Top 30 plugins and the data & ops toolkit with their official commands.
# Generated from catalog.json by scripts/kit.py render. Do not edit by hand.
# Usage:
#   ./install.sh                 interactive menu
#   ./install.sh 1 5 30          install items by number
#   ./install.sh row 3           install a whole row (rows 6-9 are the data & ops toolkit)
#   ./install.sh --list          list everything
#   ./install.sh --status        health of every item from the last daily check
#   ./install.sh --dry-run 3 17  show commands without running them
#   ./install.sh --yes 30        skip the per-item confirmation
# Works with macOS's default bash 3.2. Nothing runs without showing you the commands first.
set -u
DRY=0; YES=0; SEL=""
ROW_NAMES=('Code like a senior' 'Research and understanding' 'Big projects, fewer tokens' 'Design and visuals' 'Writing and video' 'Snowflake, dbt & data quality' 'AWS, Oracle & migrations' 'Manager & team productivity' 'Production monitoring & SRE')
ROW_COLL=('Top 30 from the post' 'Top 30 from the post' 'Top 30 from the post' 'Top 30 from the post' 'Top 30 from the post' 'Data & ops toolkit' 'Data & ops toolkit' 'Data & ops toolkit' 'Data & ops toolkit')
NAMES=('Karpathy Skills' 'Matt Pocock Skills' 'ECC (Everything Claude Code)' 'Agent Skills (Addy Osmani)' Superpowers Ponytail 'Career Ops' 'REA (Reverse Engineer Anything)' Graphify 'Understand Anything' 'Last 30 Days' 'Agent Reach' Headroom 'BMAD Method' Claude-Mem gstack Caveman 'GSD (Get Shit Done)' Taste Archify 'Diagram Design' Impeccable 'UI UX Pro Max' 'PPT Master' 'Marketing Skills' 'Skills by Anthropic' OpenMontage Humanizer HyperFrames 'I Have ADHD' 'Snowflake AI Kit (Cortex Code)' 'dbt Agent Skills' 'dbt MCP server' 'Astronomer Airflow agents' 'Snowflake cost monitoring (dbt)' 'Elementary (data observability)' 'Great Expectations' 'Agent Toolkit for AWS' 'AWS MCP servers (data & ops)' 'Oracle SQLcl MCP server' SQLGlot SQLFluff 'Informatica for Claude (IDMC)' 'Anthropic knowledge-work plugins' 'Jira & Confluence MCP (Data Center)' 'Apache DevLake (DORA dashboards)' 'Middleware (DORA metrics)' 'Claude Code ROI monitoring' ccusage 'Grafana OTel LGTM (all-in-one)' 'Grafana MCP server' 'Keep (alert hub & AIOps)' 'HolmesGPT (AI SRE agent)' 'Uptime Kuma (status pages)' 'Dynatrace for AI (plugin + MCP)' 'PagerDuty MCP server (hosted)')
REPOS=(multica-ai/andrej-karpathy-skills mattpocock/skills affaan-m/ECC addyosmani/agent-skills obra/superpowers DietrichGebert/ponytail career-ops-hq/career-ops morluto/rea Graphify-Labs/graphify Egonex-AI/Understand-Anything mvanhorn/last30days-skill Panniantong/Agent-Reach headroomlabs-ai/headroom bmad-code-org/BMAD-METHOD thedotmack/claude-mem garrytan/gstack JuliusBrussee/caveman open-gsd/gsd-core Leonxlnx/taste-skill tt-a1i/archify cathrynlavery/diagram-design pbakaus/impeccable nextlevelbuilder/ui-ux-pro-max-skill hugohe3/ppt-master coreyhaines31/marketingskills anthropics/skills calesthio/OpenMontage blader/humanizer heygen-com/hyperframes ayghri/i-have-adhd Snowflake-Labs/snowflake-ai-kit dbt-labs/dbt-agent-skills dbt-labs/dbt-mcp astronomer/agents get-select/dbt-snowflake-monitoring elementary-data/elementary fivetran/great_expectations aws/agent-toolkit-for-aws awslabs/mcp oracle/mcp tobymao/sqlglot sqlfluff/sqlfluff forcedotcom/informatica-claude-plugins anthropics/knowledge-work-plugins sooperset/mcp-atlassian apache/devlake middlewarehq/middleware anthropics/claude-code-monitoring-guide ccusage/ccusage grafana/docker-otel-lgtm grafana/mcp-grafana keephq/keep HolmesGPT/holmesgpt louislam/uptime-kuma Dynatrace/dynatrace-for-ai PagerDuty/pagerduty-mcp-server)
ROWS=(1 1 1 1 1 1 2 2 2 2 2 2 3 3 3 3 3 3 4 4 4 4 4 4 5 5 5 5 5 5 6 6 6 6 6 6 6 7 7 7 7 7 7 8 8 8 8 8 8 9 9 9 9 9 9 9)
NEEDS=(claude claude claude claude claude claude 'claude node git' node python claude 'claude python' python 'python claude' node 'claude bun' 'git bun' claude node claude node claude claude 'claude python' 'claude python git' claude claude 'git python node ffmpeg' claude 'claude node ffmpeg' claude claude claude uv 'claude uv' python python python claude uv java python python claude claude uv docker docker 'docker git' node docker uv 'docker git' python docker claude claude)
NOTES=('' '' 'Heaviest by far: ~47.6k tokens added to every session. Only download from github.com/affaan-m/ECC or npm ecc-universal.' '' '' '' 'Works as a project folder. Draft-only: never submits applications.' 'Setup targets macOS (installs Homebrew + Hopper). Fake trojan '"'"'REA.exe'"'"' copies exist: only use github.com/morluto/rea, rea.tools or npm rea-agents.' 'PyPI name is graphifyy (double y).' 'First /understand on a big repo burns a lot of tokens; later runs are incremental.' 'More sources unlock with keys in ~/.config/last30days/.env. Runs take 2-8 minutes.' 'Many guides still show '"'"'agent-reach install --env=auto'"'"'; v1.6 replaced it with '"'"'agent-reach setup'"'"'. X/Reddit need a login (agent-reach login <channel>); cookies stay local.' 'README itself says 15-20% savings for coding agents (60-95% is for JSON-heavy data).' 'Installs per project (run it in the project folder).' 'Runs a background worker (Bun). Data lives in ~/.claude-mem.' 'Its setup asks you to add CLAUDE.md lines telling Claude to use gstack'"'"'s /browse instead of Claude in Chrome.' 'An independent placebo test (skill-placebo) found no significant output-token saving and ~14% higher cost on Opus 5.5.' 'gsd-build/get-shit-done moved to open-gsd/gsd-core. gsd-core declares Node 24+ (worked on 22 with a warning).' '' '' '' '' '' 'Repo is ~110 MB. If pip refuses (macOS '"'"'externally-managed'"'"'), create a venv in ~/ppt-master first.' '~15.7k tokens per session for all 52. Installing only the skills you need is much lighter.' 'The Claude app already has these built in; this is for Claude Code.' 'AGPL-3.0. Generation providers (Veo, Kling, ElevenLabs...) need your own API keys; stock/archive and FFmpeg paths are free.' '' '' '' 'Needs the Cortex Code CLI and a Snowflake connection in ~/.snowflake/connections.toml. Its migration agent (in Cortex Code: /migrate) covers Oracle sources and converts Informatica jobs to dbt; Oracle code extraction is marked '"'"'planned'"'"' by Snowflake.' 'dbt-migration includes migrating-dbt-project-across-platforms, useful when moving warehouse SQL to Snowflake.' '' '' 'Needs a dbt project on Snowflake with a role that can read SNOWFLAKE.ACCOUNT_USAGE.' '' 'Soda Core is an alternative but uses the Elastic License, which some firms restrict.' 'Uses your AWS credentials; start with a read-only role.' 'The repo has 60+ servers (Redshift, DynamoDB, Step Functions, IaC...). Read-only IAM first.' 'Needs Java 17+. Point it at a read-only schema or a dev copy, never production.' 'Handles SQL, not PL/SQL procedural code; pair it with Claude for packages and procedures.' '' 'For Informatica'"'"'s cloud (IDMC). For PowerCenter-to-Snowflake conversion, Snowflake'"'"'s free SnowConvert AI and Cortex Code'"'"'s /migrate agent are the tools to evaluate.' '' 'Atlassian'"'"'s official MCP server (atlassian/atlassian-mcp-server) only works with Atlassian Cloud. Use --read-only mode until approved for writes.' 'Apache-2.0. Keep ENCRYPTION_SECRET safe; it encrypts the stored tokens.' 'Simpler than DevLake but Git-only (no Jira).' 'Telemetry includes per-user activity: agree on what'"'"'s collected with your team and firm first.' '' 'For trials and dev. Production Grafana stacks are usually run by a platform team (Grafana is AGPL-3.0).' 'Use a Viewer-role service account token.' MIT. 'Point it at read-only data sources; it runs the queries it decides on.' MIT. 'Replaces dynatrace-oss/dynatrace-mcp, archived after v2.1.2. One of the heavier plugins (skills plus the full MCP tool list). Grail queries can incur cost; scope the platform token to read-only.' 'PagerDuty moved development to this hosted server and archived the local repo, which is tracked here for notices.')
USES=('Automatic once installed.' 'Run /setup-matt-pocock-skills once per repo, then /grill-me.' '/plugin configure ecc@ecc to set hook options.' '/spec then /plan then /build.' 'Automatic; starts with brainstorming before code.' '/ponytail:ponytail ultra, /ponytail:ponytail-review' 'cd ~/career-ops, add cv.md, run claude, then /career-ops <job URL>.' 'Ask: '"'"'Use REA to explain how search works in the Notes app.'"'"'' '/graphify . in Claude Code, or graphify update <path> (code-only, no LLM).' '/understand then /understand-dashboard' '/last30days <topic>; run /last30days setup to add API keys.' 'Ask the agent to read a tweet, Reddit thread or YouTube video.' 'headroom perf to see savings; headroom unwrap claude to undo.' 'Run inside a project folder, then /bmad-help.' 'Automatic; search with the mem-search skill.' '/office-hours, /plan-ceo-review, /review, /ship' '/caveman, /caveman-compress CLAUDE.md' '/gsd-help, then /gsd-new-project' 'Automatic on landing pages and redesigns.' ''"'"'Use archify to draw a high-level architecture of this repo.'"'"'' 'Ask for a diagram; it asks for brand tokens first.' '/impeccable init once, then /impeccable critique <target>' 'Automatic on UI work.' ''"'"'Make a deck from this PDF.'"'"'' 'Start with the product-marketing-context skill.' 'Automatic when you ask for a .docx/.xlsx/.pptx/.pdf.' 'Open Claude Code in ~/OpenMontage and describe the video.' '/humanizer <paste text>' '/hyperframes '"'"'Make a 10-second product intro.'"'"'' '/i-have-adhd once per session; '"'"'stop adhd mode'"'"' to turn off.' 'Ask '"'"'show my warehouses and their credit use this week'"'"', or $cortex-run <task>.' 'Automatic on dbt work; try '"'"'why did last night'"'"'s job fail?'"'"'' 'claude mcp add dbt -- dbt-mcp, then ask about a model'"'"'s upstream sources.' 'Set AIRFLOW_API_URL to your Airflow, then '"'"'why did dag X fail last night?'"'"'' 'Point a dashboard at the daily_spend and query_history_enriched models.' 'edr report  (opens an HTML report of tests, anomalies and lineage)' 'Ask Claude to draft expectations for a table from its profile.' ''"'"'Design a Glue job that lands S3 files into Snowflake'"'"' or '"'"'why did this Lambda time out?'"'"'' ''"'"'Summarize CloudWatch errors for the ingest Lambda in the last 24h.'"'"'' ''"'"'Explain what PKG_DAILY_LOAD.run does and which tables it writes.'"'"'' 'python3 -c "import sqlglot; print(sqlglot.transpile(open('"'"'q.sql'"'"').read(), read='"'"'oracle'"'"', write='"'"'snowflake'"'"', pretty=True)[0])"' 'sqlfluff lint models/ --dialect snowflake ; sqlfluff fix to auto-format' ''"'"'Which catalog assets hold customer email, and who owns them?'"'"'' '/engineering:standup, /engineering:incident-response, /operations:status-report' ''"'"'List my team'"'"'s open P1 and P2 tickets older than 5 days and draft the standup summary.'"'"'' 'Connect Jira + your Git host in the config UI, then open '"'"'DORA'"'"' and '"'"'Jira'"'"' dashboards.' 'Review lead time and change failure rate per team every sprint.' 'Share the weekly report built from report-generation-prompt.md.' 'ccusage daily ; ccusage monthly' 'Instrument one service with OpenTelemetry and build its RED dashboard.' ''"'"'What changed on the payments dashboard in the hour before the 2am alert?'"'"'' 'Connect two alert sources, then build a correlation rule for one noisy service.' 'Set ANTHROPIC_API_KEY, then: holmes ask '"'"'why is the orders API p99 latency up since 09:00?'"'"' --model anthropic/<model>' 'Give leadership one status page for the services your team owns.' 'export DT_ENVIRONMENT=https://<env>.apps.dynatrace.com DT_PLATFORM_TOKEN=..., start Claude Code, then '"'"'list open problems affecting the trade-capture service'"'"'.' 'Run /mcp in Claude Code to sign in, then '"'"'who is on call for data-platform tonight, and what fired in the last 7 days?'"'"'')
COST=('~66' '~1,169' '~33,468' '~2,903' '~706' '~430' '~116' 'n/a (MCP)' 'n/a (CLI skill)' '~870' '~67' 'n/a (CLI skill)' '~0' 'per project' '~2,060' 'n/a (skills dir)' '~1,366' 'n/a (commands)' '~246' 'n/a (skill)' '~378' '~312' '~709' '~139' '~10,604' '~759 + ~939' 'per project' '~90' '~551' '~67' '~187' '~1,136 + ~305' n/a '~3,961' n/a n/a n/a '~4,762 + ~3,855' n/a n/a n/a n/a '~234' '~695 + ~868 + ~675' n/a n/a n/a n/a n/a n/a n/a n/a n/a n/a '~?' n/a)
PROBLEMS=('' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '' '')
VERIFIED=('pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'manual 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'pass 2026-10-25' 'untested 2026-10-25' 'untested 2026-10-25')
CATALOG_DATE=2026-10-25
N=${#NAMES[@]}

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
    31) printf '%b\n' 'claude plugin marketplace add Snowflake-Labs/snowflake-ai-kit\nclaude plugin install snowflake-cortex-code@snowflake-ai-kit' ;;
    32) printf '%b\n' 'claude plugin marketplace add dbt-labs/dbt-agent-skills\nclaude plugin install dbt@dbt-agent-marketplace\nclaude plugin install dbt-migration@dbt-agent-marketplace' ;;
    33) printf '%b\n' 'uv tool install dbt-mcp' ;;
    34) printf '%b\n' 'claude plugin marketplace add astronomer/agents\nclaude plugin install astronomer-data@astronomer' ;;
    35) printf '%b\n' 'printf '\''packages:\\n  - package: get-select/dbt_snowflake_monitoring\\n    version: [">=5.6.0", "<6.0.0"]\\n'\'' >> packages.yml\ndbt deps' ;;
    36) printf '%b\n' 'pipx install '\''elementary-data[snowflake]'\'' || python3 -m pip install --user '\''elementary-data[snowflake]'\''' ;;
    37) printf '%b\n' 'python3 -m pip install --user great_expectations' ;;
    38) printf '%b\n' 'claude plugin marketplace add aws/agent-toolkit-for-aws\nclaude plugin install aws-core@agent-toolkit-for-aws\nclaude plugin install aws-data-analytics@agent-toolkit-for-aws' ;;
    39) printf '%b\n' 'uv tool install awslabs.aws-dataprocessing-mcp-server\nuv tool install awslabs.cloudwatch-mcp-server\nuv tool install awslabs.billing-cost-management-mcp-server\nuv tool install awslabs.aws-documentation-mcp-server' ;;
    40) printf '%b\n' 'cd ~ && curl -fsSLo sqlcl-latest.zip https://download.oracle.com/otn_software/java/sqldeveloper/sqlcl-latest.zip && unzip -qo sqlcl-latest.zip' ;;
    41) printf '%b\n' 'python3 -m pip install --user sqlglot' ;;
    42) printf '%b\n' 'pipx install sqlfluff || python3 -m pip install --user sqlfluff' ;;
    43) printf '%b\n' 'claude plugin marketplace add anthropics/knowledge-work-plugins\nclaude plugin install informatica-for-claude-platform@knowledge-work-plugins' ;;
    44) printf '%b\n' 'claude plugin marketplace add anthropics/knowledge-work-plugins\nclaude plugin install engineering@knowledge-work-plugins\nclaude plugin install data@knowledge-work-plugins\nclaude plugin install operations@knowledge-work-plugins' ;;
    45) printf '%b\n' 'uv tool install mcp-atlassian' ;;
    46) printf '%b\n' 'mkdir -p ~/devlake && cd ~/devlake && curl -fsSLO https://github.com/apache/devlake/releases/latest/download/docker-compose.yml && curl -fsSLO https://github.com/apache/devlake/releases/latest/download/env.example && mv env.example .env\ncd ~/devlake && echo "ENCRYPTION_SECRET=$(openssl rand -base64 2000 | tr -dc A-Z | fold -w 128 | head -n 1)" >> .env && docker compose up -d' ;;
    47) printf '%b\n' 'docker run --name middleware -p 3333:3333 -p 9696:9696 -p 9697:9697 -v middleware_postgres_data:/var/lib/postgresql/data -v middleware_keys:/app/keys -d middlewareeng/middleware:latest' ;;
    48) printf '%b\n' 'git clone --depth 1 https://github.com/anthropics/claude-code-monitoring-guide.git ~/claude-code-monitoring-guide\ncd ~/claude-code-monitoring-guide && docker compose up -d' ;;
    49) printf '%b\n' 'npm install --global ccusage' ;;
    50) printf '%b\n' 'docker run -d --name lgtm -p 3000:3000 -p 4317:4317 -p 4318:4318 grafana/otel-lgtm:latest' ;;
    51) printf '%b\n' 'uv tool install mcp-grafana' ;;
    52) printf '%b\n' 'git clone --depth 1 https://github.com/keephq/keep.git ~/keep\ncd ~/keep && docker compose up -d' ;;
    53) printf '%b\n' 'pipx install holmesgpt || python3 -m pip install --user holmesgpt' ;;
    54) printf '%b\n' 'docker run -d --restart=always -p 3001:3001 -v uptime-kuma:/app/data --name uptime-kuma louislam/uptime-kuma:2' ;;
    55) printf '%b\n' 'claude plugin marketplace add Dynatrace/dynatrace-for-ai\nclaude plugin install dynatrace@dynatrace-for-ai' ;;
    56) printf '%b\n' 'claude mcp add --scope user --transport http pagerduty https://mcp.pagerduty.com/mcp' ;;
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
      uv)     have uv || miss="$miss uv(https://docs.astral.sh/uv)";;
      docker) have docker || miss="$miss docker";;
      java)   have java || miss="$miss java(17+)";;
    esac
  done
  echo "$miss"
}

flag() { [ -n "${PROBLEMS[$1]}" ] && printf ' \033[33m⚠\033[0m' || true; }

list_all() {
  local r i last=""
  for r in $(seq 1 ${#ROW_NAMES[@]}); do
    if [ "${ROW_COLL[$((r-1))]}" != "$last" ]; then last="${ROW_COLL[$((r-1))]}"; printf '\n\033[1;4m%s\033[0m\n' "$last"; fi
    printf '\n\033[1mRow %s — %s\033[0m\n' "$r" "${ROW_NAMES[$((r-1))]}"
    for i in $(seq 0 $((N-1))); do
      [ "${ROWS[$i]}" = "$r" ] || continue
      printf '  %2d. %-32s %-40s ~tokens/session: %s%s\n' "$((i+1))" "${NAMES[$i]}" "github.com/${REPOS[$i]}" "${COST[$i]}" "$(flag $i)"
    done
  done
  printf '\nCatalog checked %s. ⚠ = needs attention, see ./install.sh --status\n\n' "$CATALOG_DATE"
}

show_status() {
  local i
  printf 'Catalog checked %s\n\n' "$CATALOG_DATE"
  for i in $(seq 0 $((N-1))); do
    if [ -n "${PROBLEMS[$i]}" ]; then
      printf '  \033[33m⚠\033[0m %2d %-32s %s\n       %s\n' "$((i+1))" "${NAMES[$i]}" "install test: ${VERIFIED[$i]}" "${PROBLEMS[$i]}"
    else
      printf '  \033[32m✓\033[0m %2d %-32s %s\n' "$((i+1))" "${NAMES[$i]}" "install test: ${VERIFIED[$i]}"
    fi
  done
}

install_one() {
  local n=$1 i=$(( $1 - 1 ))
  case "$n" in ''|*[!0-9]*) echo "Skip: '$n' is not a number"; return 1;; esac
  if [ "$n" -lt 1 ] || [ "$n" -gt "$N" ]; then echo "Skip: $n is not 1-$N"; return 1; fi
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
    row) shift; for i in $(seq 0 $((N-1))); do [ "${ROWS[$i]}" = "${1:-0}" ] && SEL="$SEL $((i+1))"; done;;
    *) SEL="$SEL $1";;
  esac
  shift
done

if [ -z "$SEL" ]; then
  list_all
  echo "Tip: don't install everything. Pick the row that matches your week, then one item from it."
  printf 'Enter numbers (e.g. 5 30) or "row 3": '; read -r ans </dev/tty
  set -- $ans
  if [ "${1:-}" = "row" ]; then for i in $(seq 0 $((N-1))); do [ "${ROWS[$i]}" = "${2:-0}" ] && SEL="$SEL $((i+1))"; done; else SEL="$*"; fi
fi

for n in $SEL; do install_one "$n"; done
echo
[ "$DRY" = 1 ] && { echo "Dry run only — nothing was installed."; exit 0; }
[ -n "$OK" ] && echo "Installed:$OK   (restart Claude Code to load new plugins; check with ./verify.sh$OK)"
[ -n "$FAILED" ] && { echo "Failed or blocked:$FAILED"; exit 1; }
exit 0
