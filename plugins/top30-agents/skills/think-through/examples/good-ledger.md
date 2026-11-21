# Think ledger

prompt: Should we port our Python ingestion service to Rust?
depth: deep

## Orient
goal: decide whether a Rust rewrite is the best way to fix ingestion pain
likely failure if answered fast: answering "Rust is faster, yes" without knowing what hurts
evidence that could change the answer: profiles showing where time goes; team Rust experience
output: recommendation, tradeoff, first step; under 300 words

## [x] frame
- goal: port ingestion to Rust
- real goal: hit the 2-minute p99 freshness SLO, which misses ~3 days a week
- constraints (hard): same Kafka topics and schema; 2 engineers; one quarter
- assumed: "Python is the bottleneck"; "we must rewrite all of it"
- frame change: this is a latency problem in one stage, not a language decision
carry: judge options by p99 freshness gained per engineer-week

## [x] check
- claim: 70% of wall time is JSON parsing + validation [verified: py-spy profile of 3 prod runs, attached]
- claim: Kafka consumer lag is low during misses [verified: Grafana lag panel, last 14 days]
- claim: nobody on the team has shipped Rust to prod [verified: asked in #ingest]
- claim: orjson + msgspec would cut parse time 3-5x [unverified: vendor benchmarks only]
carry: the hot path is parsing; most of the service is not the problem

## [x] weigh
- criteria (weight): p99 gain (critical), engineer-weeks (high), operational risk (high), hiring/upkeep (medium)
- scores: full Rust port - big gain, ~20 eng-weeks, high risk, upkeep cost; swap to orjson+msgspec - likely 3x parse, 1 eng-week, low risk; Rust extension (PyO3) for the parser only - big parse gain, ~4 eng-weeks, medium risk
- critical fails: none fail p99 if the parse estimate holds
carry: parser swap first; PyO3 module if it falls short; full port is dominated

## [x] commit
- choice: don't port; swap the parser to orjson+msgspec this sprint, measure p99 for a week
- tradeoff: we keep Python's per-message overhead; if volume triples we revisit
- would change if: the swap gives < 2x on parse time, or profiles show the cost moving to the GIL
carry: one-week experiment with a clear pass bar

## [x] integrate
- through-line: the pain is one hot stage, so fix the stage, not the language
- tension kept: a PyO3 module is the fallback, and it introduces Rust in a small, reversible way
- uncertainty shown: the 3x parse gain is a vendor number until our benchmark runs
carry: answer leads with "no port; parser swap; here's the pass bar"

## Answer check
- every load-bearing claim tagged [verified]/[unverified]/[assumed]
- what would change my mind: parse speedup under 2x, or a profile showing a different hot spot
