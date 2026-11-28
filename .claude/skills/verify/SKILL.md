---
name: verify
description: Run this repo's CI checks locally (catalog, generated files, scripts, skill lint, tests) before committing a change to top30ongithub.
---

## 1. Validate the catalog, pins and zips

Run `python3 scripts/kit.py validate`. It must exit 0.

## 2. Check generated files are current

Run `python3 scripts/kit.py render`, then
`git diff --exit-code -- install.sh verify.sh guide/index.html README.md THIRD_PARTY_NOTICES.md`.
Expect no diff; if there is one, the regenerated files belong in the commit.

## 3. Check the scripts parse

Run `bash -n install.sh && bash -n verify.sh && ./install.sh --list >/dev/null && ./install.sh --dry-run row 1 >/dev/null`.
Each must exit 0.

## 4. Lint the plugin skills

Run `python3 scripts/skill_lint.py plugins/ --baseline scripts/skill_lint_baseline.json`.
Expect no new findings.

## 5. Run the tests for what changed

For each area you touched, run its tests, for example `python3 tests/skill_lint/test_skill_lint.py`.
`git diff --name-only origin/main` shows what changed; the full list is in `.github/workflows/ci.yml`.

## 6. Report

List every command you ran and its result, plus `git status --short` so the files to commit are visible. Don't report success without them.

## When it fails

| Failure | What to do |
|---|---|
| Step 2 shows a diff | Commit the regenerated files; never edit them by hand |
| `kit.py validate` names a missing zip or pin | Leave it to the refresh workflow; report it instead of rebuilding |
| A test needs a package (`sqlglot`, `librosa`, `ffmpeg`) | Install it as `ci.yml` does, then run the test again and report the result |
| Skill lint shows a new finding | Fix the skill (numbered steps, checks, failure table); don't add it to the baseline |
