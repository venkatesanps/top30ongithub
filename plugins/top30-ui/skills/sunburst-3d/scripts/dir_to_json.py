#!/usr/bin/env python3
"""Scan a folder into the JSON tree the sunburst draws: {name, size, children}.

  dir_to_json.py PATH [--depth 5] [--top 40] [--min-size 1MB] [--apparent] [-o tree.json]

Sizes are bytes on disk (allocated blocks) unless --apparent. Symlinks are not followed and
other mounted volumes are not entered. Below --depth, a folder is one leaf with its total size.
In each folder only the --top largest entries are kept; the rest, and anything under
--min-size, are summed into one "(N smaller items)" leaf, so the file stays small. Unreadable
folders are counted as empty and listed on stderr. Nothing leaves this machine. Standard library.
"""
import argparse
import json
import os
import stat
import sys
from pathlib import Path

UNITS = {"B": 1, "KB": 1e3, "MB": 1e6, "GB": 1e9, "TB": 1e12}


def parse_size(s):
    s = s.strip().upper().replace(" ", "")
    for u in sorted(UNITS, key=len, reverse=True):
        if s.endswith(u):
            return int(float(s[: -len(u)]) * UNITS[u])
    return int(float(s))


def file_size(st, apparent):
    if apparent or not hasattr(st, "st_blocks"):
        return st.st_size
    return st.st_blocks * 512


def scan(path, depth, a, dev, errors):
    """(node, total) for a folder; files and folders below the depth limit become leaves."""
    items, total = [], 0
    try:
        entries = list(os.scandir(path))
    except OSError as e:
        errors.append(f"{path}: {e.strerror or e}")
        entries = []
    for e in entries:
        try:
            st = e.stat(follow_symlinks=False)
        except OSError as err:
            errors.append(f"{e.path}: {err.strerror or err}")
            continue
        if stat.S_ISLNK(st.st_mode):
            continue
        if stat.S_ISDIR(st.st_mode):
            if st.st_dev != dev:
                continue  # another volume mounted inside
            child, size = scan(e.path, depth - 1, a, dev, errors)
            if depth <= 1:
                child = {"name": e.name, "size": size}
        else:
            size = file_size(st, a.apparent)
            child = {"name": e.name, "size": size}
        total += size
        if size > 0:
            items.append((size, child))
    items.sort(key=lambda sc: sc[0], reverse=True)
    keep = [c for s, c in items[: a.top] if s >= a.min_size]
    rest = items[len(keep):]
    if rest:
        keep.append({"name": f"({len(rest)} smaller item{'s' if len(rest) != 1 else ''})", "size": sum(s for s, _ in rest)})
    node = {"name": os.path.basename(os.path.normpath(path)) or str(path)}
    if keep:
        node["children"] = keep
    else:
        node["size"] = total
    return node, total


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("path")
    ap.add_argument("--depth", type=int, default=5, help="folder levels to keep as branches (default 5)")
    ap.add_argument("--top", type=int, default=40, help="largest entries kept per folder (default 40)")
    ap.add_argument("--min-size", type=parse_size, default=parse_size("1MB"), help="smaller entries are merged (default 1MB)")
    ap.add_argument("--apparent", action="store_true", help="file length instead of space on disk")
    ap.add_argument("--name", help="label for the root (default: the folder's name)")
    ap.add_argument("-o", "--out", help="write here instead of stdout")
    a = ap.parse_args(argv)
    root = Path(a.path).expanduser()
    if not root.is_dir():
        sys.exit(f"not a folder: {root}")
    errors = []
    tree, total = scan(str(root), max(1, a.depth), a, root.stat().st_dev, errors)
    if a.name:
        tree["name"] = a.name
    text = json.dumps(tree, separators=(",", ":"))
    if a.out:
        Path(a.out).write_text(text + "\n", encoding="utf-8")
        print(f"wrote {a.out}: {total / 1e9:.2f} GB, {len(text) // 1024} KB of JSON", file=sys.stderr)
    else:
        print(text)
    if errors:
        print(f"{len(errors)} item(s) couldn't be read, counted as empty:", file=sys.stderr)
        for e in errors[:10]:
            print("  " + e, file=sys.stderr)


if __name__ == "__main__":
    main()
