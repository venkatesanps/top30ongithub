"""Builds synthetic Claude Code transcripts and checks session_doctor.py finds each signal,
maps it to the right layer, and stays quiet on a healthy session.

python3 tests/session_doctor/test_session_doctor.py   (no dependencies, no network)
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SCRIPT = ROOT / "plugins/top30-agents/skills/session-doctor/scripts/session_doctor.py"


class T:
    """Writes transcript rows in the same shape Claude Code uses."""

    def __init__(self, cwd):
        self.rows, self.n, self.cwd, self.sec = [], 0, str(cwd), 0

    def ts(self, step=5):
        self.sec += step
        return f"2026-11-19T10:{self.sec // 60 % 60:02d}:{self.sec % 60:02d}.000Z"

    def base(self, typ, step=5, **kw):
        return {"type": typ, "uuid": f"u{len(self.rows)}", "timestamp": self.ts(step), "cwd": self.cwd,
                "sessionId": "s1", "isSidechain": False, **kw}

    def user(self, text):
        self.rows.append(self.base("user", message={"role": "user", "content": text}))

    def say(self, text, tokens=20_000):
        self.rows.append(self.base("assistant", message={
            "role": "assistant", "model": "claude-opus-5-5", "content": [{"type": "text", "text": text}],
            "usage": {"input_tokens": 10, "cache_read_input_tokens": tokens, "output_tokens": 50}}))

    def tool(self, name, inp, result="ok", error=False, took=5, reject=False, interrupted=False, sidechain=False):
        self.n += 1
        tid = f"toolu_{self.n}"
        a = self.base("assistant", message={
            "role": "assistant", "model": "claude-opus-5-5",
            "content": [{"type": "tool_use", "id": tid, "name": name, "input": inp}],
            "usage": {"input_tokens": 5, "cache_read_input_tokens": 30_000, "output_tokens": 40}})
        a["isSidechain"] = sidechain
        self.rows.append(a)
        u = self.base("user", step=took, message={"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": tid, "content": result, "is_error": error}]},
            toolUseResult={"stdout": result, "interrupted": interrupted},
            permissionDecision={"decision": "reject" if reject else "accept", "source": "config"})
        u["isSidechain"] = sidechain
        self.rows.append(u)

    def compact(self, pre=180_000, trigger="auto"):
        self.rows.append(self.base("system", subtype="compact_boundary", content="Conversation compacted",
                                   compactMetadata={"trigger": trigger, "preTokens": pre}))

    def title(self, t):
        self.rows.append({"type": "custom-title", "customTitle": t, "sessionId": "s1"})

    def write(self, path):
        with open(path, "w") as fh:
            for r in self.rows:
                fh.write(json.dumps(r) + "\n")
            fh.write("not json\n")  # a torn line must not crash it
        return path


def main():
    failures = []

    def check(cond, msg):
        print(("PASS " if cond else "FAIL ") + msg)
        if not cond:
            failures.append(msg)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        projects = tmp / "projects"
        repo = tmp / "repo"
        (repo / ".git").mkdir(parents=True)
        env = {k: v for k, v in os.environ.items() if not k.startswith("SESSION_DOCTOR")}
        env["SESSION_DOCTOR_PROJECTS"] = str(projects)

        def run(*args):
            r = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env=env)
            return r

        def diag(path, *extra):
            r = run("diagnose", str(path), "--json", *extra)
            return r.returncode, json.loads(r.stdout)

        def signals(rep):
            return {f["signal"]: f for f in rep["findings"]}

        # 1. healthy session: CLAUDE.md present, edit then test, nothing else wrong
        (repo / "CLAUDE.md").write_text("# repo\n")
        t = T(repo)
        t.title("Fix the parser")
        t.user("Fix the off-by-one in parser.py; tests in tests/test_parser.py must pass")
        t.tool("Read", {"file_path": f"{repo}/parser.py"})
        t.tool("Edit", {"file_path": f"{repo}/parser.py", "old_string": "a", "new_string": "b"})
        t.tool("Bash", {"command": "python -m pytest tests/test_parser.py"})
        t.say("Fixed: tests pass.")
        code, rep = diag(t.write(tmp / "healthy.jsonl"))
        check(code == 0 and rep["verdict"] == "healthy" and rep["findings"] == [], "healthy session has no findings")
        check(rep["stats"]["title"] == "Fix the parser" and rep["stats"]["tool_calls"] == 3, "stats read the title and calls")

        # 2. loop: same failing call three times, then 'done' without a test
        t = T(repo)
        t.user("Make the build work")
        for _ in range(3):
            t.tool("Bash", {"command": "npm run buidl"}, result="Exit code 1\nnpm ERR! missing script: buidl", error=True)
        for i in range(6):
            t.tool("Edit", {"file_path": f"{repo}/src/app.ts", "old_string": str(i), "new_string": str(i + 1)})
        t.say("Done, it works now.")
        code, rep = diag(t.write(tmp / "loop.jsonl"))
        s = signals(rep)
        check(code == 1, "problems give exit code 1")
        check("repeated-failure" in s and s["repeated-failure"]["layer"] == "loop"
              and s["repeated-failure"]["severity"] == "high", "repeated identical failure is a high loop finding")
        check("/rewind" in s["repeated-failure"]["fix"] and "/advisor" in s["repeated-failure"]["fix"],
              "stuck loop points to /rewind and /advisor")
        check("same-error" not in s, "same error isn't reported twice")
        check("edit-churn" in s and "app.ts" in s["edit-churn"]["what"], "six edits to one file flagged")
        check("unverified" in s and s["unverified"]["severity"] == "high" and "/verify" in s["unverified"]["fix"],
              "'done' with no check after the last edit is high, fix is /verify")
        check(rep["verdict"] == "weakest layer: loop", "verdict names the loop layer")

        # 3. same error across different inputs
        t = T(repo)
        t.user("Connect to the database and list the tables in the analytics schema")
        for q in ("select 1", "select 2", "select 3"):
            t.tool("Bash", {"command": f"psql -c '{q}'"}, result="psql: error: connection refused", error=True)
        code, rep = diag(t.write(tmp / "same.jsonl"))
        s = signals(rep)
        check("same-error" in s and "repeated-failure" not in s, "the same error with different inputs")

        # 4. context: auto compaction, and a big request without one
        t = T(repo)
        t.user("Refactor the whole ingestion module")
        t.compact(pre=190_000)
        t.say("Continuing after the summary.")
        code, rep = diag(t.write(tmp / "compact.jsonl"))
        s = signals(rep)
        check("compaction" in s and s["compaction"]["layer"] == "context" and s["compaction"]["severity"] == "warn",
              "auto compaction is a context warning")
        check("/context" in s["compaction"]["fix"] and "/btw" in s["compaction"]["fix"], "compaction fix names /context and /btw")
        check("190000" in " ".join(s["compaction"]["evidence"]), "compaction evidence has the token count")
        t = T(repo)
        t.user("Summarize every log file in logs/")
        t.say("Reading them all.", tokens=170_000)
        code, rep = diag(t.write(tmp / "peak.jsonl"))
        check("context-peak" in signals(rep), "a 170k-token request flagged")
        t = T(repo)
        t.user("Tidy up the notes so far")
        t.compact(trigger="manual")
        code, rep = diag(t.write(tmp / "manual.jsonl"))
        check(code == 0 and signals(rep)["compaction"]["severity"] == "info", "a manual /compact is only info")

        # 5. harness: denials, untrusted folder, long foreground command, timeout
        t = T(repo)
        t.user("Deploy the staging build and run the smoke tests")
        t.tool("Bash", {"command": "rm -rf build"}, result="Permission for this action was denied by the Claude Code auto mode classifier.", error=True)
        t.tool("Bash", {"command": "git push"}, result="The user doesn't want to proceed with this tool use. The tool use was rejected", error=True, reject=True)
        t.tool("Bash", {"command": "claude -p hi"}, result="Ignoring 6 permissions.allow entries from .claude/settings.json: this workspace has not been trusted.", error=True)
        t.tool("Bash", {"command": "npm run e2e"}, result="ok", took=300)
        t.tool("Bash", {"command": "npm run dev"}, result="Command timed out after 2m 0s", error=True)
        t.tool("Bash", {"command": "npm run dev", "run_in_background": True}, took=400)
        code, rep = diag(t.write(tmp / "harness.jsonl"))
        s = signals(rep)
        check("permission-denied" in s and "2 tool call" in s["permission-denied"]["what"], "two denials counted")
        check("untrusted-folder" in s and s["untrusted-folder"]["severity"] == "high", "untrusted folder is high")
        fw = s.get("foreground-wait", {})
        check(fw and "2 shell" in fw["what"] and "/tasks" in fw["fix"], "slow and timed-out foreground commands, not backgrounded ones")
        check("repeated-failure" not in s, "denials aren't counted as a stuck loop")
        check(rep["verdict"] == "weakest layer: harness", "verdict names the harness layer")

        # 6. prompt: no CLAUDE.md in a git repo, terse start, corrections, interrupts
        (repo / "CLAUDE.md").unlink()
        t = T(repo)
        t.user("fix it")
        for i in range(15):
            t.tool("Read", {"file_path": f"{repo}/f{i}.md"})
        t.user("no, not that file")
        t.user("[Request interrupted by user]")
        t.user("I said the parser, not the lexer")
        t.user("[Request interrupted by user for tool use]")
        code, rep = diag(t.write(tmp / "prompt.jsonl"))
        s = signals(rep)
        check("no-claude-md" in s and "/init" in s["no-claude-md"]["fix"], "missing CLAUDE.md points to /init")
        check("terse-start" in s and s["terse-start"]["severity"] == "info", "terse opening prompt noted")
        check("corrections" in s and "2 times" in s["corrections"]["what"], "two corrections found")
        check("interrupts" in s, "interrupts found")
        code, rep = diag(tmp / "prompt.jsonl", "--no-fs")
        check("no-claude-md" not in signals(rep), "--no-fs skips the folder check")
        code, rep = diag(tmp / "prompt.jsonl", "--no-snippets")
        ev = " ".join(e for f in rep["findings"] for e in f["evidence"])
        check("lexer" not in ev and "not that file" not in ev, "--no-snippets keeps prompt text out")

        # 7. subagent rows ignored by default
        (repo / "CLAUDE.md").write_text("x")
        t = T(repo)
        t.user("Investigate why nightly loads are slow")
        for _ in range(3):
            t.tool("Bash", {"command": "false"}, result="Exit code 1", error=True, sidechain=True)
        code, rep = diag(t.write(tmp / "side.jsonl"))
        check("repeated-failure" not in signals(rep), "sidechain rows ignored by default")
        code, rep = diag(tmp / "side.jsonl", "--include-subagents")
        check("repeated-failure" in signals(rep), "--include-subagents reads them")

        # 8. finding sessions: by id and --latest under the project's slug
        slug = "".join(c if c.isalnum() else "-" for c in str(repo.resolve()))
        pdir = projects / slug
        pdir.mkdir(parents=True)
        (pdir / "aaaa-1111.jsonl").write_text((tmp / "healthy.jsonl").read_text())
        os.utime(pdir / "aaaa-1111.jsonl", (1, 1))
        (pdir / "bbbb-2222.jsonl").write_text((tmp / "loop.jsonl").read_text())
        r = run("list", "--project", str(repo))
        check(r.returncode == 0 and r.stdout.splitlines()[0].startswith("bbbb-2222")
              and "Fix the parser" in r.stdout, "list shows newest first with titles")
        code, rep = diag("aaaa-1111")
        check(rep["verdict"] == "healthy", "a session id resolves")
        r = run("diagnose", "--latest", "--project", str(repo))
        check(r.returncode == 1 and "## LOOP" in r.stdout and "Fix: " in r.stdout, "--latest text report groups by layer")
        r = run("diagnose", "nope-0000")
        check(r.returncode != 0 and "Can't find" in r.stderr, "unknown id is an error")
        r = run("diagnose")
        check(r.returncode == 2, "no target is exit 2")

        # 9. never writes to the transcripts folder
        before = {p: p.stat().st_mtime for p in pdir.iterdir()}
        run("diagnose", "--latest", "--project", str(repo))
        check({p: p.stat().st_mtime for p in pdir.iterdir()} == before, "transcripts are left untouched")

    print(f"\n{'All passed' if not failures else f'{len(failures)} failed'}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
