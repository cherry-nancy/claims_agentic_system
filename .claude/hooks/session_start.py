"""SessionStart hook: print the facts CLAUDE.md asks to confirm before work. Never blocks."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from guard import ROOT, raw_dir  # noqa: E402


def main() -> None:
    br = subprocess.run(["git", "-C", str(ROOT), "branch", "--show-current"], capture_output=True,
                        text=True).stdout.strip()
    lines = [f"[session] repo={ROOT} branch={br or '(detached)'}"]
    if not br.startswith("zhijie-"):
        lines.append("[session] WARNING: not on a zhijie-* branch; confirm the working branch with the user.")
    if not (ROOT / ".env").exists():
        lines.append("[session] WARNING: .env is missing (copy .env.example and set MIMIC_RAW_DIR).")
    raw = raw_dir()
    if not raw:
        lines.append("[session] WARNING: MIMIC_RAW_DIR is not set.")
    elif not Path(raw).exists():
        lines.append(f"[session] WARNING: MIMIC_RAW_DIR={raw} does not exist on this machine.")
    else:
        lines.append(f"[session] MIMIC_RAW_DIR={raw} (read-only)")
    if os.environ.get("SNF_PA_ALLOW_PROTECTED") == "1":
        lines.append("[session] NOTE: SNF_PA_ALLOW_PROTECTED=1, protected-file guard is off for this session.")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
