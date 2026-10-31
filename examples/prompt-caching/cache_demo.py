#!/usr/bin/env python3
"""Prompt caching, measured: ask several questions about one large document and see what
caching actually saved, from the API's own usage numbers.

    pip install anthropic
    export ANTHROPIC_API_KEY=...
    python3 cache_demo.py data_dictionary.md "Which tables hold positions?" "What is the grain of fact_trades?"
    python3 cache_demo.py doc.md "q1" "q2" --model claude-sonnet-5-5 --read-multiplier 0.05

The document goes in the system prompt with cache_control, so the first call writes it to the
cache and later calls (within the TTL) read it. Cost is shown in "base input token units" so it
doesn't depend on a price table that goes stale: multiply by your model's input price.

  cache write  = 1.25x base input (5-minute TTL) or 2x (--ttl 1h)
  cache read   = 0.1x base input on most models; 0.05x on Opus 5.5 and Sonnet 5.5,
                 0.025x on Fable 5.1 and Mythos 5.1 (pass --read-multiplier)
  below the model's minimum (512 to 4,096 tokens depending on model) nothing is cached

Block-level cache_control is used because it works on the Claude API and on Amazon Bedrock.
"""
import argparse
import os
import sys
from pathlib import Path

import anthropic


def units(u, write_mult, read_mult):
    return (u.input_tokens + write_mult * (u.cache_creation_input_tokens or 0)
            + read_mult * (u.cache_read_input_tokens or 0))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("document", help="text/markdown file to ask about (the part that gets cached)")
    ap.add_argument("questions", nargs="+", help="one or more questions; each is a separate API call")
    ap.add_argument("--model", default="claude-sonnet-5-5")
    ap.add_argument("--ttl", choices=["5m", "1h"], default="5m")
    ap.add_argument("--read-multiplier", type=float, default=0.1,
                    help="cache read price vs base input (0.1 default; 0.05 for Opus/Sonnet 5.5)")
    ap.add_argument("--max-tokens", type=int, default=600)
    a = ap.parse_args()

    doc = Path(a.document).read_text(encoding="utf-8")
    write_mult = 2.0 if a.ttl == "1h" else 1.25
    cc = {"type": "ephemeral"} if a.ttl == "5m" else {"type": "ephemeral", "ttl": "1h"}
    client = anthropic.Anthropic(base_url=os.environ.get("ANTHROPIC_BASE_URL") or None)
    system = [
        {"type": "text", "text": "Answer questions using only the reference document. Say so if it doesn't cover the question."},
        {"type": "text", "text": f"<reference_document>\n{doc}\n</reference_document>", "cache_control": cc},
    ]

    rows, with_cache, without_cache = [], 0.0, 0.0
    for i, q in enumerate(a.questions, 1):
        r = client.messages.create(model=a.model, max_tokens=a.max_tokens, system=system,
                                   messages=[{"role": "user", "content": q}])
        u = r.usage
        total_in = u.input_tokens + (u.cache_creation_input_tokens or 0) + (u.cache_read_input_tokens or 0)
        cost = units(u, write_mult, a.read_multiplier)
        with_cache += cost
        without_cache += total_in
        rows.append((i, total_in, u.cache_creation_input_tokens or 0, u.cache_read_input_tokens or 0, cost))
        text = "".join(b.text for b in r.content if getattr(b, "type", "") == "text").strip()
        print(f"\nQ{i}: {q}\n{text[:600]}")

    print("\n| Call | Input tokens | Written to cache | Read from cache | Cost (base input units) |")
    print("|---|---|---|---|---|")
    for i, t, w, rd, c in rows:
        print(f"| {i} | {t:,} | {w:,} | {rd:,} | {c:,.0f} |")
    if not any(w or rd for _, _, w, rd, _ in rows):
        print("\nNothing was cached: the document is probably below this model's minimum cacheable length.")
        sys.exit(0)
    saved = 1 - with_cache / without_cache if without_cache else 0
    print(f"\nInput cost with caching: {with_cache:,.0f} units; without: {without_cache:,.0f} units "
          f"({saved:.0%} saved over {len(rows)} calls).")
    print("The first call costs more than uncached (cache write premium); savings start from the second call.")


if __name__ == "__main__":
    main()
