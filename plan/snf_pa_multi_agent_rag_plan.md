# SNF Prior Authorization 多智能体 + RAG 项目计划

## Context
用户希望用 `data/` 下的数据，做一个面向 **Medicare 出院病人** 的 **SNF（Skilled Nursing Facility）prior authorization** 系统：给定一次住院，判断病人是否符合 Medicare SNF 覆盖条件，并输出有依据（引用政策条款）的决定和理由。本文件先回答"数据是否支持 / 是否需要 multi-agent / 是否需要 RAG"，再给出分步 work plan。

---

## 1. 数据盘点（已实际检查）

`data/` 里是完整的 **MIMIC-IV 3.1 + MIMIC-IV-Note + MIMIC-IV-ED**（Beth Israel, Boston）：

| 数据 | 关键文件 | 对本项目的用途 |
|---|---|---|
| hosp | `admissions` (546k 住院) | `insurance`(Medicare)、`discharge_location`、`admittime/dischtime`、`admission_type`(含 OBSERVATION 类) |
| hosp | `diagnoses_icd`, `procedures_icd`, `drgcodes`, `services`, `transfers` | 诊断、手术、DRG、科室流转 |
| hosp | `prescriptions`, `emar`, `labevents`, `omr` | IV 药物、伤口/营养相关、化验趋势 |
| icu | `chartevents`, `icustays`, `procedureevents` | ICU 病人的护理/功能评估（Braden、活动、跌倒风险等） |
| note | `discharge.csv.gz` (1.1GB) | **核心非结构化证据**：Hospital Course、Discharge Condition（Activity Status）、Disposition |
| note | `radiology` | 骨折、卒中等影像证据 |
| ed | `edstays`, `triage` 等 | 入院前急诊信息（可选） |

实测统计（`admissions`）：
- Medicare 住院 **244,576** 次
- 其中 `discharge_location = SKILLED NURSING FACILITY`：**42,312**（LOS≥3天：36,318；<3天：5,994）
- Medicare 且 LOS≥3天 出院到 HOME HEALTH CARE：40,666；HOME：27,557；REHAB：7,869
- `admission_type` 中有 EU OBSERVATION / OBSERVATION ADMIT 等，可以近似区分 observation vs inpatient（3-midnight rule 关键）

## 2. 结论：数据是否支持？——**支持，但有 4 个必须正视的限制**

**支持的部分**：有足够大的 Medicare 队列、有真实的出院去向、有丰富的出院小结文本，可以构造"SNF vs 非 SNF"的病例，并从文本 + 结构化数据中抽取 Medicare SNF 覆盖条件所需的证据（3-day qualifying stay、daily skilled need、相关诊断、功能下降）。

**限制（要在项目报告里写清楚）**：
1. **没有真正的 PA 决策/拒付标签**。`discharge_location=SNF` 只代表"临床团队决定去 SNF"，不等于"payer 批准"。→ 把它当作 **silver label / proxy**，再人工标注一个小的 gold set（见 Step 6）。
2. **Traditional Medicare（FFS）目前不要求 SNF prior auth**，要 PA 的是 **Medicare Advantage**。MIMIC 的 `insurance=Medicare` 不区分 FFS/MA。→ 项目定位为"按 Medicare 覆盖标准（42 CFR 409 / Benefit Policy Manual Ch.8）做的 MA 风格 PA 审核"；CMS-4201-F (2024) 要求 MA 必须遵循 Traditional Medicare 覆盖标准，这正好让 RAG 语料合法统一。
3. **没有 PT/OT 评估记录、没有 SNF 床位/benefit period 数据**。功能状态只能从出院小结（"Activity Status: Ambulatory - requires assistance"）、ICU chartevents 推断。→ 设计中明确"信息不足 → pend/request more info"这一结果。
4. **标签泄漏风险极高**：出院小结里直接写了 `Discharge Disposition: Extended Care`、"discharged to rehab/___ facility"、出院指导里的去向描述。→ 必须做 **redaction**（Step 2）。

另外 **数据使用协议（PhysioNet DUA）**：MIMIC 数据**不能发送到普通的 ChatGPT/Claude 网页或保留数据的 API**。PhysioNet 允许的方式是：通过 **AWS Bedrock / Google Vertex / Azure OpenAI**（不保留数据、不训练）调用，或本地开源模型。这决定 LLM 选型（推荐 Claude via AWS Bedrock 或 Vertex）。也不要把任何原始 note 放进公开 GitHub 或 demo。

