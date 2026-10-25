# Build scripts

How the kit was produced. `catalog.json` at the repo root is the single source of truth.

| Script | What it does |
|---|---|
| `gen_scripts.py` | Regenerates `install.sh` and `verify.sh` from `catalog.json`. Run: `python3 scripts/gen_scripts.py .` |
| `pack_claude_ai.py` | Rebuilds the Claude app skill zips. Run: `python3 scripts/pack_claude_ai.py <dir-with-cloned-repos> claude-ai-skills` (clone with `git submodule update --init` first, then point it at `sources/` after renaming, or at your own clone folder). |
| `install_all.sh` | Test harness used on 2026-10-24: adds every repo's local marketplace and installs each plugin in an isolated HOME, writing results.tsv. Paths inside are from the build workspace; edit `R`, `S` and `HOME` before reusing. |
| `repos.txt` | Number, row, name, GitHub repo and local folder for all 30. |

`guide/index.html` is the published field guide; `guide/template.html` is its source (the catalog is injected at `/*CATALOG*/null`).

`sources/` pins each upstream repo as a git submodule at the commit that was tested. Fetch them with:

```bash
git submodule update --init --depth 1            # all 30 (~1.5 GB)
git submodule update --init --depth 1 sources/30-i-have-adhd   # just one
```
