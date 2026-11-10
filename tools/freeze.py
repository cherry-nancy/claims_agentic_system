"""Freeze protected files: record their sha256 in data/PROTECTED.sha256 (CLAUDE.md hard rule 7).

Run only with the user's sign-off on the file (a split, gold labels, expected results, the design doc).
Claude may start it, but the guard hook routes every run to the user's permission prompt:

    uv run python tools/freeze.py data/splits/test.csv [more paths ...]
    uv run python tools/freeze.py --unfreeze data/splits/test.csv [...]   # remove from the manifest

Unfreezing (user decision 2026-11-09) also needs the user's approval in the prompt; afterwards the file is a
protected-but-unfrozen file (changes still ask the user) until it is frozen again.
tests/test_protected_files.py then fails if any frozen file changes, whatever changed it.
Line endings are normalized (CRLF -> LF) before hashing so the same git content hashes the same
on every machine regardless of core.autocrlf.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "PROTECTED.sha256"


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def read_manifest() -> dict[str, str]:
    if not MANIFEST.exists():
        return {}
    out = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            digest, rel = line.split(None, 1)
            out[rel] = digest
    return out


def main(paths: list[str]) -> None:
    unfreeze = bool(paths) and paths[0] == "--unfreeze"
    paths = paths[1:] if unfreeze else paths
    if not paths:
        sys.exit(__doc__)
    entries = read_manifest()
    if unfreeze:
        for p in paths:
            rel = Path(p).as_posix().lstrip("./")
            if rel == "data/PROTECTED.sha256" or rel not in entries:
                sys.exit(f"not frozen (or not allowed): {rel}")
            del entries[rel]
            print(f"unfrozen  {rel}")
        paths = []
    for p in paths:
        f = (ROOT / p).resolve()
        if not f.is_file():
            sys.exit(f"not a file: {p}")
        rel = f.relative_to(ROOT).as_posix()
        old, new = entries.get(rel), file_hash(f)
        entries[rel] = new
        print(f"{'updated' if old and old != new else 'unchanged' if old else 'added'}  {rel}  {new[:12]}")
    body = "".join(f"{d}  {r}\n" for r, d in sorted(entries.items()))
    MANIFEST.write_text("# sha256 (CRLF->LF normalized) of frozen files; update only via tools/freeze.py\n"
                        + body, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main(sys.argv[1:])
