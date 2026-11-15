# Confluence versions

Confluence doesn't render the Mermaid diagrams or math blocks in the main [guide](../README.md), so these two files carry the same content with the diagrams as images and the formulas as plain text.

| File | How to use it |
| --- | --- |
| `merchant-services-confluence.html` | Open it in a browser, select all, copy, and paste into a new Confluence page. If the pictures don't come across, upload them from [`../diagrams`](../diagrams). |
| `merchant-services-confluence.wiki.txt` | Upload the eight PNGs in [`../diagrams`](../diagrams) as page attachments first, then insert this file with Confluence's **Markup** option set to *Confluence wiki*. Images link to the attachments by file name, and a table of contents is generated automatically. |

The `.mmd` files in `../diagrams` are the Mermaid sources; re-render them with `mmdc -i file.mmd -o file.png -s 2 -b white`.
