# Step 3：Policy RAG 开发计划

## 0. 定位与范围

### 对应关系
- 总计划（`snf_pa_multi_agent_rag_plan.md`）的 Step 3「政策知识库」，就是共识计划（`snf_pa_consensus_work_plan_1025.md`）的 **Step 7「政策 RAG 语料与检索评测」**。本计划以共识计划为基础，按下面的范围决定做了收窄。
- 共识计划的 Step 2「criterion cards」已经完成（`policy_docs/criterion_cards.yaml`）。所以这一步不再整理标准本身，只做语料、切块、检索和评测。

### 核心原则：卡片为主，检索补充
- **criterion cards 不经过检索。** Reviewer 判 C3–C6 时，代码直接把对应的卡片放进 prompt，每个病例都用到。
- **检索只用在卡片没覆盖的情况。** 比如气管切开护理、单纯观察病情算不算 skilled，这些细节在 BPM 的举例里。Reviewer 这时调用 `policy_search` 去查原文。
- **Policy RAG 是一个工具，不是 agent**（共识计划 D10、Step 9）。

### 范围决定（2026-11-04）
- **只针对医学必要性（C3–C6）。** 其他标准由 plan profile 里的假设处理（共识计划 D2），不进语料：
  - **医师证明**（C7，§424.20）：MIMIC 中没有这项数据，假设都已提交（`physician_cert: assume_submitted`）。
  - **benefit period**（§409.60–61）：MIMIC 中没有这项数据，假设每个病人都还有可用天数（profile 新增 `benefit_days_available: assume_true`）。
- **不做 Tier 3**（TEAM、WISeR、CMS-0057-F、州法、OIG 报告）。
  - 原因：它们只涉及 C1 或流程，和医学必要性无关。
  - 不入库，系统就检索不到它们；Reviewer 的引用只能填语料里的 chunk ID，所以也引用不了。
  - 模型凭记忆在理由里写出 "TEAM""WISeR" 的风险，用一条文本检查拦住。
  - 这修改了共识计划 D2 中"TEAM 进 Tier-3 语料，并加负向检索测试"的安排。
- **不需要下载新文件。**
  - `bp102c08.pdf`（Rev. 12283）于 2026-11-04 和 CMS 官网当前的版本逐字节比对过，完全相同。
  - eCFR 文件是 2026-10-01 的版本。

### 语料

| 文件 | Tier | 是否进入判定检索 |
|---|---|---|
| `42cfr409_subpartD.xml`（§409.30–409.36） | 1 | 是 |
| `bp102c08.pdf` 中的 §20、§30 | 2 | 是（判断医学必要性主要靠它） |
| `42cfr422_101.xml`（§422.101(b)(c)：MA 必须沿用 TM 的标准） | 1 | 否，作为背景条文 |
| CMS 2024-02 FAQ 的 Q2 和 Q7 | 2 | 否，作为系统设计原则 |
| 其余 14 个 `42cfr422_*.xml` | 1 | 否。内容是时限、申诉、通知等流程，以后做决定信或时限检查时再用 |
| `criterion_cards.yaml` | — | 否。卡片直接用，不检索，原因见第 1 节第 9 条和第 2 节 |

---

## 1. RAG 的 9 个环节：可选做法与本项目的选择

### 1.1 语料范围（Corpus）
- **一般做法**：能找到的相关文档都放进去。
- **本项目**：只放 409 Subpart D 和 BPM Ch.8 的 §20、§30，大约 120–200 个 chunk。
- **原因**：语料越杂，越容易检索到"看起来相关但不该用"的内容。语料小，评测和人工检查都能做完。

### 1.2 文档解析与清洗（Parsing）
很多 RAG 效果差，问题出在原文没解析干净，不在模型。

| 来源 | 难点 | 做法 |
|---|---|---|
| eCFR XML | 简单：段落标签自带 (a)(1)(i) 层级 | 直接按标签解析 |
| BPM PDF | 难：页眉、页脚、页码、每页的 "Rev. 12283" 标记、断行、跨页段落 | 用 pypdf 提取，再用规则清掉页眉页脚、合并断行；抽 10 页人工对照原 PDF |

### 1.3 切块（Chunking）

| 做法 | 说明 | 优缺点 |
|---|---|---|
| 固定长度 + 重叠 | 每 500 tokens 切一刀，前后重叠 50 | 最简单，但会把条款或举例列表从中间切断 |
| 按分隔符递归切 | 先按段落切，太长再按句子切 | 通用，但不懂文档结构 |
| **按文档结构切** | 按 § 编号和段落层级切 | 法规类文档的首选，每块就是一条可以引用的条款 |
| 语义切块 | 按句子相似度的变化点切 | 适合没有结构的长文，这里用不上 |
| 父子块（parent-child） | 小块用来检索，返回它所在的大块 | 检索精确，上下文也完整 |

