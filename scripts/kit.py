#!/usr/bin/env python3
"""Maintenance tool for the Claude plugins kit. catalog.json is the single source of truth.

Steps (run in this order by the daily workflow; each can also run alone):
  check    Look at every upstream repo: new commits, moved/archived/renamed, marketplace
           names still matching our install commands, package versions, stars.
  bump     Re-pin changed upstream repos (git submodules under sources/) to their new commit.
  pack     Rebuild the Claude app skill zips for items whose upstream changed (or --all).
  costs    Re-measure per-session token cost of Claude Code plugins (claude plugin details).
  smoke    Install items in a throwaway HOME and run their verify command.
  render   Regenerate install.sh, verify.sh, guide/index.html, README status, notices.
  report   Write CHANGELOG.md entry, commit message and the attention-issue body.

Usage: python3 scripts/kit.py <step> [--all | --changed | N N ...]
Run state between steps lives in build/run.json (not committed).
"""
import datetime as dt
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "catalog.json"
BUILD = ROOT / "build"
RUN = BUILD / "run.json"
ZIPDIR = ROOT / "claude-ai-skills"
TODAY = dt.date.today().isoformat()
CHECK_KINDS = {"unreachable", "moved", "renamed", "archived", "marketplace", "package", "license"}
EXCLUDE_DIRS = {".git", "node_modules", "__pycache__", "tests", "test", "evals", ".github", ".pytest_cache"}
ZIP_TIME = (2026, 1, 1, 0, 0, 0)


# ---------- helpers ----------
def load():
    return json.loads(CATALOG.read_text())


def save(c):
    CATALOG.write_text(json.dumps(c, indent=1, ensure_ascii=False) + "\n")


def run_state():
    return json.loads(RUN.read_text()) if RUN.exists() else {"date": TODAY, "changed": {}, "notes": []}


def save_run(r):
    BUILD.mkdir(exist_ok=True)
    RUN.write_text(json.dumps(r, indent=1))


def log(*a):
    print(*a, flush=True)


