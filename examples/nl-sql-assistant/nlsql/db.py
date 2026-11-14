"""Read-only database runners (lock 2 of 3). Each one refuses writes even if the guard is bypassed.

SQLiteRunner     opens the file read-only (mode=ro), sets PRAGMA query_only, and installs an
                 authorizer that denies everything except reading. Long queries are cut off.
SnowflakeRunner  runs under a named role (never an admin role), with a statement timeout and a
                 query tag. Lock 3 is yours: give that role USAGE + SELECT only (see README).
"""
import re
import sqlite3
import time
from pathlib import Path


class ReadOnlyError(Exception):
    """The database refused, or would have refused, a non-read operation."""


class QueryError(Exception):
    """The query is a read but failed (bad column, syntax the engine rejects, timeout)."""


_DENY_FUNCS = {"load_extension", "writefile", "readfile", "edit", "fts3_tokenizer"}


def _authorizer(action, arg1, arg2, dbname, source):
    allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, getattr(sqlite3, "SQLITE_RECURSIVE", 33)}
    if action in allowed:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_PRAGMA and (arg1 or "").lower() in ("table_info", "table_xinfo"):
        return sqlite3.SQLITE_OK  # schema introspection only; query_only stays on
    if action == sqlite3.SQLITE_FUNCTION:
        return sqlite3.SQLITE_DENY if (arg2 or "").lower() in _DENY_FUNCS else sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


class SQLiteRunner:
    dialect = "sqlite"

    def __init__(self, path, timeout=30):
        p = Path(path).expanduser().resolve()
        if not p.is_file():
            raise FileNotFoundError(p)
        self.path, self.timeout = p, timeout
        self.conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True, check_same_thread=False)
        self.conn.execute("PRAGMA query_only = ON")
        self.conn.set_authorizer(_authorizer)

    def _raw(self, sql, params=()):
        cur = self.conn.execute(sql, params)
        return [d[0] for d in cur.description or []], cur.fetchall()

    def run(self, sql, max_rows=1000):
        deadline = time.monotonic() + self.timeout
        self.conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10000)
        try:
            cur = self.conn.execute(sql)
            cols = [d[0] for d in cur.description or []]
            return cols, cur.fetchmany(max_rows)
        except sqlite3.DatabaseError as e:
            msg = str(e)
            if "not authorized" in msg or "readonly" in msg or "read-only" in msg or "query_only" in msg:
                raise ReadOnlyError(msg) from None
            if "interrupted" in msg:
                raise QueryError(f"stopped after {self.timeout}s") from None
            raise QueryError(msg) from None
        except sqlite3.Warning as e:  # e.g. "You can only execute one statement at a time."
            raise ReadOnlyError(str(e)) from None
        finally:
            self.conn.set_progress_handler(None, 0)


ADMIN_ROLES = {"ACCOUNTADMIN", "SYSADMIN", "SECURITYADMIN", "ORGADMIN", "USERADMIN"}
_IDENT = re.compile(r'^[A-Za-z_][A-Za-z0-9_$]*$|^"[^"]+"$')


class SnowflakeRunner:
    dialect = "snowflake"

    def __init__(self, conn=None, connection_name=None, role="", timeout=60, warehouse=None, tag="nl-sql-assistant"):
        role = (role or "").strip()
        if not role:
            raise ReadOnlyError("name a read-only role (--role): the assistant won't run under your default role")
        if role.strip('"').upper() in ADMIN_ROLES:
            raise ReadOnlyError(f"refusing to run under {role}: use a role with USAGE + SELECT only")
        for v in (role, warehouse):
            if v and not _IDENT.match(v):
                raise ReadOnlyError(f"not a valid identifier: {v}")
        if conn is None:
            import snowflake.connector  # pip install snowflake-connector-python
            conn = snowflake.connector.connect(connection_name=connection_name) if connection_name else snowflake.connector.connect()
        self.conn, self.role = conn, role
        self._raw_exec(f"USE ROLE {role}")
        if warehouse:
            self._raw_exec(f"USE WAREHOUSE {warehouse}")
        self._raw_exec(f"ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = {int(timeout)}")
        self._raw_exec(f"ALTER SESSION SET QUERY_TAG = '{tag}'")

    def _raw_exec(self, sql):
        cur = self.conn.cursor()
        try:
            cur.execute(sql)
        finally:
            cur.close()

    def _raw(self, sql, params=None, max_rows=100000):
        cur = self.conn.cursor()
        try:
            cur.execute(sql, params) if params else cur.execute(sql)
            return [d[0] for d in cur.description or []], cur.fetchmany(max_rows)
        finally:
            cur.close()

    def run(self, sql, max_rows=1000):
        try:
            return self._raw(sql, max_rows=max_rows)
        except Exception as e:  # snowflake.connector.errors.ProgrammingError and friends
            msg = str(e)
            if "Insufficient privileges" in msg or "not authorized" in msg.lower():
                raise ReadOnlyError(msg) from None
            raise QueryError(msg.splitlines()[0][:500]) from None