**本项目：按结构切，加上父子块。**
- 409 切到 (a)/(b)/(c) 这一级，BPM 切到最细一级的 §。
- **举例列表整段保留**：§409.33 的 examples，以及 BPM §30.2–30.4 的举例。总计划和共识计划都这样要求。
- 超过约 800 tokens 的 § 再按小段切开，每块记下 `parent`，需要时可以取回整个 §。
- **每块前面加路径标题**（contextual header），例如 `BPM Ch.8 > §30.4 Skilled Therapy > §30.4.1.2 Maintenance Therapy:`。小块单独看会缺上下文，加上标题后 embedding 和 BM25 都更容易找到它。
- 目标大小：300–800 tokens。

### 1.4 Metadata
- **字段**：`chunk_id`（如 `CFR:409.33(c)`、`BPM8:30.4.1.2`）、`tier`、`source`、`citation`、`title`、`parent`、`effective_date`、`url`、`page`、`criteria`（和哪些 C 标准相关，从卡片绑定推出来）。
- **用途**：检索时按 tier 或标准过滤、加权；输出时显示出处。

### 1.5 Embedding 模型

| 候选 | 特点 | 本地运行 |
|---|---|---|
| **bge-m3**（已安装） | 1024 维，支持 8k tokens 长文本，中英文都行，检索评测成绩好 | 是 |
| nomic-embed-text | 768 维，轻量快速 | 是（Ollama） |
| mxbai-embed-large | 1024 维，英文检索强 | 是（Ollama） |
| 云端模型（OpenAI、Cohere、Bedrock Titan） | 质量好 | 否 |

**本项目：默认用 bge-m3，再在评测集上和另外两个本地模型比较。**
- 只有一两百个 chunk，每个模型算一遍只要几分钟，用不着只看网上的排行榜决定。
- **查询必须在本地做 embedding。** 政策原文是公开的，但 Reviewer 写的查询可能带着病人的情况，不能发到外面。
- 注意：有的模型要求查询和文档加不同的前缀（例如 e5 的 "query:"），向量要做归一化。

### 1.6 向量存储（Vector store）
- **存的是**：每个 chunk 一行，包括 chunk_id 和 metadata、原文，以及 1024 维的向量。不存病历，也不存卡片。
- **本项目：用 numpy，不用 Chroma。** embedding 存成一个 parquet 文件，检索时用 numpy 算余弦相似度。
  - 一两百行 × 1024 个数，大约几百 KB，全部比一遍不到 1 毫秒，数据库帮不上忙。
  - 结果可复现，同一个查询每次排名都一样。
  - 文件小，也不含病人数据，可以入库。同事拿到就能用，不用重算，也不受 chromadb 在 Windows 上的兼容问题影响。
  - Chroma 这类数据库要到几万个 chunk 以上，或者语料经常变化时，才值得用。

### 1.7 检索方式（Retrieval）

| 做法 | 擅长 | 弱点 |
|---|---|---|
| BM25（关键词） | 精确词，如 "5 days a week"、"409.33"、"restorative" | 换个说法就找不到 |
| 向量检索 | 措辞不同但意思相近，如 "won't get better" 对上 "maintenance" | 精确数字和条款号容易丢 |
| **Hybrid（两者用 RRF 融合）** | 两边互补 | 多一步融合，几乎没有额外成本 |

**本项目：hybrid，用 RRF（k=60）融合。**
- BM25 的分词要保留数字和条款号，比如 "409.33" 不能被拆开。
- 检索时可以按标准加权：传入 `criterion=C5` 时，和 C5 相关的 chunk 排得更靠前。
- 默认只检索 Tier 1 和 Tier 2。

### 1.8 查询怎么写（Query formulation）
- **问题**：查询由 Reviewer 根据病例来写，用的是临床语言（"病人有压疮，需要每天换药"）；条文用的是法规语言（"treatment of extensive decubitus ulcers"）。两边措辞差得越远，越难检索到。
- **可选做法**：原样检索；query rewriting（先让 LLM 改写成政策用语）；HyDE（先让 LLM 写一段假设的答案，再拿它去检索）；multi-query（一个问题生成多种问法，再合并结果）。
- **本项目**：先原样检索。评测集里专门放一批临床语言写的问题；如果这批题明显比政策语言的题差，再加 query rewriting。

### 1.9 重排序、上下文组装与生成约束
- **重排序（rerank）**：先取 top 20，用更精细的模型重新排序，再取 top 5。可以用 cross-encoder，如 bge-reranker，也可以让 LLM 逐条打分。
  - **本项目先不做。** 共识计划规定 recall@5 低于 0.9 时才加。
