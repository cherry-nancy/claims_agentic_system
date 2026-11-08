"""Loading a policy index release (snf_pa.rag.index.PolicyIndex.load), on a two-chunk fake release; no Ollama."""
import hashlib
import json

import polars as pl
import pytest

from snf_pa.rag import index

CHUNKS = [
    {"id": "a", "citation": "a", "text": "skilled nursing needed on a daily basis", "tier": 1, "program": "SNF",
     "paragraphs": ["a"]},
    {"id": "b", "citation": "b", "text": "inpatient rehabilitation facility three hours of therapy", "tier": 3,
     "program": "IRF", "paragraphs": ["b"]},
]


@pytest.fixture
def release(tmp_path, monkeypatch):
    monkeypatch.setattr(index, "INDEX", tmp_path)
    monkeypatch.setattr(index, "LATEST", tmp_path / "LATEST")
    monkeypatch.setattr(index, "model_digest", lambda model=index.EMBED_MODEL: "digest-1")
    d = tmp_path / "v1"
    d.mkdir()
    rows = [c | {"text_sha256": hashlib.sha256(c["text"].encode()).hexdigest()} for c in CHUNKS]
    (pl.DataFrame(rows).with_columns(pl.Series("vector", [[1.0, 0.0], [0.0, 1.0]]).cast(pl.Array(pl.Float32, 2)))
     .write_parquet(d / "chunks.parquet"))
    manifest = {"version": "v1", "embedding": {"model": "bge-m3", "ollama_digest": "digest-1", "dim": 2},
                "n_chunks": 2}
    (d / "manifest.json").write_text(json.dumps(manifest))
    (tmp_path / "LATEST").write_text("v1\n")
    return d


def test_load_latest_and_search(release):
    idx = index.PolicyIndex.load()
    assert idx.manifest["version"] == "v1"
    assert [c["id"] for c in idx.chunks] == ["a", "b"]
    assert idx.chunks[0]["paragraphs"] == ["a"]
    assert [c["id"] for c in idx.search("daily skilled nursing", k=1, mode="bm25")] == ["a"]
    assert [c["id"] for c in idx.search("therapy", k=2, mode="bm25", max_tier=2)] == ["a"]


def test_refuses_a_different_embedding_model(release, monkeypatch):
    monkeypatch.setattr(index, "model_digest", lambda model=index.EMBED_MODEL: "digest-2")
    with pytest.raises(RuntimeError, match="rebuild"):
        index.PolicyIndex.load()


def test_refuses_changed_chunk_text(release):
    df = pl.read_parquet(release / "chunks.parquet")
    df.with_columns(pl.col("text").str.replace("daily", "weekly")).write_parquet(release / "chunks.parquet")
    with pytest.raises(RuntimeError, match="corrupt"):
        index.PolicyIndex.load()


def test_no_release_built(tmp_path, monkeypatch):
    monkeypatch.setattr(index, "LATEST", tmp_path / "LATEST")
    with pytest.raises(FileNotFoundError, match="snf_pa.rag.build"):
        index.PolicyIndex.load()


def test_split_search_interleaves_the_queries_without_duplicates(release):
    from snf_pa.rag.decompose import search_split

    idx = index.PolicyIndex.load()
    assert [c["id"] for c in search_split(idx, ["daily skilled nursing", "rehabilitation therapy"], k=2,
                                          mode="bm25")] == ["a", "b"]
    assert [c["id"] for c in search_split(idx, ["daily skilled nursing", "skilled nursing daily"], k=2,
                                          mode="bm25")] == ["a", "b"]
