# Policy RAG: Chunking Method and Retrieval Evaluation

> ⚠️ **AI-GENERATED DOCUMENT. This is not an original policy source.**
> Claude (Anthropic, model `claude-opus-5-5`) wrote this summary through Claude Code on 2026-11-08. A person has not
> yet reviewed it. The numbers come from index release `20261108-e0f73935` (`derived/rag/index/<version>/eval.json`)
> and `python -m snf_pa.rag.decompose`. If this file and the code disagree, the code is correct.

The code is in `src/snf_pa/rag/`; the design decisions are in `plan/snf_pa_multi_agent_rag_plan.md`, Step 3.

## 1. Sources

Fourteen official files from `policy_docs/`, registered in `sources.py` with version, program and tier. Every chunk
carries these, so a citation always names its file and version, and search can filter by tier.

| Tier | Meaning | Files |
|---|---|---|
| 1 | Binding rule | eCFR XML: 42 CFR 409 Subpart D, 409.60, 409.61, 424.20; 42 CFR 422.101, .112, .138, .566, .568, .572, .626 (Medicare Advantage) |
| 2 | CMS guidance | Medicare Benefit Policy Manual (BPM) Ch.8, Rev. 12283, issued 2023-10-05; CMS HPMS FAQ on CMS-4201-F, 2024-02-06 |
| 3 | Background, never a basis for a SNF decision | 42 CFR 412.622 (IRF), kept so that IRF rules can be filtered out |

## 2. Chunking method

**It is structure-based chunking, not semantic chunking.** Semantic chunking embeds sentences and cuts where the
similarity between neighbours drops. Our chunkers cut only at boundaries the documents already mark: CFR paragraph
levels, BPM section numbers, FAQ item numbers. No model is involved, so the same files always give the same chunks.

Reasons for choosing structure over semantic chunking:

1. **The authors already split the text by topic.** A CFR paragraph or BPM section is the regulator's own topic
   boundary. Legal text repeats the same vocabulary across topics, which weakens the similarity signal semantic
   chunking depends on.
2. **Citations must be exact.** Each chunk is one citable unit, e.g. `42 CFR 409.33(a)(2)–(a)(3)`, and its `body` is
   the verbatim source text, so a quoted passage can be checked by string match.
3. **Lead-ins carry meaning.** "(a) Services that could qualify as either skilled nursing or skilled rehabilitation
   services—" governs every item below it. We repeat it in the header of each chunk split from that paragraph; a
   similarity splitter would separate a list from its lead-in.
4. **Reproducibility.** The chunks do not change when the embedding model changes, so index versions stay
   comparable.

### Rules shared by all chunkers

- At most **800 tokens** per chunk, header included.
- Text is split only **between** units (paragraphs, sub-paragraphs, sections), never inside one.
- A unit that fits stays whole with everything under it; a larger one is split between its children, and small
  neighbouring units under the same parent are packed together.
- Each chunk has three text fields:
  - `body`: the exact source text. A section's bodies, in order, rebuild the section exactly once (tested).
  - `header`: where the chunk sits, so a chunk cut from a long section still says what it belongs to.
  - `text` = header + body; this is what is searched and embedded.

### Per document

| Document | Module | Split on | Header carries |
|---|---|---|---|
| CFR (eCFR XML) | `cfr.py` | Paragraph tree (a) > (1) > (i) > (A) > italic (1) > italic (i) | Section heading, plus the lead-in of each enclosing paragraph not already in the body (cut to 300 characters) |
| BPM Ch.8 (PDF) | `bpm.py` | Section tree 30 > 30.2 > 30.2.3 > 30.2.3.1; inside a section, between paragraphs. An "EXAMPLE" label stays with its paragraph. | Chapter and section path; "(continued)" and the last lead-in sentence for a continued section; the section's own revision line in `history` |
| CMS HPMS FAQ (PDF) | `faq.py` | One question-and-answer item per chunk; a long answer split between paragraphs. Footnotes are removed from the answer and become chunks of their own. | The question, repeated in every part |

Example: 42 CFR 409.33 becomes five chunks: (a), (a)(2)–(a)(3), (b), (c) and (d). The (a)(2)–(a)(3) chunk has
this header:

```
42 CFR 409.33 Examples of skilled nursing and rehabilitation services.
(a) Services that could qualify as either skilled nursing or skilled rehabilitation services—
```

### Result

**157 chunks**: 74 from BPM Ch.8, 25 from the FAQ, 58 from the CFR files. Tokens per chunk: median 552, quartiles
277–698, range 31–799.