def http(url, headers=None, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "claude-plugins-kit", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception:
        return None


def gh_api(path):
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    h = {"Accept": "application/vnd.github+json"}
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    b = http(f"https://api.github.com/{path}", h)
    try:
        return json.loads(b) if b else None
    except ValueError:
        return None


def raw(repo, path, ref="HEAD"):
    b = http(f"https://raw.githubusercontent.com/{repo}/{ref}/{path}")
    return b.decode("utf-8", "replace") if b else None


def git(*args, cwd=ROOT, check=True):
    return subprocess.run(["git", *args], cwd=cwd, check=check, capture_output=True, text=True).stdout.strip()


def ls_remote(repo):
    try:
        out = subprocess.run(["git", "ls-remote", f"https://github.com/{repo}.git", "HEAD"],
                             capture_output=True, text=True, timeout=60).stdout.split()
        return out[0] if out else None
    except subprocess.TimeoutExpired:
        return None


def pinned():
    out = git("ls-files", "-s", "sources")
    return {l.split()[3]: l.split()[1] for l in out.splitlines() if l.startswith("160000")}


def select(c, argv, r=None):
    if not argv or argv == ["--changed"]:
        # changed upstream, plus anything whose last install test failed (so fixes get confirmed)
        ch = set(int(k) for k in (r or run_state())["changed"])
        return [i for i in c["items"] if i["n"] in ch or i.get("verified", {}).get("result") == "fail"]
    if argv == ["--all"]:
        return c["items"]
    want = {int(a) for a in argv}
    return [i for i in c["items"] if i["n"] in want]


def set_problems(it, kinds, new):
    it["problems"] = [p for p in it.get("problems", []) if p["kind"] not in kinds] + new
    it["status"] = "attention" if it["problems"] else "ok"


# ---------- check ----------
MOVED = re.compile(r"(no longer (?:the active home|maintained|actively (?:developed|maintained)|being developed)"
                   r"|(?:has|have) (?:been )?moved to|project (?:has )?moved|now (?:lives|continues) (?:at|as|in)"
                   r"|deprecated in favou?r of|this repository (?:is|has been) archived)", re.I)
GH_LINK = re.compile(r"github\.com/([\w.-]+/[\w.-]+)")


RENAMES = []


def apply_rename(it, old, new):
    """Point every field and the submodule URL at the repo's new home (old URLs only redirect)."""
    pat = re.compile(re.escape(old), re.I)
    for k in ("repo", "alt", "verify", "use", "note", "what"):
        if isinstance(it.get(k), str):
            it[k] = pat.sub(new, it[k])
    it["install"] = [pat.sub(new, x) for x in it["install"]]
    if "ci" in it and it["ci"].get("install"):
        it["ci"]["install"] = [pat.sub(new, x) for x in it["ci"]["install"]]
    gm = ROOT / ".gitmodules"
    gm.write_text(re.sub(rf"https://github\.com/{re.escape(old)}\.git", f"https://github.com/{new}.git", gm.read_text(), flags=re.I))
    RENAMES.append((it["name"], old, new))


def check_item(it):
    repo, probs, up = it["repo"], [], it.setdefault("upstream", {})
    head = ls_remote(repo)
    if not head:
        probs.append({"kind": "unreachable", "msg": f"github.com/{repo} did not answer git ls-remote"})
    up["head"] = head or up.get("head")
    meta = gh_api(f"repos/{repo}")
    if meta and "full_name" in meta:
        up.update(stars=meta.get("stargazers_count"), pushed=(meta.get("pushed_at") or "")[:10],
                  license=(meta.get("license") or {}).get("spdx_id") or up.get("license"),
                  default_branch=meta.get("default_branch"))
        if meta.get("archived"):
            probs.append({"kind": "archived", "msg": "Upstream repo is archived (read-only)."})
        if meta["full_name"].lower() != repo.lower():
            # GitHub's API names the canonical repo after a transfer/rename: follow it everywhere.
            apply_rename(it, repo, meta["full_name"])
            repo = it["repo"]
    readme = raw(repo, "README.md") or ""
    head_text = readme[:4000]
    m = MOVED.search(head_text)
    if m:
        near = head_text[m.start(): m.start() + 500]
        others = [l.rstrip(".") for l in GH_LINK.findall(near) if l.lower().rstrip(".") != repo.lower()]
        if others:
            probs.append({"kind": "moved", "msg": f"README says the project moved (points to github.com/{others[0]})."})
    # marketplace names used by our install commands still exist?
    src = None
    for cmd in it["install"]:
        a = re.match(r"claude plugin marketplace add (\S+)", cmd)
        if a:
            src = a.group(1)
        b = re.match(r"claude plugin install (\S+)@(\S+)", cmd)
        if b and src and re.fullmatch(r"[\w.-]+/[\w.-]+", src):
            mj = raw(src, ".claude-plugin/marketplace.json")
            try:
                mk = json.loads(mj) if mj else None
            except ValueError:
                mk = None
            if not mk:
                probs.append({"kind": "marketplace", "msg": f"{src} has no readable .claude-plugin/marketplace.json."})
            else:
                names = [p.get("name") for p in mk.get("plugins", [])]
                if mk.get("name") != b.group(2):
                    probs.append({"kind": "marketplace", "msg": f"Marketplace in {src} is now named '{mk.get('name')}', install uses '{b.group(2)}'."})
                elif b.group(1) not in names:
                    probs.append({"kind": "marketplace", "msg": f"Plugin '{b.group(1)}' is no longer listed in {src} (has: {', '.join(n for n in names if n)})."})
    # package registries
    vers = {}
    for p in it.get("packages", []):
        if "pypi" in p:
            j = http(f"https://pypi.org/pypi/{p['pypi']}/json")
            v = json.loads(j)["info"]["version"] if j else None
            key = f"pypi:{p['pypi']}"
        else:
            j = http(f"https://registry.npmjs.org/{p['npm'].replace('/', '%2F')}/latest")
            v = json.loads(j).get("version") if j else None
            key = f"npm:{p['npm']}"
        if v:
            vers[key] = v
        else:
            probs.append({"kind": "package", "msg": f"{key} not found on its registry."})
    if vers:
        up["packages"] = vers
    return head, probs


def cmd_check(argv):
    c, r = load(), run_state()
    pins = pinned()
    items = select(c, argv or ["--all"], r)
    for it in items:
        before = dict(it.get("upstream", {}))
        head, probs = check_item(it)
        old = pins.get(it["source"])
        if head and head != old:
            r["changed"][str(it["n"])] = {"old": old, "new": head}
        for k, v in (it["upstream"].get("packages") or {}).items():
            ov = (before.get("packages") or {}).get(k)
            if ov and ov != v:
                r["notes"].append(f"{it['name']}: {k} {ov} → {v}")
        oldp = {p["msg"] for p in it.get("problems", []) if p["kind"] in CHECK_KINDS}
        set_problems(it, CHECK_KINDS, probs)
        for p in probs:
            if p["msg"] not in oldp:
                r["notes"].append(f"⚠ {it['name']}: {p['msg']}")
        for m in oldp - {p["msg"] for p in probs}:
            r["notes"].append(f"✓ {it['name']}: resolved — {m}")
        log(f"{it['n']:2d} {it['name']:32s} {'CHANGED' if str(it['n']) in r['changed'] else 'same   '} {len(probs)} problem(s)")
    for name, old, new in RENAMES:
        r["notes"].append(f"{name}: repo moved from github.com/{old} to github.com/{new}; catalog and install commands updated automatically")
    RENAMES.clear()
    c["checked"] = TODAY
    save(c)
    save_run(r)
    log(f"{len(r['changed'])} upstream repo(s) changed")


# ---------- bump ----------
def ensure_source(it, sha):
    os.environ.setdefault("GIT_LFS_SKIP_SMUDGE", "1")
    path = ROOT / it["source"]
    if not (path / ".git").exists():
        git("submodule", "update", "--init", "--depth", "1", it["source"], check=False)
    if not (path / ".git").exists():
        shutil.rmtree(path, ignore_errors=True)
        git("clone", "--depth", "1", "--filter=blob:limit=20m", f"https://github.com/{it['repo']}.git", str(path))
    if git("rev-parse", "HEAD", cwd=path, check=False) != sha:
        git("fetch", "--depth", "1", "origin", sha, cwd=path)
        git("checkout", "-q", sha, cwd=path)
    return path


def cmd_bump(argv):
    c, r = load(), run_state()
    for it in select(c, argv, r):
        new = r["changed"].get(str(it["n"]), {}).get("new") or ls_remote(it["repo"])
        if not new:
            log(f"skip {it['source']}: no upstream commit")
            continue
        # Re-pinning only needs the commit id; pack fetches a checkout when it needs files.
        git("update-index", "--add", "--cacheinfo", f"160000,{new},{it['source']}")
        it.setdefault("upstream", {})["pinned"] = new
        log(f"pinned {it['source']} -> {new[:10]}")
    save(c)


# ---------- pack ----------
def frontmatter(p):
    t = p.read_text(encoding="utf-8", errors="replace")
    m = re.match(r"^---\s*\n(.*?)\n---", t, re.S)
    if not m:
        return None, False
    name = re.search(r"^name:\s*(.+)$", m.group(1), re.M)
    return (name.group(1).strip().strip("'\"") if name else None), bool(re.search(r"^description:", m.group(1), re.M))


def find_license(src):
    for f in sorted(src.iterdir()):
        if re.match(r"(licen[cs]e|copying)(\.md|\.txt)?$", f.name, re.I) and f.is_file():
            t = f.read_text(errors="replace")
            kind = ("MIT" if re.search(r"MIT License|Permission is hereby granted", t) else
                    "Apache-2.0" if "Apache License" in t else
                    "AGPL-3.0" if "AFFERO" in t.upper() else
                    "GPL" if "GNU GENERAL PUBLIC" in t.upper() else
                    "BSD" if "BSD" in t else "see LICENSE")
            return t, kind
    for pj in (src / ".claude-plugin" / "plugin.json", src / "package.json"):
        try:
            lic = json.loads(pj.read_text()).get("license")
        except (OSError, ValueError):
            lic = None
        if lic:
            note = (f"{lic} license, as declared in the upstream {pj.relative_to(src)}.\n"
                    f"The upstream repository has no separate license file.\n")
            return note, lic
    return None, None


def zwrite(z, arc, data, mode=0o644):
    zi = zipfile.ZipInfo(arc, ZIP_TIME)
    zi.compress_type = zipfile.ZIP_DEFLATED
    zi.external_attr = (mode & 0xFFFF) << 16
    z.writestr(zi, data)


def pack_item(it, taken):
    cfg, src = it["zip"], ROOT / it["source"]
    folder = ZIPDIR / cfg["folder"]
    lic_text, lic_kind = find_license(src)
    if not lic_text:
        return [], {"kind": "license", "msg": "No license file or declared license upstream; skill zips not built."}
    base = src / cfg["base"] if cfg["base"] else src
    skills = cfg["skills"]
    if skills == "*":
        skills = sorted(d.name for d in base.iterdir() if (d / "SKILL.md").is_file())
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    built = []
    for s in skills:
        sd = (base / s).resolve()
        sk = sd / "SKILL.md"
        if not sk.is_file():
            log(f"  skip {s}: no SKILL.md")
            continue
        name, has_desc = frontmatter(sk)
        if not name or not has_desc:
            log(f"  skip {s}: SKILL.md frontmatter lacks name/description")
            continue
        if name in taken and taken[name] != cfg["folder"]:
            log(f"  skip {s}: name '{name}' already used by {taken[name]}")
            continue
        taken[name] = cfg["folder"]
        files = []
        only = cfg.get("only")
        for rootd, dirs, fs in os.walk(sd, followlinks=True):
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDE_DIRS)
            for f in sorted(fs):
                full = Path(rootd) / f
                rel = full.relative_to(sd).as_posix()
                if only and rel not in only:
                    continue
                files.append((rel, full))
        zp = folder / f"{name}.zip"
        with zipfile.ZipFile(zp, "w") as z:
            for rel, full in files:
                zwrite(z, f"{name}/{rel}", full.read_bytes(), full.stat().st_mode)
            if not any(rel.upper().startswith(("LICENSE", "COPYING")) for rel, _ in files):
                zwrite(z, f"{name}/LICENSE", lic_text.encode())
        built.append({"folder": cfg["folder"], "skill": name, "path": str(Path(cfg["base"] or ".") / s),
                      "bytes": zp.stat().st_size, "license": lic_kind})
    return built, None


