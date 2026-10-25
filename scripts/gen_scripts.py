"""Generate install.sh and verify.sh from catalog.json (single source of truth)."""
import json, shlex, sys, os

kit = sys.argv[1]
cat = json.load(open(os.path.join(kit, "catalog.json")))
items = cat["items"]
rows = cat["rows"]

def q(s):
    return shlex.quote(s)

L = []
L.append("""#!/usr/bin/env bash
# Claude plugins kit — installs any of the 30 plugins with their official commands.
# Usage:
#   ./install.sh                 interactive menu
#   ./install.sh 1 5 30          install items by number
#   ./install.sh row 3           install a whole row
#   ./install.sh --list          list everything
#   ./install.sh --dry-run 3 17  show commands without running them
#   ./install.sh --yes 30        skip the per-item confirmation
# Works with macOS's default bash 3.2. Nothing runs without showing you the commands first.
set -u
DRY=0; YES=0; SEL=""
""")
L.append("ROW_NAMES=(" + " ".join(q(rows[str(i)]) for i in range(1, 6)) + ")")
L.append("NAMES=(" + " ".join(q(it["name"]) for it in items) + ")")
L.append("REPOS=(" + " ".join(q(it["repo"]) for it in items) + ")")
L.append("ROWS=(" + " ".join(str(it["row"]) for it in items) + ")")
L.append("NEEDS=(" + " ".join(q(" ".join(it["needs"])) for it in items) + ")")
L.append("NOTES=(" + " ".join(q(it["note"]) for it in items) + ")")
L.append("USES=(" + " ".join(q(it["use"]) for it in items) + ")")
L.append("COST=(" + " ".join(q(it["always_on"]) for it in items) + ")")
L.append("")
L.append("cmds_for() {  # prints one command per line for item $1")
L.append("  case \"$1\" in")
for it in items:
    body = "\\n".join(c.replace("\\", "\\\\").replace("'", "'\\''") for c in it["install"])
    L.append(f"    {it['n']}) printf '%b\\n' '{body}' ;;")
L.append("  esac\n}")
L.append("")
L.append(r'''
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

list_all() {
  local r i
  for r in 1 2 3 4 5; do
    printf '\n\033[1mRow %s — %s\033[0m\n' "$r" "${ROW_NAMES[$((r-1))]}"
    for i in $(seq 0 29); do
      [ "${ROWS[$i]}" = "$r" ] || continue
      printf '  %2d. %-32s %-40s ~tokens/session: %s\n' "$((i+1))" "${NAMES[$i]}" "github.com/${REPOS[$i]}" "${COST[$i]}"
    done
  done
  echo
}

install_one() {
  local n=$1 i=$(( $1 - 1 ))
  if [ "$n" -lt 1 ] || [ "$n" -gt 30 ]; then echo "Skip: $n is not 1-30"; return 1; fi
  printf '\n\033[1m[%d] %s\033[0m  (github.com/%s)\n' "$n" "${NAMES[$i]}" "${REPOS[$i]}"
  [ -n "${NOTES[$i]}" ] && printf '  Note: %s\n' "${NOTES[$i]}"
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
    -h|--help) sed -n '2,12p' "$0"; exit 0;;
    row) shift; for i in $(seq 0 29); do [ "${ROWS[$i]}" = "$1" ] && SEL="$SEL $((i+1))"; done;;
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
''')
open(os.path.join(kit, "install.sh"), "w").write("\n".join(L))

V = ["#!/usr/bin/env bash",
     "# Checks that installed plugins work. ./verify.sh (all)  or  ./verify.sh 5 30",
     "set -u", "verify_cmd() {", "  case \"$1\" in"]
for it in items:
    v = it["verify"].replace("'", "'\\''")
    V.append(f"    {it['n']}) echo '{v}' ;;")
V += ["  esac", "}"]
V.append("NAMES=(" + " ".join(q(it["name"]) for it in items) + ")")
V.append(r'''
SEL="$*"; [ -z "$SEL" ] && SEL=$(seq 1 30)
pass=0; fail=0
for n in $SEL; do
  c=$(verify_cmd "$n"); [ -z "$c" ] && continue
  if ( eval "$c" ) >/dev/null 2>&1; then printf '  \033[32mPASS\033[0m %2d %s\n' "$n" "${NAMES[$((n-1))]}"; pass=$((pass+1))
  else printf '  \033[90m----\033[0m %2d %s  (not installed or check failed: %s)\n' "$n" "${NAMES[$((n-1))]}" "$c"; fail=$((fail+1)); fi
done
echo "$pass passed, $fail not detected."
''')
open(os.path.join(kit, "verify.sh"), "w").write("\n".join(V))
os.chmod(os.path.join(kit, "install.sh"), 0o755)
os.chmod(os.path.join(kit, "verify.sh"), 0o755)
print("ok")
