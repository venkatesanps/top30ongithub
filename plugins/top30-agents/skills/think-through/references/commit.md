# commit

An analysis that ends in "it depends" leaves the work to the user. Pick.

1. **Fast or deep?** If the choice is cheap to reverse, pick the leader and move; say it's
   reversible. If it's expensive to reverse (data model, public API, vendor contract, delete),
   slow down: check the deciding claim first or propose a cheap experiment.
2. **State the choice** in one sentence.
3. **Name the main tradeoff:** what you give up by choosing it.
4. **Would change if:** the specific evidence or condition that would flip the choice.
5. **Next step:** the first concrete action, or the experiment that settles the deciding
   uncertainty (spike, benchmark, prototype, ask the owner).

"Both" or "it depends" is allowed only with the rule that decides: "use X if writes > 1k/s,
else Y".

Ledger: `choice`, `tradeoff`, `would change if`, next step, `carry`.
