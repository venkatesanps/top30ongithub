# widen

The first idea is usually the obvious one. Get structurally different options before judging any.

Different means a different mechanism, not the same plan with other parameters. "Redis vs
Memcached" is one option; "cache", "precompute", "remove the call" are three.

Operators that reliably produce new branches:

- **Invert:** what if we did the opposite, or made the problem the feature?
- **Subtract:** remove a component, step, or requirement. What still works?
- **Change scale:** 10x users, one user, one day, ten years.
- **Change actor:** user does it, a script does it, a vendor does it, nobody does it.
- **Change time:** do it earlier (build time), later (lazily), or once (cache, snapshot).
- **Change medium:** code to config, UI to CLI, doc to test, meeting to checklist.
- **Borrow:** how does another field solve the same shape of problem?
- **Edit a constraint:** take one "assumed" constraint from frame and drop it.

Write at least three options as `option A:`, `option B:`, `option C:` with one line each on how
it works. Include one option you'd expect to lose; it often shows what the criteria really are.
Don't score here; that's weigh.

Ledger: options, `operators used`, `carry` (the 2-4 options worth weighing).
