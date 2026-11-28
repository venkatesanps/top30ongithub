---
name: steward
description: House rules for looking after PRs in top30ongithub
user-invocable: false
disable-model-invocation: true
---

<!-- Read by the local watch (/ship, /steward) from the working directory and by PR Steward
     from the default branch. Changes to this file get the same care as changes to CI. -->

- `catalog.json` is the source of truth. After changing it, run `python3 scripts/kit.py render`
  and commit the regenerated `install.sh`, `verify.sh`, `guide/index.html`, `README.md` and
  `THIRD_PARTY_NOTICES.md` in the same push. Never hand-edit those generated parts.
- If the "Generated files match catalog.json" check fails, the fix is `python3 scripts/kit.py render`,
  not an edit to the generated file.
- Don't touch `CHANGELOG.md`, `sources/` pins, `.gitmodules` or the skill zips in `claude-ai-skills/`:
  the daily refresh workflow writes them. A conflict in `CHANGELOG.md` resolves by taking main's
  version.
- Before pushing a fix, run `python3 scripts/kit.py validate`, `bash -n install.sh verify.sh`,
  `python3 scripts/skill_lint.py plugins/ --baseline scripts/skill_lint_baseline.json` and the
  `tests/<area>/test_*.py` files for anything you touched.
- Never lower a test expectation or add to `scripts/skill_lint_baseline.json` to make a check pass;
  report the failing case to the author.
- Install-test failures for an upstream repo (moved, archived, renamed) are the refresh
  workflow's job. Report them; don't patch install commands by hand.
- Leave wording, fact-check claims and "which tools belong in the kit" to the author.
