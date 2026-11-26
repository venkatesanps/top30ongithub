"""Why re-running COPY INTO is safe, and the two ways to make it unsafe."""
from figkit import Figure

fig = Figure(
    "Re-running COPY INTO loads nothing new",
    "The table keeps 64 days of load metadata, so files it has already loaded are skipped.",
    kicker="Snowflake · ingestion",
    source="guide/snowflake-de-architecture/README.md §2; docs: Loading data (64-day load metadata)",
    height=500,
)
fig.box(40, 150, 150, 64, "Stage", "3 files", "ink", id="stage")
fig.box(290, 150, 190, 64, "COPY INTO", "checks load metadata", "blue", id="copy")
fig.box(560, 150, 150, 64, "Table", "3 files loaded", "ink", id="table")
fig.box(790, 150, 130, 64, "Metadata", "64 days", "teal", id="meta")
fig.connect("stage", "copy", "run 1")
fig.connect("copy", "table", "loads 3")
fig.connect("table", "meta", "records", tn="teal", dashed=True)
fig.decision(385, 300, 230, 76, "loaded before?", tn="blue", id="q")
fig.connect("copy", "q", "run 2", sides=("bottom", "top"))
fig.box(580, 268, 340, 64, "0 files processed", "safe to re-run after a failure", "good", id="skip")
fig.connect("q", "skip", "yes")
fig.heading(40, 384, "two ways to load the same rows twice", "bad")
fig.cards(40, 398, 880, [("FORCE = TRUE", "reloads every file", "bad"),
                         ("CREATE OR REPLACE TABLE", "wipes the metadata", "bad")], h=60)
