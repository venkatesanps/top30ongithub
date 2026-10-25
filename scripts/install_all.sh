#!/usr/bin/env bash
# Add each repo's Claude Code marketplace (local folder) and install every plugin it lists,
# in an isolated HOME. Logs one line per action to results.tsv.
export HOME=/home/claude/testhome
R=/home/claude/repos
S=/tmp/claude-0/-home-claude/8d161694-cdd0-507a-a2ab-f273944f1765/scratchpad
OUT=$S/results.tsv
: > "$OUT"
while IFS='|' read -r n cat name repo d; do
  d=${d:-$(basename "$repo")}
  mk="$R/$d/.claude-plugin/marketplace.json"
  if [ ! -f "$mk" ]; then
    printf '%s\t%s\tno-marketplace\t-\t-\n' "$n" "$d" >> "$OUT"; continue
  fi
  val=$(timeout 60 claude plugin validate "$R/$d" 2>&1 | tail -1 | tr '\t\n' '  ')
  mname=$(python3 -I -c 'import json,sys;print(json.load(open(sys.argv[1]))["name"])' "$mk")
  add=$(timeout 120 claude plugin marketplace add "$R/$d" 2>&1 | tail -1 | tr '\t\n' '  ')
  printf '%s\t%s\tmarketplace-add\t%s\t%s\n' "$n" "$d" "$mname" "$add" >> "$OUT"
  printf '%s\t%s\tvalidate\t%s\t%s\n' "$n" "$d" "$mname" "$val" >> "$OUT"
  for p in $(python3 -I -c 'import json,sys;[print(p["name"]) for p in json.load(open(sys.argv[1])).get("plugins",[])]' "$mk"); do
    res=$(timeout 300 claude plugin install "$p@$mname" 2>&1 | tail -1 | tr '\t\n' '  ')
    printf '%s\t%s\tinstall\t%s@%s\t%s\n' "$n" "$d" "$p" "$mname" "$res" >> "$OUT"
  done
done < "$S/repos.txt"
echo done
