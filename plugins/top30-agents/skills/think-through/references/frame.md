# frame

Find the problem worth solving before solving the one you were handed.

1. **Stated vs real goal.** Write what was asked, then ask "so that what?" until you hit
   something the user would recognise as the point. "Port to Rust" may really be "cut p99
   latency" or "stop the memory leaks".
2. **Unit and boundary.** What is being changed: a function, a service, a team habit? What is
   explicitly out of scope?
3. **Hard vs assumed constraints.** Hard: deadline, budget, law, API contract. Assumed: "we have
   to keep the schema", "users won't read docs". Mark each. Assumed ones are where better
   options hide.
4. **Proxy check.** If success is measured by a number (tests pass, stars, latency), say what
   the number misses.
5. **Try one other frame.** Restate the problem from another angle: the user's customer, the
   on-call engineer, a year from now, the opposite goal. Keep it if it explains more.

Ledger: `goal`, `real goal`, `constraints (hard)`, `assumed`, `frame change`, `carry`.

Stop when the real goal is one sentence the user would sign. If you can't get there and a
wrong guess is costly, ask one question.
