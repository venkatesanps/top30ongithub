---
name: steward
description: House rules for looking after PRs in this repository
user-invocable: false
disable-model-invocation: true
---

<!-- Goes to .claude/skills/steward/SKILL.md. The local watch (/ship, /steward) reads it from
     your working directory; PR Steward (the cloud service) reads it from the default branch.
     It cannot loosen the watch's restrictions. Anyone who can merge can edit it, so review
     changes to it as carefully as changes to CI. Replace the examples with your own. -->

- Regenerate the lockfile with `npm install`; don't edit it by hand.
- `e2e-nightly` is flaky. Re-run it once before looking for a cause.
- Run `npm test` and `npm run lint` before pushing a fix.
- Leave comments about API design, scope or naming debates to the author.
- Never change test expectations just to make a check pass; report the failing case instead.
- Never touch CI config, CODEOWNERS, rule files or secrets; escalate if a fix seems to need it.
