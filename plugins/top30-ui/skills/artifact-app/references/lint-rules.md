# Lint rules

| Rule | Why it matters once installed | Fix |
|---|---|---|
| A01 title | The title becomes the app's name in the Dock, Start menu and window bar. | 2-4 words, no subtitle. |
| A02 viewport | Windows get resized narrow. | `width=device-width,initial-scale=1` |
| A03 tokens | One place to change colors for both themes. | `--bg`, `--ink`, `--accent` on `:root` |
| A04 dark mode | The app follows the OS theme; a white window at night stands out. | tokens under `prefers-color-scheme: dark`, plus `data-theme` overrides |
| A05 background | There is no page behind the window. | `body{background:var(--bg)}` |
| A06 script host | Only a few CDNs are allowed; anything else won't load or is a remote part that can change. | cdnjs, jsdelivr, unpkg, tailwind, jquery; or inline |
| A07 pinned | `chart.js` with no version can change under an installed app with no new prompt. | `chart.js@4.4.1` |
| A08 stylesheet | Same as A06 for CSS. | inline; Google Fonts only |
| A09 storage | Storage can be empty or throw (private mode, blocked site data). | try/catch every read and write; render without it |
| A10 runtime guard | A capability can be missing (browser preview) or denied. | `window.claude?.x`, `if (window.claude)`, fallback UI |
| A11 notification permission | Notifying without permission fails silently or nags. | check `Notification.permission`, ask from a click |
| A12 dynamic code | Turns any untrusted string into code. | remove |
| A13 innerHTML | Connector data and Claude output can contain markup. | `textContent` or an escape helper |
| A14 fast polling | Each Claude request counts toward plan limits. | refresh on focus or every 5-15 min |
| A15 errors / offline | Installed apps need to be online and signed in. | catch, show retry and offline states |
| A16 iframe | Content from another site changes without a new prompt. | drop it or link out |
| A17 secret | The page is shared and stored; the app doesn't need keys. | remove; use connectors |
| A18 size | 16 MB page limit. | asset store instead of base64 |
| A19 fixed width | Narrow windows scroll sideways. | `max-width`, flex/grid |
| A20 no script | A static page installs fine but never updates or reminds. | fine if that's the intent |

The linter reads one HTML file with regular expressions. It can miss code built at runtime and
can't see what a capability actually does; read the page too.
