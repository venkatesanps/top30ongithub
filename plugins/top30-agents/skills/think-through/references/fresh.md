# fresh

Your training has a cutoff. The world didn't stop there.

Facts that go stale: library and model versions, API signatures and defaults, prices and
limits, who holds a role, laws and regulations, company products and names, benchmark results,
"the best tool for X", anything with "latest", "current" or a year in it.

1. **List the time-sensitive facts** the answer depends on.
2. **Look each one up** with whatever is available: web search, package registry, the repo's
   lockfile, `--version`, official docs, changelog. Note the source and date.
3. **Tag:** `time-sensitive: ... [checked: source, date]`. If you can't check, say so in the
   answer next to the fact, with the date your knowledge is from.
4. If nothing in the answer is time-sensitive, write `no time-sensitive facts` and move on.

Don't present a remembered version number or price as current without a check or a caveat.