Each chunk stores 14 metadata fields: id, citation, section, section_title, paragraphs (every paragraph it covers),
header, body, text, n_tokens, source_file, version, program, tier, history.

There is no parent–child (small-to-big) index. The header gives each chunk its parent's context instead.

## 3. Search and index releases

- **Hybrid search** (`index.py`): BM25 for exact terms ("observation", "§ 409.34") plus vector search with
  `qwen3-embedding:0.6b` (queries get the model's instruction prefix), fused with reciprocal rank fusion (k = 60).
  All 157 chunks are scored for every query; no vector database is needed.
- **Filters**: `max_tier=2` keeps the tier-3 IRF rule out of SNF decisions; `programs` limits by program.
- **Query split** (`decompose.py`): a local LLM (`qwen3.5:9b`) lists the rules a question needs, chosen from a fixed
  checklist; each rule is searched separately and the results are interleaved. With fewer than two rules, or on
  any failure, the original question is searched unchanged.
- **Versioned releases** (`build.py`): each build writes `chunks.parquet` (metadata, text hash, vector),
  `manifest.json` (model digest, source-file hashes, git commit) and `eval.json`. The live pointer moves only if
  one-rule recall@5 ≥ 0.9. Loading refuses a changed chunk text or a different embedding model.

## 4. Evaluation

**Question set**: `policy_docs/derived/retrieval_eval_GENERATED.yaml`, 171 questions, each with the citations that
answer it; 24 questions need two rules and count as a hit only if both are found.

**Metrics**: recall@k is the share of questions with a correct chunk in the top k. MRR is the mean of 1 / rank of
the first correct chunk, so 1.0 means always first.

### Overall

| | BM25 | Vector | Hybrid | Hybrid + query split |
|---|---|---|---|---|
| recall@1 | 0.53 | 0.54 | 0.59 | 0.60 |
| recall@3 | 0.73 | 0.75 | 0.79 | 0.82 |
| **recall@5** | 0.74 | 0.80 | **0.87** | **0.90** |
| MRR | 0.62 | 0.65 | 0.70 | 0.72 |
| One-rule recall@5 (release gate ≥ 0.9) | 0.82 | 0.87 | **0.94** | — |
| Misses at 5 | 44 | 34 | 22 | 17 |

### Recall@5 by question kind

| Kind | n | BM25 | Vector | Hybrid | Split |
|---|---|---|---|---|---|
| Original (first set, written with the criterion cards) | 45 | 0.89 | 0.98 | 1.00 | 1.00 |
| Paraphrase (same rule, different words) | 59 | 0.76 | 0.86 | 0.93 | 0.93 |
| Sub-paragraph (answer is one specific sub-paragraph) | 19 | 0.74 | 0.58 | 0.79 | 0.79 |
| Adjacent program (confusable with IRF, home health, ...) | 11 | 0.91 | 1.00 | 1.00 | 1.00 |
| Medicare Advantage | 13 | 0.85 | 0.85 | 0.92 | 1.00 |
| **Two rules** | 24 | 0.29 | 0.38 | **0.46** | **0.62** |

### Findings

- **Hybrid beats either ranking alone** on every kind. Vector search is better on paraphrases; BM25 is better on
  exact sub-paragraph wording, where vector search falls to 0.58.
- **Two-rule questions are the main weakness.** One search ranks the best-matching rule first and fills the top 5
  with chunks on the same topic. The query split raises them from 0.46 to 0.62: it fixed 8 questions and broke 3, a
  gain that is not yet statistically significant (p ≈ 0.23).
- **Remaining misses**: 22 for hybrid. Seven are missed by every embedding model tried (q60, q62, q64, q67, q90,
  q107, q144); most of the rest are two-rule questions.
- **The scores are likely optimistic.** Every question was written by Claude, and the first 45 were used while tuning
  the chunkers and answer keys (hence 1.00). The set's reviewer-written section is still empty; questions from a
  reviewer or an outside source are needed for an unbiased score.

### Tried and not adopted

| Change | Result |
|---|---|
| Cross-encoder reranker (`bge-reranker-v2-m3`, hybrid top 20) | recall@5 fell from 0.96 to 0.91 (on the earlier, smaller question set) |
| BM25 stemming, BM25 weighting in the fusion | No gain |
| MMR (diversity re-ranking) | Not adopted |
| Embedding models, 153-question set, hybrid recall@5 | `qwen3-embedding:0.6b` 0.92 (chosen); `qwen3-embedding:4b` 0.90 at 371 ms/query; `bge-m3` 0.88; `embeddinggemma` 0.88. `qwen3-embedding:8b-q8_0` did not fit in 16 GB RAM. |