def cmd_pack(argv):
    c, r = load(), run_state()
    man_p = ZIPDIR / "_manifest.json"
    manifest = json.loads(man_p.read_text()) if man_p.exists() else []
    items = [i for i in select(c, argv, r) if i.get("zip")]
    folders = {i["zip"]["folder"] for i in items}
    keep = [m for m in manifest if m.get("folder") not in folders]
    taken = {m["skill"]: m["folder"] for m in keep}
    for it in items:
        sha = it.get("upstream", {}).get("pinned") or pinned().get(it["source"])
        ensure_source(it, sha)
        built, prob = pack_item(it, taken)
        set_problems(it, {"license"}, [prob] if prob else [])
        if built and not it.setdefault("upstream", {}).get("license"):
            it["upstream"]["license"] = built[0]["license"]
        for b in built:
            b["commit"] = sha
        keep += built
        log(f"{it['zip']['folder']}: {len(built)} zip(s)")
    keep.sort(key=lambda m: (m["folder"], m["skill"]))
    man_p.write_text(json.dumps(keep, indent=1) + "\n")
    save(c)


# ---------- costs ----------
def env_for(home):
    e = dict(os.environ)
    npm = Path(home) / ".npm-global"
    e.update(HOME=str(home), NPM_CONFIG_PREFIX=str(npm), GIT_LFS_SKIP_SMUDGE="1", CI="1",
             PATH=f"{home}/.local/bin:{npm}/bin:{home}/.bun/bin:" + os.environ.get("PATH", ""))
    return e


