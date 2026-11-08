"""Frozen protected files must not change (CLAUDE.md hard rule 7). Manifest: data/PROTECTED.sha256."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("freeze", ROOT / "tools" / "freeze.py")
freeze = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(freeze)

ENTRIES = freeze.read_manifest()


def test_manifest_exists_and_is_not_empty():
    assert freeze.MANIFEST.exists()
    assert ENTRIES, "data/PROTECTED.sha256 has no entries"


@pytest.mark.parametrize("rel", sorted(ENTRIES))
def test_frozen_file_unchanged(rel):
    f = ROOT / rel
    assert f.is_file(), f"frozen file is missing: {rel}"
    assert freeze.file_hash(f) == ENTRIES[rel], (
        f"{rel} changed after it was frozen. Protected files may only change with the user's approval; "
        "the user then re-runs tools/freeze.py.")
