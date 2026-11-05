"""Runs ora2sf.py on invented Oracle samples and checks what it translates and what it flags.

python3 tests/ora2sf/test_ora2sf.py   (needs sqlglot; no network, no database)
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SCRIPT = ROOT / "plugins/top30-data/skills/oracle-to-snowflake/scripts/ora2sf.py"
SAMPLES = HERE / "samples"


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True, timeout=120)


def main():
    failures = []

    def check(cond, msg):
        print(("PASS " if cond else "FAIL ") + msg)
        if not cond:
            failures.append(msg)

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out"
        r = run(SAMPLES, "--out", out)
        check(r.returncode == 0, f"runs on a folder ({r.stderr.strip()[:200]})")
        fs = json.loads((out / "findings.json").read_text())
        rules = {f["rule"] for f in fs}
        sql = (out / "converted" / "daily_load.sql").read_text()
        pkg = (out / "converted" / "pkg_positions.sql").read_text()
        rep = (out / "report.md").read_text()

        def at(rule):
            return sorted({f["line"] for f in fs if f["rule"] == rule and f["file"].endswith("daily_load.sql")})

        # Translation
        check("COALESCE(p.market_value, 0)" in sql, "NVL becomes COALESCE")
        check("EXCEPT" in sql and "MINUS" not in sql.split("*/")[-1], "MINUS becomes EXCEPT")
        check("VARCHAR(30)" in sql and "PARTITION BY RANGE" not in sql, "CREATE TABLE translates once storage clauses are dropped")
        check("parse-failed" not in rules, "every plain SQL statement in the sample parses")
        check("parallel" not in sql.lower(), "optimizer hint removed")
        check("PACKAGE BODY pkg_positions" in pkg and pkg.count("/*") >= 1, "PL/SQL kept as a comment, not mistranslated")

        # Silent-difference rules that a translator alone would miss
        for rule, line in [("rownum", 14), ("outer-join-plus", 12), ("date-integer-math", 13), ("sysdate-timezone", 13),
                           ("order-siblings", 16), ("empty-string-null", 20), ("db-link", 22), ("number-no-scale", 5),
                           ("date-has-time", 6), ("partitioning", 7), ("hint", 9)]:
            check(line in at(rule), f"{rule} flagged at line {line} (got {at(rule)})")
        for rule in ["plsql-rewrite", "autonomous-txn", "type-anchor", "row-by-row", "oracle-package-call",
                     "dbms-output", "named-exception", "raise-app-error", "package", "number-no-scale"]:
            check(any(f["rule"] == rule and f["file"].endswith(".pkb") for f in fs), f"package body: {rule} flagged")

        # No false alarms
        check(not any(f["rule"] == "oracle-package-call" and "OUTPUT" in f["match"].upper() for f in fs),
              "DBMS_OUTPUT is a note, not an error")
        check(not any(f["rule"] == "currval" for f in fs), "NEXTVAL alone is not flagged as CURRVAL")
        check(not any(f["rule"] == "db-link" and f["line"] != 22 for f in fs), "no db-link false positives")

        # Report and exit codes
        check("| pkg_positions.pkb | 0 | 0 | 1 |" in rep, "report counts the PL/SQL block")
        check(rep.index("| error |") < rep.index("| warn |") < rep.index("| info |"), "report orders rules by severity")
        r = run(SAMPLES / "daily_load.sql", "--out", Path(tmp) / "strict", "--fail-on", "error")
        check(r.returncode == 1, "--fail-on error exits 1 when there are errors")

        clean = Path(tmp) / "clean.sql"
        clean.write_text("SELECT a, NVL(b, 0) AS b FROM t WHERE c = 'x';\n")
        r = run(clean, "--out", Path(tmp) / "c", "--fail-on", "warn")
        check(r.returncode == 0, "clean SQL passes --fail-on warn")
        r = run(Path(tmp) / "missing.sql", "--out", Path(tmp) / "m")
        check(r.returncode != 0 and "not found" in r.stderr, "clear error for a missing path")

    print(f"\n{'FAILED' if failures else 'OK'}: {len(failures)} failure(s)")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