## 3. 需要 multi-agent 吗？——**需要，而且有合理理由（不是为了用而用）**

PA 审核本身就是多角色流程：病历摘录 → 对照标准 → 判定 → 质控 → 写决定信。不同步骤需要不同的上下文和工具（SQL/结构化数据 vs 长文本 vs 政策检索），拆开后每个 agent 上下文更小、更准、可单独评估。

**但注意**：确定性规则（是否 Medicare、住院是否 ≥3 midnights、是否 observation）**用普通 Python 函数/tool，不要用 agent**。

建议的 agent 架构（Orchestrator + 5 个专职 agent）：

```
            ┌────────── Orchestrator / Case Manager ──────────┐
            │  (状态机：intake → extract → evaluate → review) │
            └──────────────────────────────────────────────────┘
   1. Intake/Eligibility Agent   —— tool: SQL on admissions/transfers；3-midnight、Medicare、observation 判断（规则为主）
   2. Clinical Evidence Agent    —— 读 redacted 出院小结 + 结构化数据，输出结构化 evidence JSON（诊断、skilled needs、功能状态，每条带原文引用）
   3. Policy RAG Agent           —— 从 Medicare 政策知识库检索相关条款
   4. Medical Necessity Reviewer —— 将 evidence 对照检索到的条款逐条判定：Approve / Deny / Pend(需补资料)，带置信度
   5. QA / Critic Agent          —— 检查：每个结论是否有病历引用 + 政策引用、是否有幻觉、是否违反"不能因病人无改善而拒绝"(Jimmo)
   6. Letter Writer Agent        —— 生成决定信（批准通知 / 拒绝须附政策依据和申诉权利）
```
Deny 或低置信度 → 进入 **human-in-the-loop**（模拟 medical director 复核），这一点在 PA 场景是监管要求，也是项目亮点。

## 4. 需要 RAG 吗？——**需要，用在两处**

1. **Policy RAG（主要）**：Medicare SNF 覆盖规则条文长、分散、会更新，适合检索而不是塞进 prompt。语料**不在 data 文件夹里，需另外下载（都是公开文档）**：
   - Medicare Benefit Policy Manual **Chapter 8**（SNF Services, §20–§30：3-day stay、skilled services、daily basis、practical matter）
   - **42 CFR 409.30–409.36**（SNF 覆盖条件），42 CFR 424.20（physician certification）
   - **Jimmo v. Sebelius** 和解说明（maintenance therapy 也可覆盖）
   - **CMS-4201-F**（2024 MA 规则：必须用 Traditional Medicare 标准）、**CMS-0057-F**（PA 时限、拒绝理由要求）
   - Medicare Claims Processing Manual Ch.6（可选）、MA denial notice (NDMC/ IDN) 模板
   - ⚠️ InterQual / MCG 是专有标准，**不要使用**
2. **Patient-record RAG（次要）**：出院小结很长（常 >3k tokens），加上 radiology 报告；按 section 切块后在单个病人范围内检索（"patient-scoped retrieval"），给 Clinical Evidence Agent 用。

## 5. Work Plan（Step by step）

### Step 0 — 环境与合规
- **做法**：完成 PhysioNet DUA 确认；开通 AWS Bedrock（或 Vertex）Claude；Python 环境装 `duckdb`, `polars`/`pandas`, `pydantic`, 向量库（`chromadb` 或 `lancedb`/pgvector），agent 框架（推荐 **LangGraph** 或 **Claude Agent SDK**，二选一）。
- **注意**：当前机器 Python 没有 pandas，需要建 venv。原始数据 >10GB（labevents 2.6GB、chartevents 3.5GB），**用 DuckDB 直接读 .csv.gz 或先转 Parquet**，不要 pandas 全量加载。`.gitignore` 掉 `data/` 和任何派生的病人文件。

