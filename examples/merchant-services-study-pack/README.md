# Merchant services study pack

Sample output from the [`top30-learn`](../../plugins/top30-learn) plugin: one subject, card
acquiring (payment processing for merchants), taught four ways.

> **Unofficial.** Built from the public-source [merchant-services-guide](../../merchant-services-guide/README.md)
> in this repo. Not produced, reviewed or endorsed by JPMorgan Chase or any acquirer. No real
> pricing, logos or customer data. The comic's people and tea shop are fictional.

Open [`index.html`](index.html) for everything on one page.

| Command | What it made | Files |
|---|---|---|
| `/mindmap` | *How a card payment works*: 7 branches, 48 nodes, from the five parties to reporting | [svg](mindmap/payment-lifecycle.svg) · [html](mindmap/payment-lifecycle.html) · [mermaid](mindmap/payment-lifecycle.mmd) · [opml](mindmap/payment-lifecycle.opml) |
| `/sketchnotes` | *Life of a $100 online order*: 9 numbered steps from checkout to representment | [svg](sketchnote/life-of-a-100-order.svg) |
| `/flashcards` | *Merchant services basics*: 30 cards (26 Q&A, 4 cloze) tagged by topic, with sources | [study page](flashcards/merchant-services.html) · [Anki](flashcards/merchant-services.anki.txt) · [print](flashcards/merchant-services.print.html) · [markdown](flashcards/merchant-services.md) |
| `/educationalcomics` | *The case of the disputed $100 order*: 2 pages, 8 panels, a sale then a chargeback won on evidence | [page 1](comic/disputed-order-page1.svg) · [page 2](comic/disputed-order-page2.svg) · [reader](comic/disputed-order.html) · [image prompts](comic/disputed-order.prompts.md) |

The inputs are in [`specs/`](specs). Rebuild everything from the repo root:

```bash
L=plugins/top30-learn/skills; P=examples/merchant-services-study-pack
python3 $L/mindmap/scripts/mindmap.py render $P/specs/payment-lifecycle.mindmap.md -o $P/mindmap
python3 $L/sketchnotes/scripts/sketchnotes.py render $P/specs/life-of-a-100-order.sketchnote.json -o $P/sketchnote/life-of-a-100-order.svg
python3 $L/flashcards/scripts/flashcards.py render $P/specs/merchant-services.flashcards.json -o $P/flashcards
python3 $L/educational-comics/scripts/edu_comics.py render $P/specs/disputed-order.comic.json -o $P/comic
```

## How the four fit together

- The **mind map** is the whole subject at a glance; start here.
- The **sketchnote** follows one sale through time, so the map's branches become a sequence.
- The **flashcards** hold the terms and facts; study them after the first two.
- The **comic** walks through the hardest part, disputes, as a story you'll remember.

## Using it for onboarding

Ask Claude with the plugin installed: *"Use study-pack-builder on merchant-services-guide/README.md,
focus on Layer 3 settlement"* for a deeper pack on one layer, then *"study-pack-reviewer on
examples/merchant-services-study-pack"* to check every claim against the guide before sharing.