- **上下文组装**：
  - 取 top 5，去掉重复：同一个 parent 下的多个小块合并成父块。
  - 每块前标上 chunk ID 和引用，例如 `[BPM8:30.4.1.2] ...`。
  - 控制总长度，大约 3k tokens 以内。
- **生成约束**（属于 Step 9，但在这一步定好设计）：
  - Reviewer 的 `policy_refs` 只能填 chunk ID。
  - 代码检查 ID 是否存在、tier 是否允许，再回填原文。
  - 这样模型在结构上没法编造条款，思路和病历的 span ID（D9）一样。

---

## 2. 卡片绑定（criterion cards ↔ chunks）

给每张卡记下"它摘自语料里的哪一块原文"，再用代码核对摘得对不对。以 A9 为例：

```
criterion_cards.yaml                       chunks
─────────────────────                      ─────────────────────
id: A9                                     chunk_id: CFR:409.31(b)(2)
cfr: 42 CFR 409.31(b)(2)        ──绑定──►  citation: 42 CFR 409.31(b)(2)
text_verbatim: "The daily skilled          text: "(2) The daily skilled services
  services must be ones that..."                  must be ones that, as a practical
summary_zh / guardrail / ...                     matter, can only be provided..."
```

**绑定程序对每张卡做三件事：**
1. **找 chunk**：把卡片的 `cfr` 换算成 chunk ID，确认语料里真的有这一块。
2. **核对原文**：统一引号和空白后，卡片里的 `text_verbatim` 必须能在那块原文中逐字找到。
3. **核对 see_also**：`see_also` 里列出的条款也要能找到对应的 chunk。

**为什么要做绑定：**
- **防止抄错**：卡片是人工整理的，可能漏字或改了措辞。
- **防止版本漂移**：法规更新、原文一变，绑定就会失败，马上知道哪张卡要改。
- **引用统一**：卡片和检索结果用同一套 chunk ID，代码可以用同一种方法验证所有引用、回填原文。

**为什么不把卡片也放进向量库：**
- 内容重复：卡片的 `text_verbatim` 本来就摘自原文。两份都放，检索会返回几乎一样的两条结果，挤掉别的条文。
- 规则和解读会混在一起：卡片的 note、guardrail、evidence_hints 是我们的解读，不是法规原文。按共识计划，引用必须指向原文条款。

**criterion_cards.yaml 在整个系统里的用处：**

| 阶段 | 谁用 | 怎么用 |
|---|---|---|
| Step 3（本步） | 绑定程序 | 核对卡片和原文是否一致 |
| 共识 Step 8 标注 gold | 标注人 | 作为标注规则：按卡片的条文和 evidence_hints 判 MET / NOT_MET / INSUFFICIENT |
| 共识 Step 9 Criteria Reviewer（主要用途） | LLM | 判 C3–C6 时，把对应卡片的条文、guardrail 和 evidence_hints（question、supports、against、pend_if、rfi）放进 prompt |
| 共识 Step 9 Critic | LLM | 用同一套卡片检查有没有违反 guardrail，比如因为"病情不会好转"就判 NOT_MET，违反 Jimmo |
| 共识 Step 9 Aggregator 和决定信 | 代码、模板 | PEND 时用卡片的 `rfi` 生成补交资料清单；决定信引用绑定的条款号和原文 |
| 共识 Step 10 ablation | 评估 | A1（不给政策）对比 A2（A1 + 全部 cards），衡量卡片带来多少提升 |

---

## 3. 分步做法

代码放在 `src/snf_pa/rag/`。共识计划 Step 0 打算以后把它并入 `engine/`，到时整个目录搬过去即可。

| 编号 | 内容 | 产出 |
|---|---|---|
| 3.1 | 语料核对（已完成：BPM 是最新版，不需要下载） | `SOURCES.md` 中记下核对日期 |
| 3.2 | 解析与切块（`rag/corpus.py`） | `policy_docs/chunks.jsonl`（入库，方便看 diff 和人工检查） |
| 3.3 | 卡片绑定（`rag/bind_cards.py`） | 每张卡的 chunk ID、原文核对结果 |
| 3.4 | 建索引（`rag/index.py`）：bge-m3 向量 + BM25 + RRF，按 tier 过滤，记录语料 hash | `policy_docs/index.parquet`（入库） |
| 3.5 | 检索工具接口（`rag/search.py`）：`policy_search(query, criterion=None, tiers=(1, 2), k=5)`、`get_policy(chunk_id)`、引用校验；输入输出用 pydantic schema | 供 Step 9 的 agent 调用 |
| 3.6 | 检索评测集（`rag/eval_queries.yaml`，入库） | 约 40 条，分 dev 和 test |
| 3.7 | 测试和评测报告 | `tests/test_rag.py`、`reports/step3_rag_eval.md` |

---

## 4. 评估：分四层

