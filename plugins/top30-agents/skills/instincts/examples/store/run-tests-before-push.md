---
id: run-tests-before-push
trigger: "before git push"
confidence: 0.85
domain: "testing"
source: "session-observation"
scope: project
last_seen: 2026-11-19
---

# Run the tests before pushing

## Action
Run `python3 scripts/kit.py validate` and the changed area's tests; push only if both pass.

## Evidence
- 2026-11-04 correction: user asked why CI broke after a push with no local run
- 2026-11-07 repeat: validate run before push in 3 sessions
- 2026-11-12 confirm: user approved the pre-push check
- 2026-11-15 correction: "always run validate before you push"
- 2026-11-19 confirm: CI green on first push
