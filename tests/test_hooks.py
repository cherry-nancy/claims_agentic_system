"""Tests for .claude/hooks/guard.py, run against a throwaway fake repo and fake raw-data folder.

The real MIMIC_RAW_DIR is never touched: every case points MIMIC_RAW_DIR at a temp folder.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

GUARD = Path(os.environ.get("SNF_PA_GUARD_UNDER_TEST")
             or Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "guard.py")


@pytest.fixture()
def repo(tmp_path):
    root = tmp_path / "repo"
    raw = tmp_path / "raw data"  # space on purpose, like "D:/project data/mimiciv"
    (raw / "mimiciv-3.1" / "hosp").mkdir(parents=True)
    (raw / "mimiciv-3.1" / "hosp" / "admissions.csv.gz").write_bytes(b"x")
    (root / "data" / "splits").mkdir(parents=True)
    (root / "data" / "splits" / "test.csv").write_text("subject_id\n1\n")        # frozen
    (root / "data" / "splits" / "draft_cases.csv").write_text("hadm_id\n1\n")    # protected, not frozen
    (root / "data" / "PROTECTED.sha256").write_text("# manifest\n" + "0" * 64 + "  data/splits/test.csv\n")
    (root / "plan").mkdir()
    (root / "plan" / "snf_pa_consensus_work_plan_1025.md").write_text("doc\n")
    (root / ".env").write_text(f"MIMIC_RAW_DIR={raw.as_posix()}\n")
    subprocess.run(["git", "init", "-q", "-b", "zhijie-test", str(root)], check=True)
    return root, raw


def run(root: Path, payload: dict, **env):
    e = {k: v for k, v in os.environ.items()
         if k not in ("MIMIC_RAW_DIR", "SNF_PA_ALLOW_PROTECTED", "SNF_PA_GUARD_OFF")}
    e.update(CLAUDE_PROJECT_DIR=str(root), **env)
    r = subprocess.run([sys.executable, str(GUARD)], input=json.dumps(payload), capture_output=True,
                       text=True, env=e)
    if r.returncode == 2:
        return "deny"
    if '"permissionDecision": "ask"' in r.stdout:
        return "ask"
    assert r.returncode == 0, r.stderr
    return "allow"


def bash(cmd):
    return {"tool_name": "Bash", "tool_input": {"command": cmd}}


def ps(cmd):
    return {"tool_name": "PowerShell", "tool_input": {"command": cmd}}


def edit(path, tool="Edit"):
    return {"tool_name": tool, "tool_input": {"file_path": str(path)}}


def git_bash_path(p: Path) -> str:
    s = p.as_posix()
    return f"/{s[0].lower()}{s[2:]}" if s[1:2] == ":" else s


# ---- raw data folder (hard rule 1)

def test_raw_read_allowed(repo):
    root, raw = repo
    f = (raw / "mimiciv-3.1/hosp/admissions.csv.gz").as_posix()
    assert run(root, bash(f'ls "{raw.as_posix()}"')) == "allow"
    assert run(root, bash(f"""uv run python -c "import duckdb; duckdb.sql(\\"select 1 from read_csv('{f}')\\")" > traces/out.txt""")) == "allow"
    assert run(root, bash(f'gzip -dc "{f}" | head')) == "allow"
    assert run(root, ps(f'Get-ChildItem "{raw}"')) == "allow"


@pytest.mark.parametrize("cmd", [
    'rm "{f}"',
    'mv "{f}" /tmp/x',
    'echo hi > "{d}/new.txt"',
    'touch "{d}/new.txt"',
    'gunzip -k "{f}"',
    'sed -i s/a/b/ "{f}"',
])
def test_raw_write_denied_bash(repo, cmd):
    root, raw = repo
    f = (raw / "mimiciv-3.1/hosp/admissions.csv.gz").as_posix()
    assert run(root, bash(cmd.format(f=f, d=raw.as_posix()))) == "deny"


def test_raw_write_denied_git_bash_and_backslash_spelling(repo):
    root, raw = repo
    assert run(root, bash(f'rm -r "{git_bash_path(raw)}/mimiciv-3.1"')) == "deny"
    assert run(root, ps(f'Remove-Item "{raw}\\mimiciv-3.1" -Recurse')) == "deny"
    assert run(root, ps(f'Set-Content -Path "{raw}\\x.txt" -Value 1')) == "deny"


def test_raw_write_denied_file_tools(repo):
    root, raw = repo
    assert run(root, edit(raw / "new.txt", "Write")) == "deny"
    assert run(root, edit(str(raw / "mimiciv-3.1" / "hosp" / "admissions.csv.gz").replace("/", "\\"))) == "deny"


# ---- protected files (hard rule 7)

def test_protected_existing_file_denied(repo):
    root, _ = repo
    assert run(root, edit(root / "data/splits/test.csv")) == "deny"
    assert run(root, edit(root / "data/splits/test.csv", "Write")) == "deny"
    assert run(root, bash("rm data/splits/test.csv")) == "deny"
    assert run(root, bash("echo 2 >> data/splits/test.csv")) == "deny"
    assert run(root, bash("git checkout -- data/splits/test.csv")) == "deny"


def test_unfrozen_protected_file_asks(repo):
    root, _ = repo
    assert run(root, edit(root / "data/splits/draft_cases.csv")) == "ask"
    assert run(root, edit(root / "data/splits/draft_cases.csv", "Write")) == "ask"
    assert run(root, bash("rm data/splits/draft_cases.csv")) == "ask"
    # one frozen file in the same command is enough to deny
    assert run(root, bash("rm data/splits/draft_cases.csv data/splits/test.csv")) == "deny"
    assert run(root, bash("rm data/splits/*")) == "deny"
    # the manifest itself is always frozen
    assert run(root, edit(root / "data/PROTECTED.sha256")) == "deny"


def test_protected_new_file_and_reads_allowed(repo):
    root, _ = repo
    assert run(root, edit(root / "data/splits/dev.csv", "Write")) == "allow"
    assert run(root, bash("cat data/splits/test.csv")) == "allow"
    assert run(root, bash("git add data/splits/test.csv")) == "allow"
    assert run(root, bash("git diff data/splits/")) == "allow"


def test_protected_override_env(repo):
    root, _ = repo
    assert run(root, edit(root / "data/splits/test.csv"), SNF_PA_ALLOW_PROTECTED="1") == "allow"


def test_design_doc_asks(repo):
    root, _ = repo
    assert run(root, edit(root / "plan/snf_pa_consensus_work_plan_1025.md")) == "ask"
    assert run(root, bash("cat plan/snf_pa_consensus_work_plan_1025.md")) == "allow"


def test_freeze_needs_user_approval(repo):
    root, _ = repo
    # running the freeze tool always goes to the user's permission prompt
    assert run(root, bash("uv run python tools/freeze.py data/splits/test.csv")) == "ask"
    assert run(root, bash(".venv/Scripts/python.exe tools/freeze.py x")) == "ask"
    assert run(root, bash("uv run tools/freeze.py x")) == "ask"
    assert run(root, bash("./tools/freeze.py x")) == "ask"
    # reading, staging, diffing the tool needs no approval
    assert run(root, bash("cat tools/freeze.py")) == "allow"
    assert run(root, bash("git add tools/freeze.py tests/test_hooks.py")) == "allow"
    assert run(root, bash("git add src/snf_pa/paths.py tools/freeze.py data/PROTECTED.sha256")) == "allow"
    # other rules still win: a forbidden push in the same command is denied, not asked
    assert run(root, bash("uv run python tools/freeze.py x && git push origin cfeng")) == "deny"
    assert run(root, bash("git diff -- tools/freeze.py")) == "allow"


@pytest.mark.parametrize("cmd", [
    "git checkout origin/cfeng -- data/",
    "git checkout origin/cfeng -- data",
    "git restore .",
    "git checkout -- .",
    "rm -rf data",
    "rm -rf *",
    "git reset --hard origin/cfeng",
])
def test_parent_folder_of_protected_denied(repo, cmd):
    root, _ = repo
    assert run(root, bash(cmd)) == "deny"


def test_parent_folder_allowed_when_protected_dirs_empty(tmp_path):
    root = tmp_path / "empty"
    (root / "data").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "zhijie-test", str(root)], check=True)
    assert run(root, bash("git checkout origin/cfeng -- data/")) == "allow"
    assert run(root, bash("git reset --hard origin/zhijie-test")) == "allow"


def test_teammate_file_checkout_allowed(repo):
    root, _ = repo
    assert run(root, bash("git checkout origin/cfeng -- src/snf_pa/rag/bm25.py")) == "allow"
    assert run(root, bash("git checkout zhijie-other")) == "allow"


def test_cd_into_raw_then_write_denied(repo):
    root, raw = repo
    assert run(root, bash(f'cd "{raw.as_posix()}" && rm mimiciv-3.1/hosp/admissions.csv.gz')) == "deny"
    assert run(root, bash(f'cd "{raw.as_posix()}" && echo x > new.txt')) == "deny"
    assert run(root, ps(f'Set-Location "{raw}"; Remove-Item x')) == "deny"
    assert run(root, bash(f'cd "{raw.as_posix()}" && ls && cd - && rm -rf traces/tmp')) == "allow"
    assert run(root, bash(f'git -C "{raw.as_posix()}" init')) == "deny"


def test_grep_glob_test_gold_denied(repo):
    root, _ = repo
    assert run(root, {"tool_name": "Grep", "tool_input": {"pattern": "x", "path": str(root / "data/gold/test")}}) == "deny"
    assert run(root, {"tool_name": "Glob", "tool_input": {"pattern": "data/gold/test/**/*.csv"}}) == "deny"
    assert run(root, {"tool_name": "Grep", "tool_input": {"pattern": "x", "path": str(root / "src")}}) == "allow"


def test_guard_off_escape_hatch(repo):
    root, raw = repo
    assert run(root, edit(raw / "x.txt", "Write"), SNF_PA_GUARD_OFF="1") == "allow"


# ---- test isolation (hard rule 3)

def test_test_gold_and_test_split_denied(repo):
    root, _ = repo
    assert run(root, bash("cat data/gold/test/labels.csv")) == "deny"
    assert run(root, {"tool_name": "Read", "tool_input": {"file_path": str(root / "data/gold/test/a.csv")}}) == "deny"
    assert run(root, bash("uv run snf-pa eval --config F --split test")) == "deny"
    assert run(root, bash("uv run snf-pa eval --config F --split dev")) == "allow"


# ---- git rules

def test_git_commit_branch(repo):
    root, _ = repo
    assert run(root, bash('git commit -m "x"')) == "allow"
    assert run(root, bash('git commit --no-verify -m "x"')) == "deny"
    subprocess.run(["git", "-C", str(root), "checkout", "-q", "-b", "cfeng"], check=True)
    assert run(root, bash('git commit -m "x"')) == "deny"


def test_git_push_targets(repo):
    root, _ = repo
    assert run(root, bash("git push origin zhijie-test")) == "allow"
    assert run(root, bash("git push")) == "allow"
    assert run(root, bash("git push -u origin HEAD")) == "allow"
    assert run(root, bash("git push origin cfeng")) == "deny"
    assert run(root, bash("git push origin HEAD:snf-criterion-cards")) == "deny"
    assert run(root, bash("git push --force origin zhijie-test")) == "deny"
    assert run(root, bash("git push origin +zhijie-test")) == "deny"
    # shell redirections are not push targets
    assert run(root, bash("git push -u origin zhijie-test 2>&1 | tail -5")) == "allow"
    assert run(root, bash("git push origin zhijie-test > push.log")) == "allow"
    assert run(root, bash("git push origin cfeng 2>&1")) == "deny"


def test_unrelated_commands_allowed(repo):
    root, _ = repo
    assert run(root, bash("uv run pytest -q")) == "allow"
    assert run(root, edit(root / "src/snf_pa/paths.py", "Write")) == "allow"
    assert run(root, bash("rm -rf traces/tmp")) == "allow"