def sh(cmd, env, cwd, timeout=900):
    try:
        p = subprocess.run(["bash", "-c", cmd], env=env, cwd=cwd, capture_output=True, text=True,
                           timeout=timeout, input="\n" * 50)
        return p.returncode, (p.stdout + p.stderr)
    except subprocess.TimeoutExpired as e:
        return 124, f"timed out after {timeout}s\n{(e.stdout or '')}"


def cmd_costs(argv):
    c, r = load(), run_state()
    if not shutil.which("claude"):
        log("claude CLI not found; skipping cost measurement")
        return
    ver = subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=60).stdout.strip()
    measured = 0
    for it in select(c, argv, r):
        lines = [l for l in it["install"] if l.startswith("claude plugin")]
        ids = [re.match(r"claude plugin install (\S+)", l).group(1) for l in lines if l.startswith("claude plugin install")]
        if not ids:
            continue
        with tempfile.TemporaryDirectory() as home:
            env = env_for(home)
            ok = all(sh(l, env, home, 600)[0] == 0 for l in lines)
            vals = []
            for pid in ids if ok else []:
                rc, out = sh(f"claude plugin details {shlex.quote(pid)}", env, home, 120)
                m = re.search(r"Always-on:\s+(~[\d,]+)", out)
                if rc or not m:
                    ok = False
                    break
                vals.append(m.group(1))
        if ok and vals:
            new = " + ".join(vals)
            if new != it["always_on"]:
                r["notes"].append(f"{it['name']}: per-session tokens {it['always_on']} → {new}")
                it["always_on"] = new
            measured += 1
            log(f"{it['n']:2d} {it['name']:32s} {new}")
        else:
            log(f"{it['n']:2d} {it['name']:32s} could not measure (kept {it['always_on']})")
    if measured:
        c["costs_measured_with"] = f"{ver or 'Claude Code'} on {TODAY}"
    save(c)
    save_run(r)


