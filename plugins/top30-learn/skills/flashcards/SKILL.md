---
name: flashcards
description: Turn notes, a document, a chapter or a topic into a flashcard deck - basic Q&A and cloze cards - exported as an Anki import file, printable double-sided cards, a self-contained study page with flip and spaced repetition (Leitner boxes), and Markdown. Claude's version of ChatGPT's /flashcards. Use when the user says "/flashcards", "make flashcards", "quiz me", "Anki deck", "study cards", "help me memorize", or is preparing for an exam, certification or onboarding.
---

# Flashcards

You write the cards; `scripts/flashcards.py` checks them against the rules of good cards and
builds four outputs. Standard library only, no network.

## 1. Write cards that teach

Read the source first. Then, per card:

- **One idea.** If the answer has "and", it's probably two cards.
- **Short back** - 30 words or fewer; most should be under 15.
- **Ask, don't hint.** The answer mustn't appear in the question.
- **Use cloze for lists and sequences**: `Stages: retrieval -> {{c1::first chargeback}} ->
  {{c2::representment}}`. Up to two cloze numbers per card.
- **Tag by topic** so people can study one part, and add a `source` (section or page) so every
  card can be checked.
- **Cover the source evenly** - 20-40 cards for a chapter. Facts, terms, causes, and "what
  happens if" cards; not trivia.

```json
{"deck": "Name", "description": "What it covers",
 "cards": [{"front": "Question?", "back": "Answer", "tags": ["topic"], "source": "doc, section"},
           {"type": "cloze", "front": "The {{c1::issuer}} approves the auth.", "tags": ["topic"]}]}
```

CSV works too: columns `front,back,tags,source,type`, tags separated by spaces.

## 2. Lint and build

```bash
F="${CLAUDE_PLUGIN_ROOT}/skills/flashcards/scripts/flashcards.py"
python3 "$F" lint deck.json
python3 "$F" render deck.json -o flashcards/ --formats anki,print,study,md
```

The linter flags long backs, answers leaking into the question, two questions on one card,
duplicates, broken cloze syntax and missing tags. Fix warnings, not just errors.

| File | Use |
|---|---|
| `<name>.html` | Study page: flip with Space, grade with 1/2, cards move through 5 Leitner boxes, filter by tag. Progress stays in that browser. |
| `<name>.anki.txt` | Anki: File > Import. Note type, deck and tags come from the file header. |
| `<name>.print.html` | Print double-sided (flip on long edge), 8 cards per sheet, backs line up. |
| `<name>.md` | Plain list for a README or notes app. |

## 3. Hand it over

Open the study page, give the card count by tag, and offer a quiz in chat: ask 5 random fronts,
wait for each answer, and mark it.