### Step 1 — 队列构建（Cohort）
- **做法**：DuckDB SQL：
  - 纳入：`insurance='Medicare'`，年龄≥65（`patients.anchor_age` + anchor_year 换算），出院存活，有 discharge note，hosp 时间可用。
  - 正例：`discharge_location='SKILLED NURSING FACILITY'`；负例：`HOME`/`HOME HEALTH CARE`（且 LOS≥3，作为"难负例"）；LTACH 可作为第三类或排除。
  - **REHAB(IRF) 作为独立小层纳入**（40 例：dev 24 / test 16），**按 SNF 标准评估**：IRF 要求多学科、通常每天 ≥3 小时、每周 ≥5 天的治疗（42 CFR 412.622(a)(3)），高于 SNF 的每周 ≥5 天 skilled rehab（42 CFR 409.34(a)(2)），所以预期 C4/C5 多为满足。这一层不当正例也不当负例；不判断病人是否该去 IRF（42 CFR 412.622 只作背景，不得作为 SNF 决定的依据）。这一层在补充样本里（`scenario = irf`，40 例），不在主样本的 300 例里。
  - 计算 **inpatient midnights**：用 `transfers`/`admission_type` 排除 observation 时段，统计跨过的午夜数（Medicare 要求 ≥3 个 inpatient midnights，出院当天不算）。
  - 抽样：以 `data/sample/sample_cases1.csv` 为准，共 300 例，每人一次住院：
    - 5 个诊断类别（髋骨折、卒中、心衰、肺炎/脓毒症、关节置换）各 60 例；每类 SNF 30 / HOME HEALTH CARE 18 / HOME 12（髋骨折 HOME 不够，为 30 / 23 / 7）。
    - **dev 171 / 冻结 test 129**（每个格子内按 hash 排序，约 40% 进 test）；batch 1 = 最初的 50 例。
    - **补充样本** `data/sample/sample_cases1_supp.csv`（160 例，batch 3，`src/snf_pa/data/build_supplement.py` 生成）：补上主样本按设计抽不到、但 MIMIC 里有的场景；不与主样本重复病人，同样约 40% 进 test（dev 88 / test 72）。`scenario` 列标明场景：

      | scenario | 例数（去向） | 补的是 |
      |---|---|---|
      | `c1_short_prior_stay` / `c1_short_no_prior_stay` | 10 / 10（SNF） | 不足 3 午夜去 SNF，30 天内有 / 无合格前序住院（C1、TECHNICAL_NOT_MET 路径） |
      | `obs_to_inpatient` | 20（SNF） | 先观察后住院（C1 边界） |
      | `admitted_from_snf` | 10（SNF） | 从 SNF 入院（§409.36 再入院） |
      | `irf` | 40（REHAB） | IRF 对照层（见下一条） |
      | `deconditioning` | 40（SNF 20 / HHC 12 / HOME 8） | 内科病后体能下降：非手术、不属 5 个类别、有 PT 会诊 |
      | `skilled_nursing` | 20（SNF 12 / HHC 8） | 伤口护理 / 鼻饲 / TPN 医嘱，或静脉抗生素 ≥5 天（C4 skilled nursing） |
      | `dx_gap_hemorrhagic_stroke` / `dx_gap_hypertensive_hf` | 5 / 5（SNF 3 + HHC 2） | 主样本诊断码漏掉的出血性卒中、高血压性心衰 |

      格子很小（2–3 例）时 test 比例会偏离 40%。MIMIC 里不存在的场景（C2 入住 SNF 时间、C7 认证、C8 天数、FFS vs MA、TEAM/WISeR）不抽。
    - 人工标注量按一人约 80–90 例设计（见 Step 6），不再做 ~2,000 例开发集。
- **注意**：同一 `subject_id` 的多次住院要放在同一个 split，防止泄漏；不要只挑"简单例子"；记录 `admission_type` 中 observation 的比例。

