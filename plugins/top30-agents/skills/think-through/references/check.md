# check

Re-reading your own reasoning is not verification. Check means evidence from outside your head.

1. **List the claims the answer rests on.** If this claim were false, would the answer change?
   Those are the ones to check. Skip decoration.
2. **Pick the cheapest real check for each:** run the code or test, read the source or docs,
   compute the number, query the data, search for the current fact, look at the actual file.
3. **Tag every claim** in the ledger:
   - `[verified: how]` e.g. `[verified: ran pytest -k auth, 3 pass]`
   - `[unverified: why]` e.g. `[unverified: no access to prod logs]`
   - `[assumed]` when it's a stated working assumption
4. **Downgrade the answer** to match: an unverified claim that carries the answer becomes a
   caveat next to it, or the first next step.

Also check for claims of the form "X is impossible / unsupported / always". Those are cheap to
falsify and expensive when wrong.

Ledger: `claim: ... [tag]` lines, `carry` (what's now solid, what's still open).
