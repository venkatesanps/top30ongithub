"""Three Snowflake caches: where each lives, how long it lasts, what it costs to use."""
from figkit import Figure

fig = Figure(
    "Three caches, three lifetimes",
    "Only the warehouse cache costs anything, and it's the one that disappears on suspend.",
    kicker="Snowflake · performance and cost",
    source="guide/snowflake-de-architecture/README.md §5 (Snowflake docs, Nov 2026)",
    height=480,
)
rows = [
    ["Result cache", "cloud services", "finished results", ("24 h; renews on reuse", "teal"),
     ("free", "good")],
    ["Metadata", "cloud services", "row counts, min/max", ("always", "teal"), ("free", "good")],
    ["Warehouse cache", "warehouse disk + RAM", "table data it read", ("dropped on suspend", "bad"),
     ("warehouse running", "bad")],
]
fig.table(40, 140, ["cache", "lives in", "holds", "how long", "cost to use"], rows,
          [150, 180, 170, 200, 180], row_h=44)
fig.heading(40, 352, "what that means")
fig.notes(40, 362, [
    "A repeated dashboard query is free only while the data is unchanged and the SQL text is identical; "
    "each reuse renews the 24 hours, up to 31 days from the first run.",
    "A short auto-suspend saves credits on ETL warehouses but throws away the cache a BI warehouse lives on.",
], 880, tn="muted")
