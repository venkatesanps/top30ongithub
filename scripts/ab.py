#!/usr/bin/env python3
"""Before/after test for one plugin: same task, same repo, plugin off vs on.

    python3 scripts/ab.py --plugin pm-execution@pm-skills \\
        --prompt "Write a one-page PRD for the Snowflake cost dashboard into PRD.md" \\
        --repo ~/work/sandbox-repo --runs 3 --check "test -s PRD.md"

Each run copies --repo to a fresh temp folder (your repo is never touched), then runs
`claude -p` headless with the plugin disabled (arm "off") and enabled (arm "on"), alternating
so time-of-day effects even out. It records cost, tokens, turns and time from Claude Code's JSON
output, runs --check in the copy (exit 0 = pass), and prints a table plus a JSON file.

The plugin must already be installed (claude plugin install ...). Only plugins can be toggled
this way; for CLI tools such as rtk, run the script twice with --off-settings / --on-settings.

A few runs show a direction, not proof. Small differences (under ~10%) are usually noise. For a
proper placebo-controlled method see https://github.com/simonether/skill-placebo.
Python standard library only.
"""
import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def run_arm(args, arm, settings, workdir):
    cmd = [args.claude, "-p", args.prompt, "--output-format", "json", "--settings", json.dumps(settings),
           "--permission-mode", args.permission_mode, "--max-budget-usd", str(args.budget)]
    if args.model:
        cmd += ["--model", args.model]
    t0 = time.time()
    p = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True, timeout=args.timeout)
    wall = time.time() - t0
    try:
        d = json.loads(p.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        d = {"is_error": True, "result": (p.stderr or p.stdout)[-300:]}
    u = d.get("usage") or {}
    tokens = sum(u.get(k) or 0 for k in ("input_tokens", "output_tokens",
                                          "cache_creation_input_tokens", "cache_read_input_tokens"))
    ok = None
    if args.check:
        ok = subprocess.run(args.check, shell=True, cwd=workdir, capture_output=True, timeout=600).returncode == 0
    return {"arm": arm, "error": bool(d.get("is_error")) or p.returncode != 0,
            "cost_usd": d.get("total_cost_usd"), "tokens": tokens, "output_tokens": u.get("output_tokens"),
            "turns": d.get("num_turns"), "seconds": round((d.get("duration_ms") or wall * 1000) / 1000, 1),
            "check_passed": ok, "message": None if not d.get("is_error") else str(d.get("result"))[:300]}


def mean(xs):
    xs = [x for x in xs if isinstance(x, (int, float))]
    return statistics.mean(xs) if xs else None


def fmt(v, kind):
    if v is None:
        return "—"
    return {"usd": f"${v:.3f}", "int": f"{v:,.0f}", "s": f"{v:.0f}s", "f": f"{v:.1f}"}[kind]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plugin", help="name@marketplace, as shown by `claude plugin list`")
    ap.add_argument("--prompt", required=True, help="the task, exactly as you'd type it")
    ap.add_argument("--repo", default=".", help="folder to copy for each run (default: current folder)")
    ap.add_argument("--runs", type=int, default=3, help="runs per arm (default 3)")
    ap.add_argument("--check", help="shell command run in the copy afterwards; exit 0 = task passed")
    ap.add_argument("--model", help="e.g. sonnet or opus; default is your Claude Code default")
    ap.add_argument("--budget", type=float, default=1.0, help="max USD per single run (default 1.00)")
    ap.add_argument("--permission-mode", default="acceptEdits", help="passed to claude (default acceptEdits)")
    ap.add_argument("--off-settings", help="JSON settings for the 'off' arm (overrides --plugin)")
    ap.add_argument("--on-settings", help="JSON settings for the 'on' arm (overrides --plugin)")
    ap.add_argument("--out", default="ab-results.json", help="where to save per-run results")
    ap.add_argument("--timeout", type=int, default=1800, help="seconds per run (default 1800)")
    ap.add_argument("--claude", default=os.environ.get("CLAUDE_BIN", "claude"), help=argparse.SUPPRESS)
    args = ap.parse_args()

    if not args.plugin and not (args.off_settings and args.on_settings):
        ap.error("give --plugin, or both --off-settings and --on-settings")
    if not shutil.which(args.claude):
        sys.exit("Claude Code CLI not found. Install it first: npm install -g @anthropic-ai/claude-code")
    repo = Path(args.repo).expanduser().resolve()
    if not repo.is_dir():
        sys.exit(f"--repo {repo} is not a folder")
    if args.plugin:
        listed = subprocess.run([args.claude, "plugin", "list"], capture_output=True, text=True).stdout
        if args.plugin not in listed:
            sys.exit(f"{args.plugin} is not installed. Install it first, e.g. ./install.sh <number>")
    arms = {"off": json.loads(args.off_settings) if args.off_settings else {"enabledPlugins": {args.plugin: False}},
            "on": json.loads(args.on_settings) if args.on_settings else {"enabledPlugins": {args.plugin: True}}}

    results = []
    with tempfile.TemporaryDirectory(prefix="ab-") as tmp:
        for r in range(args.runs):
            order = ("off", "on") if r % 2 == 0 else ("on", "off")
            for arm in order:
                work = Path(tmp) / f"{arm}-{r + 1}"
                shutil.copytree(repo, work, symlinks=True,
                                ignore=shutil.ignore_patterns("node_modules", ".venv", "__pycache__"))
                print(f"run {r + 1}/{args.runs} · plugin {arm} ...", file=sys.stderr, flush=True)
                res = run_arm(args, arm, arms[arm], work)
                res["run"] = r + 1
                results.append(res)
                if res["error"]:
                    print(f"  error: {res['message']}", file=sys.stderr)

    Path(args.out).write_text(json.dumps({"plugin": args.plugin, "prompt": args.prompt, "runs": results}, indent=1))
    rows, summary = [], {}
    for arm in ("off", "on"):
        rs = [x for x in results if x["arm"] == arm]
        good = [x for x in rs if not x["error"]]
        checks = [x["check_passed"] for x in rs if x["check_passed"] is not None]
        summary[arm] = {k: mean(x[k] for x in good) for k in ("cost_usd", "tokens", "output_tokens", "turns", "seconds")}
        passed = f"{sum(checks)}/{len(checks)}" if checks else "—"
        rows.append(f"| {arm} | {len(good)}/{len(rs)} | {passed} | {fmt(summary[arm]['cost_usd'], 'usd')} | "
                    f"{fmt(summary[arm]['tokens'], 'int')} | {fmt(summary[arm]['output_tokens'], 'int')} | "
                    f"{fmt(summary[arm]['turns'], 'f')} | {fmt(summary[arm]['seconds'], 's')} |")
    print(f"\nPlugin: {args.plugin or 'custom settings'}   Runs per arm: {args.runs}\n")
    print("| Plugin | Runs ok | Check passed | Mean cost | Mean tokens | Output tokens | Turns | Time |")
    print("|---|---|---|---|---|---|---|---|")
    print("\n".join(rows))
    a, b = summary["off"]["cost_usd"], summary["on"]["cost_usd"]
    if a and b:
        ch = (b - a) / a * 100
        verdict = ("within noise for this few runs" if abs(ch) < 10 else
                   "cheaper with the plugin" if ch < 0 else "more expensive with the plugin")
        print(f"\nCost change with the plugin: {ch:+.0f}% ({verdict}).")
    print("Keep it only if the result is better (check passed, output you'd ship) or cheaper.")
    print(f"Per-run details: {args.out}")


if __name__ == "__main__":
    main()
