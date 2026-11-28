# Review instructions

<!-- Read by Code Review (the managed GitHub service) from the default branch, never from the
     PR under review. Local /code-review does NOT read this file: put the "Always check" rules
     in CLAUDE.md too if you review locally or with /ship.
     Path exclusions and the Nit cap only take effect when the default branch is protected.
     Add a rule only after the same comment shows up on 2+ PRs; delete rules that stop earning
     their place. A person approves the PR that changes this file. -->

## What Important means here

Wrong results, leaked data, or anything that blocks a rollback.
Style and naming are Nit at most.

## Always check

- Database queries are scoped to the caller's tenant.
- New API routes have an integration test.
- SQL that writes (INSERT, MERGE, UPDATE, DELETE, CREATE OR REPLACE) names its target
  database explicitly and never points at a PROD_* database from a dev path.
- No credentials, account identifiers, tokens or personal data in code, tests, fixtures or logs.

## Keep it quiet

- Report at most five Nits.
- Skip generated files and lockfiles.
- Behavior claims need a file and line.
