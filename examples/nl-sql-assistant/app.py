"""Streamlit front end for the NL->SQL assistant.

    pip install streamlit sqlglot anthropic          # + snowflake-connector-python for Snowflake
    export ANTHROPIC_API_KEY=...                       # or pick Bedrock in the sidebar
    streamlit run examples/nl-sql-assistant/app.py
"""
import os
import sys
from pathlib import Path

import streamlit as st

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "sample"))

from nlsql import db, schema  # noqa: E402
from nlsql.assistant import Assistant  # noqa: E402
from nlsql.llm import ClaudeSQL, DEFAULT_MODEL  # noqa: E402

st.set_page_config(page_title="Ask your data", layout="wide")
st.title("Ask your data")
st.caption("Plain English in, read-only SQL out. Every query is parsed and checked before it runs, "
           "on a read-only connection.")

with st.sidebar:
    st.header("Database")
    kind = st.radio("Source", ["SQLite", "Snowflake"], horizontal=True)
    if kind == "SQLite":
        path = st.text_input("SQLite file", str(HERE / "sample" / "shop.db"))
        conn_args = ("sqlite", path)
    else:
        conn_name = st.text_input("Connection (connections.toml)", "")
        role = st.text_input("Read-only role", "")
        database = st.text_input("Database", "")
        sf_schema = st.text_input("Schema", "")
        warehouse = st.text_input("Warehouse (optional)", "")
        conn_args = ("snowflake", conn_name, role, database, sf_schema, warehouse or None)
    st.header("Model")
    provider = st.radio("Provider", ["anthropic", "bedrock"], horizontal=True,
                        help="Bedrock keeps traffic in your AWS account (AWS credentials, Bedrock model id).")
    model = st.text_input("Model", DEFAULT_MODEL if provider == "anthropic" else os.environ.get("NLSQL_BEDROCK_MODEL", ""))
    explain = st.radio("Explanation", ["sample", "facts", "none"],
                       help="sample: facts + up to 20 rows, personal values masked. facts: no rows. none: no second call.")
    max_rows = st.number_input("Max rows", 10, 10000, 1000, step=100)


@st.cache_resource(show_spinner="Reading the schema...")
def connect(args):
    if args[0] == "sqlite":
        p = Path(args[1]).expanduser()
        if not p.exists() and p.name == "shop.db":
            import make_sample
            make_sample.build(p)
        r = db.SQLiteRunner(p)
        return r, schema.describe_sqlite(r)
    _, conn_name, role, database, sf_schema, warehouse = args
    r = db.SnowflakeRunner(connection_name=conn_name or None, role=role, warehouse=warehouse)
    return r, schema.describe_snowflake(r, database, sf_schema)


try:
    runner, sch = connect(conn_args)
except Exception as e:  # show the reason, don't crash the page
    st.error(f"Can't connect: {e}")
    st.stop()

with st.expander(f"Schema sent to the model ({len(sch.tables)} tables, {len(sch.sensitive)} sensitive columns)"):
    st.code(sch.text(), language="sql")
    st.caption("Names and types only. Values from [sensitive] columns are never sent.")


def render(res):
    st.code(res.sql or "-", language="sql")
    if res.intent:
        st.caption(res.intent)
    for w in res.warnings:
        st.warning(w)
    if not res.ok:
        st.error("Refused or failed: " + "; ".join(res.problems))
        return
    st.dataframe([dict(zip(res.columns, r)) for r in res.rows], width="stretch")
    st.info(res.explanation)
    st.caption(f"{res.attempts} attempt(s), {res.seconds:.1f}s")


audit = Path("~/.nl-sql-assistant/audit.jsonl").expanduser()
q = st.text_input("Question", placeholder="Show top 5 products by revenue")
if st.button("Ask", type="primary", disabled=not q):
    try:
        llm = ClaudeSQL(model=model, provider=provider)
    except Exception as e:
        st.error(f"Model not available: {e}")
        st.stop()
    with st.spinner("Writing and checking SQL..."):
        res = Assistant(runner, sch, llm, explain=explain, max_rows=int(max_rows), audit_path=audit).ask(q)
    render(res)

with st.expander("Run your own SQL (no model call)"):
    own = st.text_area("SQL", "SELECT category, COUNT(*) AS products FROM products GROUP BY category")
    if st.button("Check and run"):
        render(Assistant(runner, sch, llm=None, max_rows=int(max_rows), audit_path=audit).run_sql(own))
