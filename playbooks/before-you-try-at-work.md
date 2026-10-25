# Before you try this at work

Most of these tools send what they read to an AI model, and several can act on real systems.
In a regulated firm, a few minutes on these questions saves a hard conversation later.

## 1. Use the AI platform your firm has approved

- If Claude Code (or the Claude app) isn't approved for work data, don't use it with work data.
  The patterns in these playbooks still apply to whatever assistant your firm provides.
- Plugins, skills and MCP servers are software: check whether your firm needs them reviewed
  before install, the same as any other open-source dependency.
- Prefer installing from the official source each entry links to. The catalog flags known fakes
  (for example, counterfeit "REA.exe" downloads).

## 2. Decide what data the assistant may see

| Safe to start with | Needs approval first | Keep out |
|---|---|---|
| Public docs, your own notes, synthetic or masked samples, schema DDL with no data | Internal code, ticket text, logs, query plans, dev/test databases | Customer or client data, credentials, production data, anything restricted by your data classification policy |

## 3. Connect with the least access that works

- **Databases** (SQLcl, dbt, Snowflake): a read-only role on a dev or masked copy. Never a personal
  production account.
- **Cloud** (AWS MCP servers): a read-only IAM role, in a sandbox account.
- **Jira / Confluence**: a personal access token with your own permissions; run `mcp-atlassian`
  with `--read-only` until writes are agreed.
- **Monitoring** (Grafana, Dynatrace, PagerDuty): Viewer or read-only API tokens. Leave PagerDuty's
  write tools off.
- Store tokens in your OS keychain or an approved secrets tool, not in shell history or repo files.

## 4. Check licences before anything reaches production

| Licence | Entries | What it usually means |
|---|---|---|
| MIT, Apache-2.0 | Most entries | Generally fine; keep the notice. |
| AGPL-3.0 | Grafana, OpenMontage | Running a modified copy as a service has source-sharing obligations; most firms route this via the platform team. |
| Elastic License | Soda Core (mentioned, not listed) | Restrictions on offering it as a service; often needs legal review. |

## 5. Measuring people needs their agreement

The Claude Code ROI stack, ccusage, DevLake and Middleware can show activity per person. Use them
for team-level trends (lead time, adoption, cost), agree with the team what is collected, and
don't use them to rank individuals. DORA's own guidance says the same.

## 6. Watch the cost

Each plugin adds tokens to every session (see the "Tokens/session" column). ECC and Marketing
Skills are by far the heaviest. Start with one or two plugins per person and check `ccusage`
after a week.

## 7. Keep a short log

For each tool you trial: what it touched, which credentials it used, what you learned, and
whether it stays. That log is what a reviewer will ask for, and it's how good tools get approved
for the wider team.