### 第 1 层：解析和切块质量
- **自动检查**：
  - chunk ID 不重复；
  - 没有残留的页眉页脚和 "Rev." 标记；
  - 举例列表没有被切断；
  - 块大小分布合理；
  - 16 张卡全部绑定成功，原文 100% 匹配。
- **人工检查**：随机抽 15 个 chunk，生成对照页，和原文比对。全是公开文本，可以直接在对话里展示。

### 第 2 层：检索质量（最核心）

**评测集**：约 40 条"问题 → 应命中的 chunk"。
- **相关度分级**：2 = 直接回答问题；1 = 相关、有帮助。一条问题可以有多个正确答案。
- **问题来源**：卡片的 evidence_hints；把 BPM 里的举例反过来编成问题；按 C3–C6 编写的临床情景。不使用 MIMIC 原文。
- **问题类型**：

| 类型 | 例子 | 条数 |
|---|---|---|
| 政策语言 | "skilled rehab 每周要几天才算 daily？" | 约 15 |
| 临床语言 | "每天静脉抗生素，加每周 5 天 PT" | 约 15 |
| 容易判错的点 | 维持性治疗（Jimmo）；观察与评估、照护计划管理这类"看不出是 skilled"的服务；一周 5 天和 6 天；照护者能否在家提供（替代照护能否报销不影响判断） | 约 10 |

- **分 dev 20 条、test 20 条**：只用 dev 调参数，最后在 test 上跑一次，避免对着考题调模型。
- **gold**：Claude 起草，项目组审核。哪条问题应该命中哪个 §，属于政策判断。

**指标：**

| 指标 | 衡量什么 |
|---|---|
| **recall@5**（主指标） | 正确的 chunk 有没有出现在前 5 名。Reviewer 只看前 5，漏掉了就等于没检索到 |
| MRR | 第一个正确答案排第几 |
| nDCG@10 | 考虑相关度分级的整体排序质量 |

**对比实验**（语料小，每种组合都能跑完）：

| 维度 | 候选 |
|---|---|
| 切块 | 按结构切 / 按结构切 + 路径标题 / 固定 500 tokens |
| Embedding | bge-m3 / nomic-embed-text / mxbai-embed-large |
| 检索方式 | 只用 BM25 / 只用向量 / hybrid |

一共 27 种组合。在 dev 上选出最好的一组，再在 test 上报告结果。

### 第 3 层：失败分析
每条没命中的问题都拿出来，归到某一类：原文没解析好、chunk 边界切错、措辞差距太大（见 1.8）、gold 本身标错。然后按类别修改。这一层比看总分更能说明问题出在哪里。

### 第 4 层：端到端效果（共识 Step 9–10 才能做，这里先定好指标）
- **引用可解析率**：Reviewer 引用的 chunk ID 有多少真实存在。目标 100%，由代码保证。
- **引用支持率**：引用的条文是否真的支持结论。用 LLM 当裁判打分，再人工抽查。
- **RAG 的价值**：对比"什么都不给""只给卡片""卡片 + 检索"三组设置下 C3–C6 判定准确率的差别。

---

## 5. 版本管理与运行成本
- **版本记录**：语料 hash、embedding 模型名和版本写进索引文件，也写进每次运行的 trace（应对共识计划风险表中的"政策版本漂移"）。
- **缓存**：原文没变就不重算 embedding。
- **速度**：一两百个 chunk 用 numpy 比对，不到 1 毫秒。主要耗时是 bge-m3 给查询做 embedding，每条约 0.1–0.5 秒。

## 6. 完成标准
1. test 集上 hybrid 检索的 recall@5 ≥ 0.9（共识计划 Step 7）；
2. 16 张卡全部绑定成功，原文 100% 匹配；
3. 每个 chunk 都有完整的 metadata，`SOURCES.md` 和实际文件对得上；
4. 判定模式下检索不到范围以外的文件，引用校验能拦下不存在的 chunk ID。

工作量约 2 天。

## 7. 做的顺序与分工
1. 解析和切块，接着做第 1 层检查。**项目组看对照页。**
2. 卡片绑定。
3. 起草评测集。**项目组审核 gold。**
4. 建索引，跑 27 组对比，做失败分析，按需调整（可能加 query rewriting 或 reranker）。
5. 在 test 上跑一次最终评测，写 `reports/step3_rag_eval.md`。
6. 完成 `policy_search` 和 `get_policy` 接口，交给 Step 9 使用。

## 8. 暂不做
- **病历侧的 RAG**：D11 规定，整份去泄漏后的出院小结直接放进上下文；单病例检索留到 Step 9 遇到长 note 时再考虑。
- **Reranker**：除非 recall 不够。
- **Tier 3 文件，以及 §424.20、§409.60–61**：见第 0 节的范围决定。
