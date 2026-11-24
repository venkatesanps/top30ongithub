# App shapes

| Shape | Example | Needs | Watch for |
|---|---|---|---|
| **Morning brief** | meeting prep from calendar and email | connectors, Claude requests | run once on open, cache the result with a timestamp, a Refresh button |
| **Due-list with reminders** | chargeback reply deadlines, orders to ship today | local or shared state, notifications | ask for notifications from a button; one notification per item per day |
| **Menu bar or tray glance** | open incidents count, today's settlement total | menu bar or tray item | one number or one line in the bar; click opens the window |
| **Quick capture** | log a call note with a global shortcut | global shortcut, stored state | show the shortcut in the UI, let the user change it, never steal common chords |
| **Floating helper** | call script or timer that stays on top | always-on-top window | a visible unpin toggle; small default size |
| **File tool** | rename exports, sort a downloads folder | full computer access | try a file picker and download first; if full access is truly needed, the app stays in your org |
| **Team tracker** | shared sign-up or status board | shared state capability | shared state, not localStorage; show who changed what |

For every shape: an empty state, an error state, an offline state, and a "last updated" time.
