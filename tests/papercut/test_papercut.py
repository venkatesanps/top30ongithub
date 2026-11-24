"""Checks the papercut skill: filing, required fields, scrubbing, caps, the repo guard, search,
grouping by signature, summary, export (prints, never posts), torn lines, and the SKILL.md.

python3 tests/papercut/test_papercut.py   (no dependencies, no network)
"""
import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SK = ROOT / "plugins/top30-agents/skills/papercut"
PC = SK / "scripts/papercut.py"


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        home = td / "home"
        home.mkdir()
        log = home / ".claude/papercuts/papercuts.jsonl"
        env = dict(os.environ, HOME=str(home), PAPERCUT_LOG=str(log))
        env.pop("PAPERCUT_ALLOW_REPO", None)

        def run(*args, cwd=None, e=None):
            return subprocess.run([sys.executable, str(PC), *map(str, args)], capture_output=True, text=True,
                                  env=e or env, cwd=cwd or td)

        def rows():
            out = []
            for l in (log.read_text().splitlines() if log.exists() else []):
                try:
                    r = json.loads(l)
                except json.JSONDecodeError:
                    continue
                if isinstance(r, dict):
                    out.append(r)
            return out

        base = ["file", "--skill", "pr-create", "--tool", "gh", "--tried", "ran gh pr checks 123",
                "--expected", "a no-checks result", "--got", "404 Not Found after 30 retries"]

        r = run(*base, "--fix", "treat 404 as no CI", "--workaround", "skipped the wait step")
        check(r.returncode == 0 and r.stdout.startswith("filed "), f"file: {r.stdout}{r.stderr}")
        check("0 earlier reports" in r.stdout, f"first report counts 0 earlier: {r.stdout}")
        check(log.exists() and oct(log.stat().st_mode & 0o777) == "0o600", "log created with mode 600")
        rec = rows()[0]
        for k in ("id", "time", "skill", "tool", "tried", "expected", "got", "fix", "workaround", "sig", "severity"):
            check(k in rec, f"record has {k}")
        check(rec["severity"] == "medium" and rec["agent"] == "claude-code", "defaults")

        # the same problem with different numbers groups under one signature and surfaces the workaround
        r = run("file", "--skill", "pr-create", "--tool", "gh", "--tried", "ran gh pr checks 987",
                "--expected", "no checks", "--got", "404 Not Found after 12 retries")
        check("1 earlier report " in r.stdout and "earlier workaround: skipped the wait step" in r.stdout,
              f"duplicate detection: {r.stdout}")
        check(rows()[0]["sig"] == rows()[1]["sig"], "numbers don't split the signature")
        run("file", "--skill", "pr-create", "--tool", "gh", "--tried", "x", "--expected", "y", "--got", "permission denied")
        check(rows()[2]["sig"] != rows()[0]["sig"], "a different error gets its own signature")

        # required fields
        r = run("file", "--skill", "s", "--tried", "a", "--expected", "b", "--got", "  ")
        check(r.returncode != 0 and "--got is required" in r.stderr, f"blank --got refused: {r.stderr}")
        r = run("file", "--skill", "s", "--tried", "a", "--expected", "b")
        check(r.returncode != 0, "missing --got refused")

        # scrubbing and caps
        secret_got = (f"auth failed for me@example.com with ghp_{'a' * 36} and sk-ant-{'b' * 30} "
                      f"token=abc123secret password: 'hunter2' at {home}/work/app.py "
                      f"Bearer {'c' * 20} postgres://user:pw@db.local/x AKIA{'D' * 16}")
        run("file", "--skill", "sec", "--tried", "line one\nline two", "--expected", "ok", "--got", secret_got,
            "--fix", "use the retry flag " * 60)
        s = rows()[-1]
        blob = json.dumps(s)
        for leak in ("me@example.com", "ghp_", "sk-ant-", "abc123secret", "hunter2", str(home), "user:pw", "AKIA", "c" * 20):
            check(leak not in blob, f"scrubbed: {leak}")
        for mark in ("[EMAIL]", "[GITHUB TOKEN]", "[API KEY]", "[REDACTED]", "~/work/app.py", "[CREDENTIALS]@", "[AWS KEY]"):
            check(mark in s["got"], f"scrub marker {mark} in {s['got']}")
        check(s["tried"] == "line one line two", "fields collapse to one line")
        check(len(s["fix"]) == 300 and s["fix"].endswith("…"), "fields capped at 300")

        # repo guard: a log inside a git repo is refused, even when the folder doesn't exist yet
        repo = td / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        e2 = dict(env, PAPERCUT_LOG=str(repo / "not/yet/there.jsonl"))
        r = run(*base, e=e2)
        check(r.returncode != 0 and "inside a git repository" in r.stderr, f"repo guard: {r.stderr}")
        check(not (repo / "not").exists(), "nothing written inside the repo")
        r = run(*base, e=dict(e2, PAPERCUT_ALLOW_REPO="1"))
        check(r.returncode == 0, "PAPERCUT_ALLOW_REPO overrides")
        r = run(*base, cwd=repo)  # cwd in a repo, log outside: allowed
        check(r.returncode == 0, f"cwd inside a repo doesn't block a log outside: {r.stderr}")

        # torn or foreign lines never break reading
        with open(log, "a") as f:
            f.write('{"half": \n["not a record"]\n{"torn": tr')  # last line has no newline
        r = run("summary")
        check(r.returncode == 0, f"summary survives torn lines: {r.stderr}")
        n = len(rows())
        run(*base)
        check(len(rows()) == n + 1, "a report after a torn last line still lands on its own line")

        # search
        r = run("search", "404 retries")
        check(r.returncode == 0 and "match" in r.stdout and "workaround: skipped the wait step" in r.stdout, f"search: {r.stdout}")
        r = run("search", "404", "--skill", "nope")
        check(r.stdout.strip() == "0 matches", f"search skill filter: {r.stdout}")
        r = run("search", "zzzzqqq")
        check(r.stdout.strip() == "0 matches", "search miss")

        # show
        pid = rows()[0]["id"]
        r = run("show", pid)
        check(r.returncode == 0 and json.loads(r.stdout)["id"] == pid, "show")
        check(run("show", "nope0000").returncode == 1, "show unknown id")

        # summary
        r = run("summary", "--skill", "pr-create")
        check("pr-create: " in r.stdout and "distinct problem" in r.stdout and "fix: treat 404 as no CI" in r.stdout, f"summary: {r.stdout}")
        top = r.stdout.splitlines()[2]
        check(top.strip().startswith("4×") or top.strip().startswith("5×") or "×" in top, f"most-reported first: {r.stdout}")
        j = json.loads(run("summary", "--json").stdout)
        check(j[0]["count"] >= j[-1]["count"] and all("ids" in g for g in j), "summary --json sorted by count")
        check("no papercuts for ghost" in run("summary", "--skill", "ghost").stdout, "empty summary")
        r = run("summary", "--days", "1")
        check("pr-create" in r.stdout, "--days keeps recent reports")

        # export prints, never posts
        r = run("export", "--skill", "pr-create")
        check(r.returncode == 0 and r.stdout.startswith("# papercut(pr-create): 404") and "**Suggested fix:** treat 404" in r.stdout
              and "Report ids:" in r.stdout, f"export markdown: {r.stdout}")
        r = run("export", "--skill", "pr-create", "--gh", "owner/repo", "--body-file", td / "body.md")
        check("gh issue create --repo owner/repo" in r.stdout and "--body-file" in r.stdout and "run it only if" in r.stdout,
              f"export gh: {r.stdout}")
        check((td / "body.md").read_text().startswith("Papercut on `pr-create`"), "body file written")
        check(run("export", "--skill", "ghost").returncode == 1, "export unknown skill")
        r = run("export", "--skill", "pr-create", "--gh", "owner/repo")
        check(str(log.parent / "papercut-") in r.stdout, f"default body file sits beside the log: {r.stdout}")
        run("file", "--skill", "evil", "--tried", "x", "--expected", "y", "--got", "boom $(touch pwned) `id` \"; rm -rf ~ #")
        r = run("export", "--skill", "evil", "--gh", "owner/repo", "--body-file", td / "evil.md")
        line = [l for l in r.stdout.splitlines() if l.strip().startswith("gh issue create")][0]
        argv = shlex.split(line)
        title = argv[argv.index("--title") + 1]
        check(argv[:3] == ["gh", "issue", "create"] and "$(touch pwned)" in title and "`id`" in title and "rm -rf" in title
              and argv[-2:] == ["--body-file", str(td / "evil.md")], f"export command is shell-quoted: {line}")
        check("--label" not in line, "no label that may not exist")
        src = PC.read_text()
        check("subprocess.run([\"gh\"" not in src and "urllib" not in src and "http.client" not in src and "socket" not in src,
              "the script has no network path")

    sk = (SK / "SKILL.md").read_text()
    check(sk.startswith("---\nname: papercut\n"), "SKILL.md frontmatter")
    check("Search first" in sk and "File it once" in sk and "Carry on" in sk, "SKILL.md workflow")
    check("never posts" in sk and "CLAUDE.md" in sk, "SKILL.md: export never posts; CLAUDE.md line for always-on")
    lint = subprocess.run([sys.executable, str(ROOT / "scripts/skill_lint.py"), str(SK)], capture_output=True, text=True)
    check(lint.returncode == 0 and "0 findings" in lint.stdout, f"papercut SKILL.md lints clean: {lint.stdout}")
    check((ROOT / "plugins/top30-agents/claude-ai/papercut.zip").exists(), "claude-ai zip present")

    if fails:
        print(f"FAIL ({len(fails)})")
        for f in fails:
            print(" -", f)
        return 1
    print("ok - papercut: file, scrub, caps, repo guard, search, group, summary, export")
    return 0


if __name__ == "__main__":
    sys.exit(main())