# ---------- smoke ----------
def cmd_smoke(argv):
    c, r = load(), run_state()
    logs = BUILD / "smoke"
    logs.mkdir(parents=True, exist_ok=True)
    results = r.setdefault("smoke", {})
    for it in select(c, argv, r):
        ci = it.get("ci", {})
        if ci.get("skip"):
            log(f"{it['n']:2d} skip: {ci['skip']}")
            continue
        with tempfile.TemporaryDirectory() as home:
            env = env_for(home)
            out_all, failed = [], None
            for cmd in ci.get("install") or it["install"]:
                rc, out = sh(cmd, env, home)
                out_all.append(f"$ {cmd}\n{out}\n[exit {rc}]")
                if rc:
                    failed = (cmd, rc, out)
                    break
            if not failed:
                vcmd = ci.get("verify") or it["verify"]
                rc, out = sh(vcmd, env, home, 300)
                out_all.append(f"$ {vcmd}  (verify)\n{out}\n[exit {rc}]")
                if rc:
                    failed = (vcmd + "  (verify)", rc, out)
        (logs / f"{it['n']:02d}.log").write_text("\n".join(out_all))
        prev = it.get("verified", {}).get("result")
        if failed:
            tail = " | ".join(l.strip() for l in failed[2].strip().splitlines()[-3:])[:300]
            set_problems(it, {"install"}, [{"kind": "install", "msg": f"`{failed[0]}` failed (exit {failed[1]}): {tail}"}])
            it["verified"] = {"date": TODAY, "result": "fail"}
            if prev != "fail":
                r["notes"].append(f"⚠ {it['name']}: install test failed")
        else:
            set_problems(it, {"install"}, [])
            it["verified"] = {"date": TODAY, "result": "pass"}
            if prev == "fail":
                r["notes"].append(f"✓ {it['name']}: install test passes again")
        results[str(it["n"])] = it["verified"]["result"]
        log(f"{it['n']:2d} {it['name']:32s} {it['verified']['result']}")
    save(c)
    save_run(r)