### Step 2 — 病历预处理与去泄漏（最关键的一步）
- **做法**：
  - 解析出院小结为 section（Chief Complaint, HPI, Hospital Course, Discharge Condition, Medications…）。
  - **删除/屏蔽**：`Discharge Disposition`、`Facility:`、`Discharge Instructions`、`Followup Instructions` 整段；正则清除 "rehab / extended care / SNF / nursing facility / ___ rehab / discharge to" 等句子。
  - **PA 提交时刻 T_pa = `dischtime` − 24h**（主规则；敏感性分析用 −48h）。模型只能看到 T_pa 之前已存在的信息。
    - 依据：病例经理通常在计划出院前 1–3 天提交 PA；−24h 是这个区间里较晚、证据最多的一端，隐含假设是计划在 1 天内作出决定（加急决定最长 72 小时，42 CFR 422.572(a)，`policy_docs/42cfr422_572_ecfr_2026-10-30.xml`，eCFR up to date as of 2026-10-30）。所以 −24h 的结果是偏乐观的估计，必须同时报 −48h。
    - 带时间戳的数据（`labevents`、`emar`、`prescriptions`、`poe`、`transfers`、ICU、radiology 报告）只取 ≤ T_pa 的记录；radiology 按**签署时间** `storetime`（缺失时用 `charttime`）判断，因为检查做了但报告没签就还不存在。
    - 出院小结写于 T_pa 之后：strict 模式删掉 Discharge Medications；Hospital Course、Discharge Condition 仍含 T_pa 之后的内容，作为已知局限。只用时间戳数据拼成的 timed packet 才完全符合 T_pa。
    - 不用事件规则（如"首个 PT 医嘱"）：MIMIC 只有医嘱时间、看不到 PT 何时建议 SNF；而且截点会随结局变化（去 SNF 的病人 PT 可能更早），截点本身就会泄漏去向。固定偏移对所有病例一样。
    - 已做的敏感性检查（影像测试，`src/snf_pa/data/imaging.py --cutoff-hours`）：timed 影像 AUC −24h 0.651 / −48h 0.648，结构化基线 0.651，结论不随截点改变；主评估（Step 6 的 P/R/F1）两个截点都要报。
  - 结构化特征（均截取到 T_pa）：主要诊断、手术、ICU 天数、IV 抗生素天数（emar/prescriptions）、伤口/压疮相关、最近化验、年龄、既往从 SNF 入院（`admission_location`）。**不用 DRG**：DRG 在出院后编码，属于泄漏。
- **注意**：写一个**泄漏检测器**——用简单关键词模型/TF-IDF 预测标签，若 AUC 异常高，说明还有泄漏；人工抽查 50 篇。`___` 是 MIMIC 去标识占位符，保留即可。

### Step 3 — 政策知识库（Policy RAG）
- **做法**：下载 Step 4 列出的公开文档 → 按**条款层级切块**（§ 编号为单位，300–800 tokens，带 metadata：source、section、effective date、URL）→ embedding（本地 `qwen3-embedding:0.6b`，经 Ollama；选型见下）→ **hybrid 检索（BM25 + 向量，RRF 融合）**，不加 rerank（见下）。
- **索引发布（仿生产数据产品）**：`python -m snf_pa.rag.build` 切块、embedding、跑检索评测，写出带版本的 release `derived/rag/index/<version>/`：`chunks.parquet`（切块 + 文本 sha256 + 向量）、`manifest.json`（embedding 模型名、Ollama digest、维度；每个源文件的 sha256 和版本；git commit；构建时间）、`eval.json`（各模式 recall@k / MRR，评测集 sha256）。版本号 = 日期 + (模型 digest + 全部切块文本) 的哈希，输入相同则版本相同。hybrid recall@5 ≥ 0.9 才移动 `LATEST`，否则构建失败。查询端 `PolicyIndex.load()` 只读 release、只 embed 查询；release 不存在、切块哈希不符、或 Ollama 当前的模型 digest 与 manifest 不一致时直接报错，不会自己重建。
- **检索评测结果**（45 题，`policy_docs/derived/retrieval_eval_GENERATED.yaml`；157 块：CFR XML、BPM Ch.8 Rev. 12283、HPMS FAQ 2024-02-06；release 20261107-23b6d817）：

  | 模式 | recall@1 | recall@3 | recall@5 | MRR | 未命中@5 |
  |---|---|---|---|---|---|
  | BM25 | 0.62 | 0.89 | 0.89 | 0.74 | 5 |
  | 向量（bge-m3） | 0.80 | 0.91 | 0.91 | 0.85 | 4 |
  | **hybrid（采用）** | **0.84** | **0.96** | **0.96** | **0.90** | 2（q08、q43） |
  | hybrid + rerank（不采用） | 0.78 | 0.91 | 0.91 | 0.84 | 4（q06、q08、q19、q43） |

  上表用的是最初的答案键。之后核对原文发现 q08 的答案键不全：BPM §30、§30.3、§30.4 都写明 coverage "does not turn on the presence or absence of … potential for improvement"，已补入（评测集里有注释；同时加了 `=` 写法表示只算该节自身正文，不算子节，q05/q27 也改用它）。新答案键下（release 20261108-23b6d817）：hybrid recall@1 0.82、recall@5 0.98、MRR 0.89，只剩 q43 未命中。
