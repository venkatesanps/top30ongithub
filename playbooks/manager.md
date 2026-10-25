# Playbook: technology manager

Goal: spend less time assembling status and more time on decisions and people.
Install numbers refer to `./install.sh` (for example `./install.sh 44 45 46`).

## Set up once

| Need | Install | Why |
|---|---|---|
| Ask questions of Jira and Confluence | **45** Jira & Confluence MCP | Works with Data Center via a personal access token. |
| Standups, incident reviews, status reports | **44** Anthropic knowledge-work plugins | `engineering` and `operations` plugins ship these as skills. |
| Delivery metrics (DORA, sprint flow) | **46** Apache DevLake, or **47** Middleware | DevLake reads Jira + Git + Jenkins; Middleware is Git-only and lighter. |
| AI adoption and cost for the team | **48** Claude Code ROI monitoring, **49** ccusage | Team-level trends, with the team's agreement (see the guardrails page). |
| One page leadership can check | **54** Uptime Kuma status page | Shows whether the services your team owns are up, without asking anyone. |

## Weekly rhythm

**Monday — plan the week (20 min).**
"From Jira, list my team's open items for this sprint grouped by person, flag anything blocked
for more than 3 days or with no update in 5 days, and draft three questions for standup."

**Daily — standup in 5 minutes.**
`/engineering:standup` with yesterday's Jira and Git activity. Read the summary before the call;
spend the call on blockers only.

**Wednesday — delivery health (15 min).**
Open DevLake's DORA dashboard. Ask: "Lead time went from X to Y days this month. Which stage grew:
coding, pickup, review or deploy?" Pick one bottleneck to fix with the team, not five.

**After any incident — review the same week.**
`/engineering:incident-response` to draft the timeline from the incident ticket and channel
notes; `/operations:runbook` to turn the fix into a runbook. Track action items as Jira tickets.

**Friday — status report (15 min).**
`/operations:status-report`: shipped, slipped (and why), risks, asks. Edit for tone; send.

**Monthly — capacity and tech debt.**
`/operations:capacity-plan` against next month's committed work, and `/engineering:tech-debt`
on the two services that caused the most incidents.

## 1:1 prep

"Summarize what Priya worked on in the last two weeks from Jira and Confluence: shipped items,
reviews she gave, docs she wrote. Suggest two things to recognise and one growth topic."
Use it as a memory aid, never as the evaluation.

## Metrics worth watching (team level)

- Lead time for changes, deployment frequency, change failure rate, time to restore (DORA).
- Work in progress per person and age of open items.
- Incidents per service, and how many repeat.
- AI usage: active users, cost per merged PR, sessions per week. Adoption, not surveillance.

## Pitfalls

- Dashboards nobody discusses decay. Put one chart on the agenda each week.
- A metric used to rank people stops being honest. Keep them at team level.
- AI drafts of status and reviews are a first pass; you own what goes out.
