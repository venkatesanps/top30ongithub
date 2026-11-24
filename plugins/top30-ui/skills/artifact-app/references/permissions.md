# Permission tiers for installed apps

Paraphrased from Anthropic's Install as app announcement (2026-11-24). Check the current help
article before relying on details; this is a beta.

| Tier | What the app can do | Who can grant it |
|---|---|---|
| **Default** | What a web page can do in a browser. Connectors and Claude requests through the artifact runtime. | Anyone who installs it. |
| **App permissions** | Features Claude can tightly control: notifications, a menu bar (Mac) or system tray (Windows) item, global keyboard shortcuts, always-on-top windows. | The user, per app. Team and Enterprise admins can switch app permissions off for the org. |
| **Full computer access** | Run programs and read, change or delete files without asking each time. | Only for apps the user made, or on Team and Enterprise, apps made by people in the org. Admins can switch it off; it's off by default on Team. |

Things that follow from this:

- **Permissions are per version.** Every edit, including the author's own, makes Claude ask again.
  Batch edits to an installed app and tell users a prompt is coming.
- **Remote parts aren't covered.** If part of the app loads from another website, that part can
  change without a new prompt. Inline code or pin exact CDN versions; avoid iframes.
- **No review.** Anthropic doesn't review apps before install. Only grant full access to apps you
  trust, and read what a shared app does first (the `app-permission-reviewer` agent helps).
- **Usage.** Requests the app sends to Claude count toward the user's plan limits.
- **Availability.** Beta on Claude for Mac and Windows, all plans; off until an owner turns it on
  for Enterprise; not available to HIPAA-ready organizations or hybrid deployments. Requires being
  online and signed in. Claude Docs, Slides and Sheets can't be installed.