- **也试过、不采用**（2026-11-08）：BM25 加词干化（snowball），以及 hybrid 里加大 BM25 权重（1.5:1、2:1）。recall@5 没有提高（0.96–0.98），recall@1 和 MRR 下降；q43 在所有 hybrid 变体里仍未命中。原因：q43 的 42 CFR 422.626 在 BM25 排第 1，但向量检索排第 73，等权融合后掉到第 12。向量检索还有"热门块"问题：§30.6 出现在 45 题中 10 题的向量 top 5，块之间平均余弦相似度 0.63。只为一道题调权重是对 45 题过拟合，等评测集扩大后再处理。
- **评测集扩到 153 题、换 embedding 模型**（2026-11-08）。45 题时 embeddinggemma 和 qwen3-embedding:0.6b 的 recall@5 都到 1.00，分不出好坏，所以新增 108 题（q46–q153）：个案经理口吻的改写、规则只在某个 CFR 小段里、需要两条规则同时命中（`expect_all`）、MA 规则、相邻项目（IRF、swing bed、hospice、payment ban）。每题带 `kind`、`author` 和 `evidence`（从应命中的块里原文复制，测试检查它确实在那里；还检查同一句话是否出现在答案键之外的块里，发现 4 处已补全）。新题都是 Claude 写的，评测集末尾留了 reviewer 写题的位置，结果按作者分开报。

  153 题上的 hybrid 结果（`policy_docs/derived/retrieval_eval_GENERATED.yaml`，2026-11-08）：

  | embedding 模型 | recall@1 | recall@5 | MRR | 未命中 | CFR 小段 | MA | 两条规则 | 每次查询 |
  |---|---|---|---|---|---|---|---|---|
  | bge-m3（原来） | 0.68 | 0.88 | 0.76 | 19 | 0.68 | 0.85 | 0.17 | 29 ms |
  | embeddinggemma | 0.67 | 0.88 | 0.76 | 19 | 0.68 | 0.69 | 0.33 | 60 ms |
  | **qwen3-embedding:0.6b（采用）** | 0.65 | **0.92** | 0.76 | **13** | 0.79 | **0.92** | 0.33 | 30 ms |
  | qwen3-embedding:4b | 0.67 | 0.90 | 0.76 | 15 | 0.84 | 0.85 | 0.33 | 371 ms |

  选 qwen3-embedding:0.6b：recall@5 最高、未命中最少，在 PA 审核最依赖的 CFR 小段和 MA 规则上明显更好，速度和 bge-m3 一样、体积一半。逐题对比 bge-m3：它多命中 7 题、少命中 1 题（p ≈ 0.07），差距真实但不大。4b 慢 12 倍且不更准；8b-q8_0（8 GB）在 16 GB 机器上会把内存挤爆，没测。查询前缀（qwen3 的 instruction）记在 manifest 里，查询端按 release 使用。现 release `20261108-e0f73935`。
  所有模型的共同弱点不在模型：两条规则的题最多只命中 0.33（前 5 里很难同时放下两条规则，后续考虑把问题拆成子查询），以及 q60、q62、q64、q67、q90、q107、q144 这几道所有模型都没命中。
