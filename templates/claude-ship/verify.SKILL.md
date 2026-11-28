---
name: verify
description: Run the web app and exercise a change end to end. Use before committing.
---

<!-- Goes to .claude/skills/verify/SKILL.md (repo root, or the folder of the code it covers).
     Customize every command. Have Claude run it a few times and fix anything flaky: people
     ignore verification they don't trust. -->

## 1. Start the stack

Run `npm run dev:stack`.

## 2. Wait until it is healthy

Poll `curl -fsS http://localhost:3000/healthz` until it returns 200 (give up after 2 minutes).

## 3. Sign in

Sign in with the seeded test account from `fixtures/users.json`. Never use a real account.

## 4. Exercise the change

Exercise the changed flow in the browser and take a screenshot of the result.

## 5. Report

Report the exact steps you ran and what you saw. Don't report success without them.

## When it fails

| Failure | What to do |
|---|---|
| Port 3000 already in use | Stop the other process (`lsof -i :3000`) or set `PORT`, then start again |
| `/healthz` never returns 200 | Read the stack logs, report the first error; don't edit code to silence it |
| Sign-in fails | Re-seed with `npm run db:seed`, then retry once; report if it still fails |
