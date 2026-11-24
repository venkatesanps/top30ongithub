---
name: artifact-app
description: Build a Claude artifact meant to be installed as a Mac or Windows desktop app ("Install as app"). Plans the job and the lowest permission tier it needs (default, app permissions for notifications, menu bar or tray, global shortcuts and always-on-top windows, or full computer access), estimates how many Claude requests a refresh schedule spends, and lints the page for what breaks or gets risky once it lives in its own window - short app name, dark mode, pinned CDN versions, no remote parts that can change without a new permission prompt, guarded runtime calls, storage in try/catch, escaped connector and Claude output, offline state, no secrets. Use for "make this an app", "install as app", "desktop app from an artifact", "menu bar app", "tray app", "app that reminds me", "/artifact-app". Not for Claude Docs, Slides or Sheets, which can't be installed.
---

# artifact-app

An artifact you open every day can be installed as an app: its own icon, its own window, your
connectors and Claude, and (if the user allows) notifications, a menu bar or tray item, global
shortcuts and always-on-top windows. That changes what "done" means. A page that was fine in a
chat pane now has to look right in a resized window, survive a denied permission, keep working
when storage is blocked, not burn plan usage on a timer, and not pull in code from another site
that can change after the user granted access.

Built from Anthropic's announcement of Install as app (2026-11-24). Original text and code.

Script: `python3 ${CLAUDE_PLUGIN_ROOT}/skills/artifact-app/scripts/appkit.py` (standard library).

## 1. Plan the app

Write three lines: **the moment** the user opens it (morning triage, before a call, when a reply
is due), **the one view** that answers that moment, and **what it watches** (connector data,
local entries, a schedule). Then:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/artifact-app/scripts/appkit.py plan "menu bar app that reminds me when chargeback replies are due"
```

It names the capabilities the description implies and the lowest permission tier that covers
them. Tiers and what each allows: [references/permissions.md](references/permissions.md). Aim for
the lowest one. Full computer access can only be granted to apps the user (or, on Team and
Enterprise, their org) made, so an app that needs it can't be shared outside the org. A file
picker or drag-and-drop often removes the need.

Common shapes and what each needs: [references/patterns.md](references/patterns.md).

Check: the tier it prints should match what the user agreed to grant. If it says `full-access`,
confirm the user made the app (or is in the org that did) before you build it that way.

## 2. Build it as an artifact

Build it the normal way: in Claude, start with the Artifact quickstart and the `artifact-design`
skill. Load `artifact-capabilities` before writing any runtime call (connectors, Claude requests,
notifications, menu bar, shortcuts, stored state); it has this account's live roster and exact
call shapes. Don't guess API names. Build so it works in three places: the chat preview, a
browser, and the installed window.

- Feature-detect every capability and show a fallback when it is missing or denied.
- Ask for a permission from a user action that explains it ("Turn on reminders"), not at launch.
- Treat connector data and Claude output as untrusted text: `textContent`, not `innerHTML`.
- Refresh on window focus or every 5-15 minutes, not every few seconds.
- Show when data was fetched and an offline state; installed apps must be online and signed in.
- Keep state that must persist or be shared in a runtime capability, not `localStorage`.

Check: open the published artifact in the chat preview with every permission denied. It should
still show its main view and say which feature is off and why.

## 3. Check the budget

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/artifact-app/scripts/appkit.py budget --every-min 15 --claude-calls 1 --hours 10
```

Requests the app sends to Claude count toward the user's plan limits. Over ~50 a day per person,
switch to refresh-on-focus or a button.

## 4. Lint it

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/artifact-app/scripts/appkit.py lint app.html
```

Errors exit 1. Full list: [references/lint-rules.md](references/lint-rules.md).

| Rule | Severity | Finds |
|---|---|---|
| A01 | error / warning | no title, or a title that isn't a 2-4 word app name |
| A02-A05 | warning | no viewport, no :root color tokens, no dark mode, no body background |
| A06 / A07 | error | script from a non-allowed host / unpinned version |
| A08 | error | external stylesheet other than Google Fonts |
| A09 | warning | storage outside try/catch |
| A10 / A11 | warning | runtime call with no guard / notification with no permission check |
| A12 | error | eval, new Function, document.write |
| A13 | warning | innerHTML built from interpolated data |
| A14 | warning | sub-minute polling in an app that makes requests |
| A15 / A15b | warning / info | requests with no error handling / no offline state |
| A16 | warning | iframe from another site |
| A17 | error | literal secret |
| A18 | error / warning | over 16 MB / heavy data URIs |
| A19 / A20 | info | fixed wide layout / no script at all |

Then run the read-only `app-permission-reviewer` agent on the page and fix what it confirms.

## 5. Publish, then install

Run the linter once more in strict mode; it should exit 0:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/artifact-app/scripts/appkit.py lint app.html --strict
```

Publish the artifact, open it, and use **Share → Install as app** in Claude for Mac or Windows.
There's nothing to package or sign. Check that the installed window opens with the right name and
icon, and that each permission prompt appears only after the action that needs it. Edits to the artifact flow to the installed app, and each new
version asks for its permissions again, so tell the user that before you edit an installed app.
Use the checklist in [references/checklist.md](references/checklist.md) before you say it's ready.

Example: [examples/chargeback-clock.html](examples/chargeback-clock.html), a dispute-deadline
tracker (fictional data) that lints clean, stores data on the device, and sends one reminder per
case per day only after the user turns reminders on. [examples/bad-app.html](examples/bad-app.html)
trips most rules.

## When it fails

| Failure | Fix |
|---|---|
| No "Install as app" in the Share menu | Update Claude for Mac or Windows; on Enterprise an owner must turn it on; Docs, Slides, Sheets and legacy artifacts can't be installed. |
| App won't open | It needs to be online and signed in to Claude. |
| A library is missing in the installed app | The script host isn't allowed or the URL isn't pinned (A06/A07); inline it or pin an exact version. |
| Permission prompt on every update | Expected: grants cover one version. Batch edits and warn users. |
| Notifications never arrive | Permission denied or never asked from a click (A11); check the app's permissions and the OS notification settings. |
| Usage limits hit early | A timer is calling Claude too often (A14); run `budget` and refresh on focus instead. |
| Data gone after restart | Storage blocked or in try/catch fallback (A09); move state that must persist to a runtime capability. |

## Don'ts

- Don't ask for full access to do something a file picker can do.
- Don't load code from a URL you don't control or haven't pinned.
- Don't put API keys in the page; the app uses the user's Claude account and connectors.
- Don't notify on every refresh; one event, one notification.
- Don't claim an app works installed until someone has installed it; the linter checks the page, not the app.
