"""Stop hook: before Claude ends a turn, the fast test suite must pass if the working tree changed.

- Skips when the working tree is clean, or unchanged since the last passing run (fingerprint cache).
- Runs `uv run --no-sync pytest -q -m "not slow"`; tests that read big raw tables or call LLMs are
  marked `slow` and are not run here.
- On failure: {"decision": "block", "reason": <tail of pytest output>} so Claude keeps fixing.
- If Claude was already blocked once this turn (stop_hook_active) and tests still fail, the stop is
  allowed but the failure is shown to the user (CLAUDE.md: report failures as they are).
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2])
STATE = ROOT / ".claude" / ".stop_pytest_pass"
IGNORED = ("traces/", "data/derived/", ".claude/.stop_pytest_pass")
TAIL = 40


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=30).stdout


def fingerprint() -> str | None:
    """None when there is nothing changed; otherwise a hash of the current changes."""
    status = [ln for ln in git("status", "--porcelain", "--untracked-files=all").splitlines()
              if not any(ln[3:].strip('"').startswith(p) for p in IGNORED)]
    if not status:
        return None
    h = hashlib.sha256()
    h.update(git("rev-parse", "HEAD").encode())
    h.update(git("diff", "HEAD").encode())
    for ln in status:
        if ln.startswith("??"):
            f = ROOT / ln[3:].strip('"')
            if f.is_file():
                h.update(ln.encode())
                h.update(f.read_bytes())
    return h.hexdigest()


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    fp = fingerprint()
    if fp is None:
        return
    if STATE.exists() and STATE.read_text().strip() == fp:
        return
    try:
        r = subprocess.run(["uv", "run", "--no-sync", "pytest", "-q", "-m", "not slow", "-p", "no:cacheprovider"],
                           cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=280)
        code, out = r.returncode, (r.stdout + r.stderr)
    except subprocess.TimeoutExpired:
        code, out = 1, "pytest timed out after 280 s"
    if code in (0, 5):  # 5 = no tests collected
        STATE.write_text(fp)
        return
    tail = "\n".join(out.strip().splitlines()[-TAIL:])
    if payload.get("stop_hook_active"):
        print(json.dumps({"systemMessage": f"pytest still failing (exit {code}); not verified:\n{tail}"}))
        return
    if "FAILED tests/test_protected_files.py" in out or "FAILED tests\\test_protected_files.py" in out:
        # A frozen file changed. If the user approved the change (e.g. a design-doc edit), the fix is a
        # re-freeze by the user, never reverting the approved edit.
        reason = ("A frozen protected file changed (tests/test_protected_files.py). Do NOT revert a change "
                  "the user approved and do not touch data/PROTECTED.sha256. If the user approved it, stop "
                  "and ask the user to re-run tools/freeze.py on that file; if nobody approved it, report "
                  f"it to the user.\n{tail}")
    else:
        reason = (f"pytest failed (exit {code}). Fix the root cause before finishing "
                  f"(do not edit expected values).\n{tail}")
    print(json.dumps({"decision": "block", "reason": reason}))


if __name__ == "__main__":
    main()
