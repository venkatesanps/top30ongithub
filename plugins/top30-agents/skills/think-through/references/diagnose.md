# diagnose

A symptom has several possible causes. Fixing the first plausible one is how bugs come back.

1. **Expected vs observed,** precisely: input, environment, what happened, since when.
   "Fails since Tuesday" means something changed on Tuesday; list what did.
2. **Two or more competing hypotheses** (`H1:`, `H2:` ...). Include at least one you find less
   likely, plus "the test or measurement is wrong".
3. **For each, what would you see if it were true** that you would not see otherwise.
4. **Discriminating check:** the cheapest observation that separates the leading hypotheses
   (a log line, a bisect, a one-line repro, a config diff). Prefer checks that can kill a
   hypothesis over ones that merely fit it.
5. **Run it** if you can, update, repeat. A fix is confirmed when the failure reproduces before
   and stops after, for the reason you think.

Ledger: `expected vs observed`, `H1`, `H2`, `discriminating check`, result, `carry`.

Don't: patch symptoms and call it root cause; trust a single passing run on a flaky failure.
