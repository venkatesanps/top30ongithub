#!/usr/bin/env bash
# Copy the Claude Ship starter files into a target repository.
#
#   templates/claude-ship/apply.sh /path/to/repo                    # REVIEW.md + steward + verify
#   templates/claude-ship/apply.sh /path/to/repo --with-approvals   # also .claude/approvals.yml
#   templates/claude-ship/apply.sh /path/to/repo --dry-run          # show what would be copied
#
# Never overwrites a file that exists and never commits: /ship won't commit rule files, so you
# review, edit and commit them yourself (a person should approve the PR that adds rules).
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
target="" ; approvals=0 ; dry=0
for arg in "$@"; do
  case "$arg" in
    --with-approvals) approvals=1 ;;
    --dry-run) dry=1 ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    -*) echo "unknown option: $arg" >&2; exit 2 ;;
    *) target="$arg" ;;
  esac
done
[ -n "$target" ] || { echo "usage: $0 /path/to/repo [--with-approvals] [--dry-run]" >&2; exit 2; }
git -C "$target" rev-parse --show-toplevel >/dev/null 2>&1 || { echo "not a git repo: $target" >&2; exit 1; }
root="$(git -C "$target" rev-parse --show-toplevel)"

copy() {  # copy SRC DEST-relative-to-repo
  local src="$here/$1" dest="$root/$2"
  if [ -e "$dest" ]; then echo "skip   $2 (exists; merge by hand from templates/claude-ship/$1)"; return; fi
  if [ "$dry" = 1 ]; then echo "would  $2"; return; fi
  mkdir -p "$(dirname "$dest")" && cp "$src" "$dest" && echo "added  $2"
}

copy REVIEW.md REVIEW.md
copy steward.SKILL.md .claude/skills/steward/SKILL.md
copy verify.SKILL.md .claude/skills/verify/SKILL.md
if [ "$approvals" = 1 ]; then
  copy approvals.observe.yml .claude/approvals.yml
  echo "note   approvals.yml turns Approvals on once merged and can start billed reviews: clear it with an Owner and the budget owner first"
fi

cat <<'EOF'

Next:
  1. Replace the example commands and rules with your repo's own.
  2. Copy the "Always check" rules into CLAUDE.md too if you review locally (/code-review and /ship
     read CLAUDE.md, not REVIEW.md).
  3. git checkout -b claude-ship-rules && git add -p && git commit   (yourself: /ship won't commit these)
  4. Open a PR and have a teammate approve it.
EOF
