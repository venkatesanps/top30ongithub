# Confluence versions

Confluence doesn't render the Mermaid diagrams or math blocks in the main [guide](../README.md), so these two files carry the same content with the diagrams as images and the formulas as plain text.

| File | How to use it |
| --- | --- |
| `merchant-services-confluence.html` | Open it in a browser, select all, copy, and paste into a new Confluence page. If the pictures don't come across, upload them from [`../diagrams`](../diagrams). |
| `merchant-services-confluence.wiki.txt` | Upload the 13 PNGs in [`../diagrams`](../diagrams) as page attachments first, then insert this file with Confluence's **Markup** option set to *Confluence wiki*. Images link to the attachments by file name, and a table of contents is generated automatically. |

The `.mmd` files in `../diagrams` are the Mermaid sources.

## Rebuilding after an edit

Edit `../README.md`, then run `python3 build.py` from this folder (needs `pandoc` and the Mermaid CLI, `mmdc`). It re-renders every diagram and regenerates both files here. If you add or remove a Mermaid block in the README, update the `NAMES` list at the top of `build.py` to match.

The interactive hierarchy page, [`../merchant-hierarchy-interactive.html`](../merchant-hierarchy-interactive.html), isn't part of the Confluence build; attach it to the page as a file if readers should have it.