- **两条规则的题：按规则拆查询**（2026-11-08，`src/snf_pa/rag/decompose.py`）。一次检索时，最匹配的规则排第一，前 5 被同一主题的相近块占满，第二条规则被挤出去。做法：本地 LLM（qwen3.5:9b）从 checklist 规则表里选出问题涉及的规则（最多 3 条），每条写一个短查询；各自做 hybrid 检索，结果交错合并（各取第 1，再各取第 2…）去重取前 5。不强迫拆：LLM 只找到一条规则、或输出失败时，用原问题检索，单规则题不会被改写。为让结果可信，把两条规则的题从 6 道扩到 24 道（q154–q171，同样带 evidence）。171 题结果：

  | 方法 | recall@1 | recall@5 | MRR | 两条规则 | MA | CFR 小段 | 修好 | 弄坏 |
  |---|---|---|---|---|---|---|---|---|
  | hybrid | 0.59 | 0.87 | 0.70 | 0.46 | 0.92 | 0.79 | – | – |
  | **拆查询（采用）** | 0.60 | **0.90** | 0.72 | **0.62** | 1.00 | 0.79 | 8 | 3 |
  | MMR λ=0.7（不采用） | 0.59 | 0.88 | 0.71 | 0.46 | 1.00 | 0.84 | 3 | 2 |
  | MMR λ=0.5（不采用） | 0.59 | 0.82 | 0.68 | 0.46 | 0.92 | 0.68 | 4 | 13 |

  LLM 拆了 24 道两条规则题中的 23 道，其余 147 道只拆了 9 道。8 修好对 3 弄坏（p ≈ 0.23），方向对但样本仍小；两条规则题 0.62 仍不够好，7 道仍未命中。`PolicyIndex.search` 不变。release 门槛改为：hybrid 在**单规则题**上 recall@5 ≥ 0.9（构建时不调 LLM）；两条规则的题照常报告但不设门槛，因为它们靠拆查询（2026-11-08 决定）。接收自由文本问题的调用方用 `splitter()` + `search_split()`。Agent 按 criterion 逐条检索时本来就是一条规则一个查询，不需要拆。每个问题多一次 LLM 调用。第一版提示词（只说"每条规则一个查询"）生成的查询都以同样的泛泛词开头、不点名规则；第二版列出 checklist 规则名但让 LLM 自由写，结果把两条规则的题改写成一条错误规则——所以改成结构化输出：从固定规则表里选。
- **决定：不做 rerank**（2026-11-07）。试过 `BAAI/bge-reranker-v2-m3` cross-encoder（sentence-transformers，本地）对 hybrid 前 20 重排，所有指标都下降：没修好 hybrid 的两个未命中（q08 "无改善潜力"、q43 MA 终止 SNF 服务的申诉），还新弄丢两题——q06（SNF 出院后 10 天再入院）把泛泛的 §20.2.1 排在 30 天再入院规则前面；q19（卒中后吞咽治疗）把罗列服务的 §50.1–§50.3 排在 §30.4.2（skilled 言语治疗）前面。推测原因：该模型在通用网页问答上训练，偏好"看起来相关"的段落而非具体规则。已删除代码和 `sentence-transformers` 依赖（连带 torch 约 1 GB）。以后若评测集变大、hybrid 掉到目标以下，再考虑用 LLM（如 qwen3.5:9b）重排，或只在 hybrid 前几名分数接近时重排。
- 另外人工整理一份 **criteria checklist**（结构化 YAML）：3-midnight stay、30 天内入 SNF、与住院相关的病情、需要 daily skilled nursing（7天/周）或 skilled rehab（5天/周）、practical matter 只能在 SNF 提供、physician certification。Reviewer 逐条判定，每条都要检索到支撑条文。
- **注意**：条文切块别切断 "examples" 列表（Ch.8 §30.2–30.4 举例很重要）；保留版本/日期；建一个 30–50 条的检索评测集（问题→应命中的 §），测 recall@5。

### Step 4 — 工具层（Tools，非 agent）
- **做法**：实现确定性函数供 agent 调用：`get_admission(hadm_id)`、`count_inpatient_midnights()`、`get_diagnoses()`、`get_meds(iv_only)`、`get_note_sections()`、`search_patient_record(query)`、`search_policy(query)`。全部返回结构化 JSON。
- **注意**：工具输出要短（摘要/截断），避免把整张 labevents 塞进上下文；每个工具单元测试。

### Step 5 — Agent 实现与编排
- **做法**：
  - 每个 agent 定义 **Pydantic 输出 schema**（例如 Evidence: `{criterion, finding, source_section, quote}`；Decision: `{criterion_results[], overall: approve|deny|pend, confidence, rationale, policy_citations[]}`）。
  - Orchestrator 用状态图：Eligibility 不通过 → 直接 deny/不适用（不用调用 LLM）；通过 → Evidence → Policy RAG → Reviewer → QA；QA 不通过可回退一次让 Reviewer 修正（限制循环次数）。
  - 低置信度或 deny → `human_review` 队列。
  - **不强迫 LLM 作答**：每个判定的 schema 都有"不确定 / 证据不足"选项（逐条 criterion 用 `insufficient_evidence`，总体用 `pend`），prompt 明确"不确定时选它，错判比不确定更糟"；评估时分开报覆盖率（作答比例）和作答部分的准确率。泄漏检查 `snf_pa.data.leakage_llm` 已按此改为可答 `unsure`。
  - 模型分配：Evidence/Reviewer 用强模型（Opus/Sonnet），QA/格式化用 Haiku 降成本。
