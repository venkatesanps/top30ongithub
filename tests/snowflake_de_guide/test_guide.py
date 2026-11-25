"""Checks the Snowflake DE architecture study guide: the flashcard deck lints clean and its
rendered files are up to date, the lab stays cheap and cleans up after itself, and the README's
local links resolve.

python3 tests/snowflake_de_guide/test_guide.py   (no dependencies, no network, no Snowflake)
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
G = ROOT / "guide/snowflake-de-architecture"
FC = ROOT / "plugins/top30-learn/skills/flashcards/scripts/flashcards.py"


def statements(sql):
    """SQL statements with -- comments removed (the lab has no ; inside strings)."""
    code = "\n".join(line.split("--", 1)[0] for line in sql.splitlines())
    return [s.strip() for s in code.split(";") if s.strip()]


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    # flashcards: lint clean, rendered files match the deck
    r = subprocess.run([sys.executable, str(FC), "lint", str(G / "deck.json")], capture_output=True, text=True)
    check(r.returncode == 0 and "0 errors, 0 warnings" in r.stdout, f"deck lints clean: {r.stdout}{r.stderr}")
    with tempfile.TemporaryDirectory() as td:
        subprocess.run([sys.executable, str(FC), "render", str(G / "deck.json"), "-o", td,
                        "--formats", "anki,print,study,md"], capture_output=True, text=True, check=True)
        for f in sorted(Path(td).iterdir()):
            have = G / "flashcards" / f.name
            check(have.exists() and have.read_bytes() == f.read_bytes(),
                  f"flashcards/{f.name} is stale: re-run flashcards.py render deck.json -o flashcards")

    # lab: cheap, Gen1, nothing left running, everything dropped
    sql = (G / "lab.sql").read_text()
    st = statements(sql)
    up = [s.upper() for s in st]
    wh = next((s for s in up if s.startswith("CREATE WAREHOUSE")), "")
    check("WAREHOUSE_SIZE = XSMALL" in wh and "AUTO_SUSPEND = 60" in wh and "STANDARD_GEN_1" in wh
          and "INITIALLY_SUSPENDED = TRUE" in wh, f"lab warehouse is X-Small, Gen1, 60 s auto-suspend: {wh}")
    created = re.findall(r"CREATE (?:OR REPLACE )?(?:TRANSIENT |SECURE |DYNAMIC |MASKING |ROW ACCESS )?"
                         r"(?:TABLE|VIEW|STREAM|TASK|STAGE|FILE FORMAT|POLICY|WAREHOUSE|DATABASE|SCHEMA)"
                         r"(?: IF NOT EXISTS)? ([A-Z0-9_.]+)", "\n".join(up))
    check(created, "found CREATE statements")
    for name in created:
        last = name.split(".")[-1]
        check(last.startswith("LAB_") or name.startswith("LAB_DE."), f"object {name} isn't namespaced LAB_*")
    check(up[-3:-1] == ["DROP DATABASE IF EXISTS LAB_DE", "DROP WAREHOUSE IF EXISTS LAB_WH"],
          f"lab ends by dropping LAB_DE and LAB_WH: {up[-3:]}")
    check(not any(re.search(r"ALTER TASK .* RESUME", s) for s in up), "the task is never resumed")
    check(any(s.startswith("EXECUTE TASK") for s in up), "the task is run once by hand")
    check(any(re.search(r"ALTER DYNAMIC TABLE \S+ SUSPEND", s) for s in up), "the dynamic table is suspended")
    check(not any("ACCOUNTADMIN" in s and s.startswith("USE ROLE") for s in up), "no USE ROLE ACCOUNTADMIN outside comments")
    check(not any(s.startswith(("CREATE SHARE", "CREATE RESOURCE MONITOR", "CREATE ACCOUNT")) for s in up),
          "account-level objects stay commented out")
    check("USE_CACHED_RESULT = FALSE" in sql and "ALTER SESSION UNSET USE_CACHED_RESULT" in sql, "result cache is turned back on")
    check(sql.count("-- expect") >= 20, "each step says what to expect")

    # README: local links resolve, corrections table and self-check present
    readme = (G / "README.md").read_text()
    for target in re.findall(r"\]\(([^)#:]+)(?:#[^)]*)?\)", readme):
        check((G / target).exists(), f"README link {target} resolves")
    check("## What the infographic gets wrong or leaves out" in readme, "corrections section")
    check(readme.count("<details>") == 10, "ten self-check scenarios")
    check("STANDARD_GEN_1" in readme and "Gen1" in readme, "Gen1 is the stated assumption")

    if fails:
        print(f"FAIL ({len(fails)})")
        for f in fails:
            print(" -", f)
        return 1
    print("ok - snowflake DE guide: deck lint + render, lab safety, README links")
    return 0


if __name__ == "__main__":
    sys.exit(main())
