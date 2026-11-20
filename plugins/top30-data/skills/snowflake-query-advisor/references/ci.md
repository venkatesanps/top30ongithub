# Running the advisor on every change

The script only reads files. It never connects to Snowflake, so it runs the same way on a laptop,
in a pre-commit hook or on a CI runner. It needs `sqlglot` and Python 3.11 or newer for a TOML config
(a JSON config works on older versions). It is tested on Python 3.12.

Copy `scripts/sf_query_advisor.py` into the repo you want checked, for example as
`tools/sf_query_advisor.py`. A copy you commit is pinned, reviewed and works offline. The examples
below assume that path.

## Options for hooks and CI

| Option | What it does |
|---|---|
| `--brief` | One line per finding on stdout: `path:line: [severity] rule: title (confidence)`. |
| `--fail-on high` | Exit 1 when any finding is at least that severe. Use `high` to start; lower it later. |
| `--changed-only [REF]` | Review only `.sql` files changed against REF's merge base (default `HEAD`), plus untracked files. In GitHub Actions use `origin/${{ github.base_ref }}` with `fetch-depth: 0`. |
| `--sarif FILE` | SARIF 2.1.0 for GitHub code scanning or any SARIF viewer. High findings are errors, medium are warnings, low and info are notes. Each result also carries a fingerprint that ignores line numbers (`sfQueryAdvisor/v1`) for SARIF tools that use one; GitHub's upload step computes its own. |
| `--md FILE` | The full report, with plans and rewrites, as a build artifact. |

Statements the parser can't read show up in `--brief` output as `not-parsed`, so nobody assumes
they were checked.

## Project config

The advisor reads the nearest `.sf-advisor.toml` or `.sf-advisor.json`, searching from the first
path it was given up to the git root. Options on the command line win. `--config FILE` picks a
file and `--no-config` ignores it. See `examples/sf-advisor.toml`:

```toml
[sf-advisor]
disable = ["count-distinct"]          # rules to turn off everywhere
exclude = ["target/*", "legacy/*"]    # globs, relative to the config file's folder
fail_on = "high"
generation = 1                        # warehouses are Gen1 unless you set 2
credit_price = 3.00

[sf-advisor.severity]                 # change a rule's severity
not-in-subquery = "high"
```

An unknown key is an error, so a typo can't silently do nothing.

## Turning a rule off where it's intended

Put a comment in the SQL. `--`, `//`, `/* */` and dbt's `{# #}` comments all work:

```sql
-- sf-advisor: disable-next-line=select-star   small lookup table, every column is used
SELECT * FROM ref.country_codes;

SELECT * FROM ref.currencies;  -- sf-advisor: disable=select-star

-- sf-advisor: disable-file=count-distinct
```

`disable` applies to the line it's on, `disable-next-line` to the line below it, and
`disable-file` to the whole file. With no `=rules`, every rule is turned off for that line. A
finding without a line, such as a measured queueing time, is turned off by a directive anywhere
inside its statement. Turned-off findings are still listed at the end of each statement in the
report, so a review can see what was silenced.

## pre-commit

`examples/pre-commit-config.yaml` sets up a local hook. pre-commit builds a virtualenv with
`sqlglot`, then passes the staged `.sql` files to the script.

## GitHub Actions

`examples/github-action.yml` reviews the SQL changed in a pull request and fails the check on high
findings. It uploads SARIF so findings show on the pull request's changed lines.

- Uploading SARIF needs `security-events: write`.
- Code scanning on a private repository needs GitHub Advanced Security (GitHub Code Security).
  Without it, drop the upload step and keep the `--brief` log and the Markdown artifact.
- SARIF upload sends findings, including short SQL snippets, to GitHub. Use it only for repos
  whose SQL is already hosted there.

## Other CI systems

Use `--brief --fail-on high` for the log and the exit code, and `--md` for a report artifact. The
SARIF file works with any tool that reads SARIF 2.1.0.