# ---------- render ----------
def q(s):
    return shlex.quote(str(s))


def bash_arr(name, vals):
    return f"{name}=(" + " ".join(q(v) for v in vals) + ")"


def render_scripts(c):
    items, rows = c["items"], c["rows"]
    cases = []
    for it in items:
        body = "\\n".join(x.replace("\\", "\\\\").replace("'", "'\\''") for x in it["install"])
        cases.append(f"    {it['n']}) printf '%b\\n' '{body}' ;;")
    probs = ["; ".join(p["msg"] for p in it.get("problems", [])) for it in items]
    tpl = (ROOT / "scripts" / "install.sh.in").read_text()
    out = (tpl.replace("@@ARRAYS@@", "\n".join([
        bash_arr("ROW_NAMES", [rows[str(i)] for i in range(1, 6)]),
        bash_arr("NAMES", [i["name"] for i in items]),
        bash_arr("REPOS", [i["repo"] for i in items]),
        "ROWS=(" + " ".join(str(i["row"]) for i in items) + ")",
        bash_arr("NEEDS", [" ".join(i["needs"]) for i in items]),
        bash_arr("NOTES", [i["note"] for i in items]),
        bash_arr("USES", [i["use"] for i in items]),
        bash_arr("COST", [i["always_on"] for i in items]),
        bash_arr("PROBLEMS", probs),
        bash_arr("VERIFIED", [f"{i['verified']['result']} {i['verified']['date']}" for i in items]),
        f"CATALOG_DATE={q(c.get('checked', c['generated']))}"]))
           .replace("@@CASES@@", "\n".join(cases)))
    (ROOT / "install.sh").write_text(out)
    v = ["#!/usr/bin/env bash", "# Checks that installed plugins work. ./verify.sh (all)  or  ./verify.sh 5 30",
         "set -u", "verify_cmd() {", "  case \"$1\" in"]
    for it in items:
        cmd = it["verify"].replace("'", "'\\''")
        v.append(f"    {it['n']}) echo '{cmd}' ;;")
    v += ["  esac", "}", bash_arr("NAMES", [i["name"] for i in items]),
          (ROOT / "scripts" / "verify.sh.in").read_text()]
    (ROOT / "verify.sh").write_text("\n".join(v))
    for f in ("install.sh", "verify.sh"):
        os.chmod(ROOT / f, 0o755)


def stats(c):
    man = json.loads((ZIPDIR / "_manifest.json").read_text())
    items = c["items"]
    return {
        "repos": len(items),
        "plugins": sum(1 for i in items if any(l.startswith("claude plugin install") for l in i["install"])),
        "zips": len(man),
        "zip_repos": len({m["folder"] for m in man}),
        "passing": sum(1 for i in items if i["verified"]["result"] == "pass"),
        "attention": sum(1 for i in items if i.get("problems")),
    }


