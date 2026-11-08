"""snf_pa.paths: MIMIC_RAW_DIR resolution, .csv / .csv.gz lookup. Uses temp folders only."""
import pytest

from snf_pa import paths


@pytest.fixture()
def raw(tmp_path, monkeypatch):
    root = tmp_path / "raw data"
    (root / "mimiciv-3.1" / "hosp").mkdir(parents=True)
    monkeypatch.setenv("MIMIC_RAW_DIR", str(root))
    return root / "mimiciv-3.1" / "hosp"


def test_only_csv(raw):
    (raw / "admissions.csv").write_text("x")
    assert paths.raw_table("mimiciv-3.1/hosp/admissions") == raw / "admissions.csv"


def test_only_csv_gz(raw):
    (raw / "admissions.csv.gz").write_bytes(b"x")
    assert paths.raw_table("mimiciv-3.1/hosp/admissions") == raw / "admissions.csv.gz"


def test_both_prefers_csv(raw):
    (raw / "admissions.csv").write_text("x")
    (raw / "admissions.csv.gz").write_bytes(b"x")
    assert paths.raw_table("mimiciv-3.1/hosp/admissions") == raw / "admissions.csv"


def test_missing_table_raises(raw):
    with pytest.raises(FileNotFoundError):
        paths.raw_table("mimiciv-3.1/hosp/admissions")


def test_unset_env_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("MIMIC_RAW_DIR", "")
    monkeypatch.setattr(paths, "ROOT", tmp_path)  # no .env there to fall back on
    with pytest.raises(RuntimeError):
        paths.raw_dir()


def test_nonexistent_root_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("MIMIC_RAW_DIR", str(tmp_path / "nope"))
    with pytest.raises(FileNotFoundError):
        paths.raw_dir()