- **注意**：要求所有结论**引用原文 quote**，QA 用字符串匹配验证 quote 真实存在于 note 中（防幻觉）；prompt 中明确 Jimmo 原则（"无改善潜力"不是拒绝理由）；用 prompt caching 缓存政策条款和 system prompt；温度设 0；记录完整 trace（LangSmith / 本地 JSONL）便于审计。

### Step 6 — 标注与评估
- **做法**：
  - **Silver 评估**：在主样本 129 例 test 上对比系统决定 vs `discharge_location`，报告 precision/recall/F1、按诊断分层的结果、pend 比例；补充样本按 `scenario` 单独报告。REHAB(IRF) 层不计入 precision/recall/F1，单独报告：预期多为 approve；若系统建议拒绝或补材料，检查是否误用了 IRF 标准（如"耐受不了每天 3 小时""只需一种治疗""无可测量改善"）。
  - **Gold 评估**：人工按 checklist 逐条标注（MET / NOT_MET / INSUFFICIENT + 证据），评估逐条判定准确率。每例约 15–25 分钟，所以：
    - **dev-gold 20–30 例**（自己标，从 dev 171 例中抽，用于调 prompt）；
    - **test-gold 60 例**（自己标）：约 45 例从主样本 test 129 例中按诊断 × 去向分层抽，约 15 例从补充样本 test 72 例中按 `scenario` 抽（每个场景 1–3 例，含 IRF）；决策级差异约能检出 ±12–13 个百分点；
    - 以后有临床背景的标注者时再补 60 例到 120，并双人标注一部分算 κ。
  - **Faithfulness**：quote 命中率、policy citation 是否真的支持结论（LLM-as-judge + 人工抽查）。
  - **Baseline 对照**：(a) 规则 baseline，(b) 单 agent + 无 RAG，(c) 单 agent + RAG，(d) 完整 multi-agent + RAG——用 ablation 证明 multi-agent 和 RAG 的价值。
  - 公平性：按 race、language、性别分层看 deny 率差异。
- **注意**：silver label 有噪声（有的病人符合但回家了、有的去 SNF 是因社会原因如无人照顾——这不是 Medicare 覆盖理由），分析错误案例时要区分"系统错"和"标签错"；成本/延迟也要记录。

### Step 7 — 输出与 Demo
- **做法**：简单 UI（Streamlit/Gradio）：输入 hadm_id → 展示每个 agent 的步骤、逐条 criteria 结果、病历引用高亮、政策条文链接、决定信、人工 override 按钮。
- **注意**：Demo 只在本地/私有环境运行，**不要公开部署含 MIMIC 内容的 demo**；公开展示可用合成病例（自己编写的假病人）。

## 6. 主要风险汇总
| 风险 | 对策 |
|---|---|
| 无真实 PA 标签 | silver + 小 gold set；清楚陈述局限 |
| 标签泄漏 | Step 2 redaction + 泄漏检测 |
| FFS 不需 PA | 定位为 MA 场景 + CMS-4201-F |
| DUA 违规 | 只用 Bedrock/Vertex/本地模型；数据不上 GitHub |
| 幻觉/无依据拒绝 | 强制 quote + citation；QA agent；deny 必须人工复核 |
| 数据量大 | DuckDB/Parquet，先做小样本 |

## 7. Verification（实施后如何验证）
- 队列 SQL 的计数与本文实测数一致（Medicare SNF ≈42k）。
- 泄漏检测器 AUC 在 redaction 后显著下降，人工抽查 50 篇无去向信息。
- 政策检索 recall@5 ≥ 0.9（自建评测集）。
- 端到端跑 20 个已知病例（10 SNF / 10 home），检查每个 agent 输出 schema 合法、quote 全部可在原文找到。
- 完整测试集 ablation 表格（4 种配置）产出。