def render_guide(c):
    st = stats(c)
    data = dict(c, stats=st)
    t = (ROOT / "guide" / "template.html").read_text()
    t = t.replace("/*CATALOG*/null", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    (ROOT / "guide" / "index.html").write_text(t)


def fmt_stars(n):
    return "—" if n is None else (f"{n/1000:.1f}k".replace(".0k", "k") if n >= 1000 else str(n))


def render_readme(c):
    st = stats(c)
    lines = [f"_Checked {c.get('checked', c['generated'])}: {st['repos']} repos, "
             f"{st['passing']} passing install tests, {st['attention']} needing attention. "
             f"Token costs measured with {c.get('costs_measured_with', 'Claude Code')}._", "",
             "| # | Plugin | Repo | Stars | Upstream updated | Install test | Tokens/session | Status |",
             "|---|---|---|---|---|---|---|---|"]
    for it in c["items"]:
        up, v = it.get("upstream", {}), it["verified"]
        status = "OK" if not it.get("problems") else "⚠ " + "; ".join(p["msg"] for p in it["problems"])[:140]
        lines.append(f"| {it['n']} | {it['name']} | [{it['repo']}](https://github.com/{it['repo']}) | "
                     f"{fmt_stars(up.get('stars'))} | {up.get('pushed') or '—'} | {v['result']} ({v['date']}) | "
                     f"{it['always_on']} | {status.replace('|', '/')} |")
    rd = ROOT / "README.md"
    t = rd.read_text()
    block = "<!-- status:start -->\n" + "\n".join(lines) + "\n<!-- status:end -->"
    t = re.sub(r"<!-- status:start -->.*?<!-- status:end -->", lambda _: block, t, flags=re.S)
    rd.write_text(t)


def render_notices(c):
    man = json.loads((ZIPDIR / "_manifest.json").read_text())
    by = {}
    for m in man:
        by.setdefault(m["folder"], m)
    out = ["# Third-party notices", "",
           "The skill zips in `claude-ai-skills/` repackage files from these projects without modification.",
           "Each zip carries its project's license file. Install scripts fetch code directly from upstream.", "",
           "| Folder | Project | License | Commit |", "|---|---|---|---|"]
    for it in c["items"]:
        z = it.get("zip")
        if not z or z["folder"] not in by:
            continue
        m = by[z["folder"]]
        out.append(f"| {z['folder']} | [{it['repo']}](https://github.com/{it['repo']}) | {m['license']} | "
                   f"[{m['commit'][:10]}](https://github.com/{it['repo']}/tree/{m['commit']}) |")
    (ROOT / "THIRD_PARTY_NOTICES.md").write_text("\n".join(out) + "\n")


def cmd_render(argv):
    c = load()
    render_scripts(c)
    render_guide(c)
    render_readme(c)
    render_notices(c)
    log("rendered install.sh, verify.sh, guide/index.html, README.md status, THIRD_PARTY_NOTICES.md")


# ---------- report ----------
def cmd_report(argv):
    c, r = load(), run_state()
    BUILD.mkdir(exist_ok=True)
    by = {str(i["n"]): i for i in c["items"]}
    ups = []
    for n, ch in sorted(r["changed"].items(), key=lambda kv: int(kv[0])):
        it = by[n]
        link = (f"https://github.com/{it['repo']}/compare/{ch['old']}...{ch['new']}" if ch.get("old")
                else f"https://github.com/{it['repo']}/commit/{ch['new']}")
        ups.append(f"- {it['name']}: [{(ch.get('old') or 'none')[:7]} → {ch['new'][:7]}]({link})")
    smoke = r.get("smoke", {})
    body = []
    if ups:
        body += ["**Upstream updates**", *ups, ""]
    if r["notes"]:
        body += ["**Notes**", *[f"- {n}" for n in r["notes"]], ""]
    if smoke:
        fails = [by[n]["name"] for n, v in smoke.items() if v != "pass"]
        body.append(f"**Install tests**: {len(smoke) - len(fails)}/{len(smoke)} passed"
                    + (f" (failed: {', '.join(fails)})" if fails else ""))
    if not body:
        body = ["No upstream changes."]
    entry = f"## {TODAY}\n\n" + "\n".join(body).strip() + "\n"
    cl = ROOT / "CHANGELOG.md"
    old = cl.read_text() if cl.exists() else "# Changelog\n\nWritten by the daily refresh workflow.\n"
    head, _, rest = old.partition("\n## ")
    if f"## {TODAY}\n" in old:  # same-day rerun: replace today's entry
        rest = re.sub(rf"^{TODAY}\n.*?(?=^\d{{4}}-\d\d-\d\d\n|\Z)", "", rest, flags=re.S | re.M)
    cl.write_text(head.rstrip() + "\n\n" + entry + ("\n## " + rest if rest.strip() else ""))
    title = (f"Refresh {TODAY}: {len(ups)} upstream update(s)"
             + (f", {sum(1 for v in smoke.values() if v != 'pass')} failing install test(s)" if smoke else ""))
    (BUILD / "commit-msg.txt").write_text(title + "\n\n" + "\n".join(body) + "\n")
    att = [i for i in c["items"] if i.get("problems")]
    issue = ["These plugins need a look. This issue is updated by the daily refresh and closes itself when all are fixed.", ""]
    for it in att:
        issue.append(f"### {it['n']}. {it['name']} — [{it['repo']}](https://github.com/{it['repo']})")
        issue += [f"- **{p['kind']}**: {p['msg']}" for p in it["problems"]]
        issue.append("")
    issue.append("Fix by editing `catalog.json` (install commands, repo, notes), then `python3 scripts/kit.py render`.")
    (BUILD / "issue.md").write_text("\n".join(issue))
    (BUILD / "attention-count").write_text(str(len(att)))
    fresh = [n for n in r["notes"] if n.startswith("⚠")]
    (BUILD / "new-problems.md").write_text(
        ("New problems found in the " + TODAY + " refresh:\n\n" + "\n".join(f"- {n[2:]}" for n in fresh) + "\n") if fresh else "")
    log(title)
    log(f"{len(att)} item(s) need attention")


def cmd_validate(argv):
    """Consistency checks for CI: catalog fields, submodule pins, zips, generated files."""
    c, errs = load(), []
    need = {"n", "row", "name", "repo", "what", "needs", "install", "verify", "use", "always_on", "note",
            "source", "status", "problems", "verified", "upstream"}
    pins = pinned()
    if [i["n"] for i in c["items"]] != list(range(1, len(c["items"]) + 1)):
        errs.append("items must be numbered 1..N in order")
    for it in c["items"]:
        miss = need - it.keys()
        if miss:
            errs.append(f"{it.get('n')}: missing {sorted(miss)}")
        if it.get("source") not in pins:
            errs.append(f"{it['n']}: {it.get('source')} is not a pinned submodule")
        if str(it.get("row")) not in c["rows"]:
            errs.append(f"{it['n']}: unknown row {it.get('row')}")
    man = json.loads((ZIPDIR / "_manifest.json").read_text())
    for m in man:
        zp = ZIPDIR / m["folder"] / f"{m['skill']}.zip"
        if not zp.is_file():
            errs.append(f"manifest lists missing {zp.relative_to(ROOT)}")
            continue
        names = zipfile.ZipFile(zp).namelist()
        if {x.split("/")[0] for x in names} != {m["skill"]} or f"{m['skill']}/SKILL.md" not in names:
            errs.append(f"{zp.name}: must hold one folder '{m['skill']}/' with SKILL.md")
        if not any(x.split("/", 1)[1].upper().startswith(("LICENSE", "COPYING")) for x in names if "/" in x):
            errs.append(f"{zp.name}: no license file inside")
    listed = {(m["folder"], m["skill"]) for m in man}
    for zp in ZIPDIR.glob("*/*.zip"):
        if (zp.parent.name, zp.stem) not in listed:
            errs.append(f"{zp.relative_to(ROOT)} is not in _manifest.json")
    for e in errs:
        log("ERROR", e)
    log(f"validate: {len(c['items'])} items, {len(man)} zips, {len(errs)} error(s)")
    sys.exit(1 if errs else 0)


STEPS = {"check": cmd_check, "bump": cmd_bump, "pack": cmd_pack, "costs": cmd_costs,
         "smoke": cmd_smoke, "render": cmd_render, "report": cmd_report, "validate": cmd_validate}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in STEPS:
        print(__doc__)
        sys.exit(2)
    STEPS[sys.argv[1]](sys.argv[2:])
