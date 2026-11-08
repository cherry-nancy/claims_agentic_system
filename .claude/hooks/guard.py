"""PreToolUse guard for the SNF PA repo (CLAUDE.md hard rules 1, 3, 7 and the git rules).

Reads the hook payload on stdin. Exit 0 = allow; exit 2 + stderr = deny (Claude sees the reason);
a JSON permissionDecision "ask" on stdout = ask the user.

This is a guard against mistakes, not a security boundary: it only sees file paths of Edit/Write and the
text of shell commands, never what a script does inside. The real protection is the OS ACL on the raw
data folder (L0) and the hash check in tests/test_protected_files.py (L3).

Stdlib only, so it runs on any Python >= 3.9 without the project venv (settings.json falls back to
`uv run --no-project python` when .venv is missing, and blocks the tool call if the guard cannot run).
An unexpected error inside the guard also blocks (fail closed). Escape hatch for the user only: start the
session with SNF_PA_GUARD_OFF=1.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2])

# Repo-relative, forward slashes, lower case. Existing files here may not be modified, moved or deleted;
# new files may be created (step 2 has to write the splits once).
PROTECTED_DIRS = (
    "data/splits/",
    "data/synthetic/",
    "data/gold/",
    "knowledge/retrieval_eval/",
    "tests/expected/",
)
PROTECTED_FILES = ("data/protected.sha256",)
# Edits allowed only with the user's per-edit approval (CLAUDE.md: never change the design doc on your own).
ASK_FILES = ("plan/snf_pa_consensus_work_plan_1025.md",)
TEST_GOLD = "data/gold/test"
ALLOW_ENV = "SNF_PA_ALLOW_PROTECTED"
OFF_ENV = "SNF_PA_GUARD_OFF"
# Verbs that wipe whole trees: a parent folder of a protected dir (".", "data", "*") is enough to hit it.
TREE_VERBS = ("rm", "rmdir", "rd", "del", "erase", "remove-item", "ri")
CD_VERBS = ("cd", "pushd", "set-location", "sl", "chdir", "push-location")

# Shell words that change files. Matched as whole words, case-insensitive (PowerShell cmdlets are too).
WRITE_VERBS = (
    "rm", "rmdir", "del", "erase", "mv", "move", "ren", "rename", "cp", "xcopy", "robocopy",
    "touch", "mkdir", "md", "tee", "truncate", "chmod", "chown", "ln", "dd", "shred",
    "icacls", "attrib", "takeown", "cacls",
    "remove-item", "move-item", "rename-item", "copy-item", "new-item", "set-content", "add-content",
    "out-file", "clear-content", "set-acl", "set-itemproperty", "expand-archive", "compress-archive",
    "ri", "mi", "rni", "cpi", "ni", "sc", "ac",
)
# Archive tools write next to the input unless told to stream to stdout.
ARCHIVE_VERBS = ("gzip", "gunzip", "unzip", "tar", "7z")
GIT_WRITE_SUB = ("checkout", "restore", "rm", "mv", "reset", "clean", "stash", "apply", "am", "revert")


def norm(p: str) -> str:
    """Lower-case, forward slashes, Git Bash /d/... -> d:/..., no trailing slash duplication."""
    p = p.strip().strip("'\"").replace("\\", "/").lower()
    # Git Bash drive paths anywhere in the text: /d/x -> d:/x (start of string or after space/quote/=/( )
    p = re.sub(r"(^|[\s\"'=(])/([a-z])/", r"\1\2:/", p)
    p = re.sub(r"(?<!:)/{2,}", "/", p)
    return p


def raw_dir() -> str | None:
    val = os.environ.get("MIMIC_RAW_DIR")
    env = ROOT / ".env"
    if not val and env.exists():
        for line in env.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line.startswith("MIMIC_RAW_DIR="):
                val = line.split("=", 1)[1].strip().strip("'\"")
    if not val:
        return None
    return norm(val).rstrip("/") + "/"


def rel_to_root(path: str) -> str | None:
    """Repo-relative normalized path, or None if outside the repo."""
    p = norm(path)
    root = norm(str(ROOT)).rstrip("/") + "/"
    if p.startswith(root):
        return p[len(root):]
    if re.match(r"^[a-z]:/", p) or p.startswith("/"):
        return None
    return p[2:] if p.startswith("./") else p


def is_protected(rel: str) -> bool:
    return rel.startswith(PROTECTED_DIRS) or rel in PROTECTED_FILES


def deny(msg: str) -> None:
    print(f"[guard] BLOCKED: {msg}", file=sys.stderr)
    sys.exit(2)


def ask(msg: str) -> None:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "ask",
        "permissionDecisionReason": f"[guard] {msg}"}}))
    sys.exit(0)


# ---------------------------------------------------------------- file tools

def check_file_tool(tool: str, ti: dict) -> None:
    path = ti.get("file_path") or ti.get("notebook_path") or ti.get("path") or ""
    raw = raw_dir()
    p = norm(path)
    if tool in ("Edit", "Write", "NotebookEdit", "MultiEdit"):
        if not path:
            return
        if raw and p.startswith(raw):
            deny(f"{path} is inside MIMIC_RAW_DIR, which is read-only (CLAUDE.md hard rule 1). "
                 "Write derived data under data/ instead.")
        rel = rel_to_root(path)
        if rel is None:
            return
        if rel in ASK_FILES:
            ask(f"{rel} is the design document. CLAUDE.md: edit its body only after the user agrees.")
        if is_protected(rel):
            # existence on the real (case-preserved) path, not the lower-cased one
            real = Path(path) if Path(path).is_absolute() else ROOT / path
            if real.exists() and os.environ.get(ALLOW_ENV) != "1":
                deny(f"{rel} is a protected file (CLAUDE.md hard rule 7) and already exists. "
                     "Stop and explain to the user why it needs to change; the user edits it, or starts "
                     f"the session with {ALLOW_ENV}=1.")
    else:  # Read / Grep / Glob
        for val in (path, ti.get("pattern", ""), ti.get("glob", "")):
            rel = rel_to_root(val) if val else None
            if rel is not None and TEST_GOLD in rel:
                deny("test-gold may not be read during development (CLAUDE.md hard rule 3).")


def protected_has_files(prot: str) -> bool:
    d = ROOT / prot
    if prot.endswith("/"):
        return d.is_dir() and any(f.is_file() for f in d.rglob("*"))
    return any(f.name.lower() == Path(prot).name for f in d.parent.glob("*"))


def path_tokens(seg: str) -> list[str]:
    toks = [t.strip("'\"") for t in re.findall(r"\"[^\"]*\"|'[^']*'|\S+", seg)]
    return [t for t in toks if t and not t.startswith("-")]


# ---------------------------------------------------------------- shell tools

SEG_SPLIT = re.compile(r"\|\||&&|;|\n|\|(?!\|)")


def words(seg: str) -> list[str]:
    return re.findall(r"[a-z0-9_.\-]+", seg.lower())


def redirect_targets(seg: str) -> list[str]:
    out = []
    for m in re.finditer(r"(?<![0-9&])\d?>>?\s*(\"[^\"]*\"|'[^']*'|[^\s;&|]+)", seg):
        out.append(m.group(1))
    for m in re.finditer(r"-(?:filepath|path|literalpath|destination)\s+(\"[^\"]*\"|'[^']*'|[^\s;&|]+)",
                         seg, re.I):
        out.append(m.group(1))
    return out


def segment_writes(seg: str) -> bool:
    w = words(seg)
    if any(v in w for v in WRITE_VERBS):
        return True
    if "sed" in w and re.search(r"\bsed\b[^|;&]*\s-i", seg):
        return True
    # streaming / listing flags (also combined, e.g. gzip -dc, unzip -l, tar -tzf) do not write files
    if any(v in w for v in ARCHIVE_VERBS) and not re.search(r"\s(-[a-z]*[clt][a-z]*|--stdout|--list)\b", seg):
        return True
    if "git" in w:
        i = w.index("git")
        if any(s in w[i + 1:] for s in GIT_WRITE_SUB):
            return True
    return False


def mentions(seg_norm: str, target: str) -> bool:
    return target in seg_norm


def current_branch() -> str:
    try:
        return subprocess.run(["git", "-C", str(ROOT), "branch", "--show-current"], capture_output=True,
                              text=True, timeout=5).stdout.strip()
    except Exception:
        return ""


def check_git(cmd: str) -> None:
    for seg in SEG_SPLIT.split(cmd):
        toks = seg.split()
        if "git" not in toks:
            continue
        i = toks.index("git")
        rest = [t for t in toks[i + 1:]]
        # skip global options like -C dir, -c k=v
        while rest and rest[0].startswith("-"):
            rest = rest[2:] if rest[0] in ("-C", "-c") else rest[1:]
        if not rest:
            continue
        sub, args = rest[0], rest[1:]
        if sub == "commit":
            br = current_branch()
            if not br.startswith("zhijie-"):
                deny(f"commits are only allowed on zhijie-* branches; current branch is '{br or '?'}'.")
            if "--no-verify" in args:
                deny("--no-verify is not allowed.")
        elif sub == "reset" and "--hard" in args and os.environ.get(ALLOW_ENV) != "1":
            refs = [a for a in args if not a.startswith("-") and a != "HEAD"]
            if refs and any(protected_has_files(p) for p in PROTECTED_DIRS):
                deny("git reset --hard to another commit could overwrite protected files "
                     "(CLAUDE.md hard rule 7); ask the user.")
        elif sub == "push":
            if any(a in ("-f", "--force", "--force-with-lease", "--mirror", "--all", "--delete", "-d")
                   or a.startswith("--force") for a in args):
                deny("force / mirror / delete pushes are not allowed.")
            refs = [a for a in args if not a.startswith("-")]
            targets = refs[1:] if len(refs) >= 2 else [current_branch()]
            for t in targets:
                if t.startswith("+"):
                    deny("force refspecs (+ref) are not allowed.")
                dst = t.split(":")[-1].removeprefix("refs/heads/")
                if dst == "HEAD":
                    dst = current_branch()
                if not dst.startswith("zhijie-"):
                    deny(f"push target '{dst}' is not a zhijie-* branch (teammate branches are read-only).")


def git_writes(w: list[str]) -> bool:
    return "git" in w and any(s in w[w.index("git") + 1:] for s in GIT_WRITE_SUB)


def is_parent_of(token: str, rel: str) -> bool:
    """token names the repo root, a glob at the root, or a folder above the protected path rel."""
    tr = rel_to_root(token)
    if tr is None:
        return False
    tr = tr.rstrip("/")
    return tr in ("", ".", "*", "./*") or rel.startswith(tr + "/")


def check_shell(cmd: str) -> None:
    raw = raw_dir()
    rawp = raw.rstrip("/") if raw else None
    cmd_norm = norm(cmd)  # whole command, normalized for path matching
    allow_prot = os.environ.get(ALLOW_ENV) == "1"
    in_raw = False  # a previous `cd` in this command moved into the raw folder
    for seg in SEG_SPLIT.split(cmd):
        seg_n = norm(seg)
        w = words(seg)
        toks = path_tokens(seg)
        writes = segment_writes(seg)
        if w and w[0] in CD_VERBS:
            tgt = norm(toks[1]) if len(toks) > 1 else ""
            in_raw = bool(rawp) and tgt.startswith(rawp)
            continue
        if rawp:
            targets = [norm(t) for t in redirect_targets(seg)]
            here = rawp in seg_n or in_raw
            if (here and (writes or "git" in w)) or any(t.startswith(rawp) for t in targets) \
                    or (in_raw and targets):
                deny("this command would modify MIMIC_RAW_DIR, which is read-only (CLAUDE.md hard rule 1).")
        if not allow_prot:
            tree = any(v in w for v in TREE_VERBS) or git_writes(w)
            for rel in PROTECTED_DIRS + PROTECTED_FILES:
                r = rel.rstrip("/")
                targets = [rel_to_root(t) or "" for t in redirect_targets(seg)]
                if (r in seg_n and writes) or any(t.startswith(r) for t in targets):
                    # step-2 scripts write splits from Python, which this guard does not see.
                    deny(f"this command would change protected path {r} (CLAUDE.md hard rule 7).")
                if tree and protected_has_files(rel):
                    for t in toks:
                        if is_parent_of(t, rel):
                            deny(f"'{t}' contains the protected path {r}, which has files; this command "
                                 "could overwrite or delete them (CLAUDE.md hard rule 7). Name the paths "
                                 "you mean explicitly.")
        for rel in ASK_FILES:
            if mentions(seg_n, rel) and writes:
                ask(f"this command changes the design document {rel}; needs the user's approval.")
    if TEST_GOLD in cmd_norm:
        deny("test-gold may not be read during development (CLAUDE.md hard rule 3).")
    if re.search(r"--split[= ]+test\b", cmd_norm) or re.search(r"snf-pa\s+eval\b.*\btest\b", cmd_norm):
        deny("runs on the test split are started by the user only (CLAUDE.md hard rule 3).")
    if runs_freeze(cmd_norm):
        deny("only the user freezes protected files (the user runs tools/freeze.py).")
    check_git(cmd)


def runs_freeze(cmd_norm: str) -> bool:
    """True if a segment executes tools/freeze.py (not when it only reads, stages or diffs it)."""
    for seg in SEG_SPLIT.split(cmd_norm):
        toks = [t.strip("'\"") for t in seg.split()]
        for i, t in enumerate(toks):
            if not t.endswith("tools/freeze.py"):
                continue
            prev = [x for x in toks[:i] if not x.startswith("-")]
            if not prev:  # executed directly: ./tools/freeze.py
                return True
            last = prev[-1].rsplit("/", 1)[-1]
            if re.fullmatch(r"py|python[0-9.]*(\.exe)?", last) or (last == "run" and "uv" in prev):
                return True
    return False


def main() -> None:
    if os.environ.get(OFF_ENV) == "1":
        return
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return  # not a hook payload; nothing to check
    try:
        tool = payload.get("tool_name", "")
        ti = payload.get("tool_input") or {}
        if tool in ("Bash", "PowerShell"):
            check_shell(ti.get("command", ""))
        elif tool in ("Edit", "Write", "NotebookEdit", "MultiEdit", "Read", "Grep", "Glob"):
            check_file_tool(tool, ti)
    except Exception as e:  # fail closed
        deny(f"guard error ({type(e).__name__}: {e}). The user can fix .claude/hooks/guard.py or start "
             f"the session with {OFF_ENV}=1.")


if __name__ == "__main__":
    main()
