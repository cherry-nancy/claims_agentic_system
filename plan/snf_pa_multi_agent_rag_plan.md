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
  - 正例：`discharge_location='SKILLED NURSING FACILITY'`；负例：`HOME`/`HOME HEALTH CARE`（且 LOS≥3，作为"难负例"）；REHAB(IRF)/LTACH 可作为第三类或排除。
  - 计算 **inpatient midnights**：用 `transfers`/`admission_type` 排除 observation 时段，统计跨过的午夜数（Medicare 要求 ≥3 个 inpatient midnights，出院当天不算）。
  - 抽样：先做 ~2,000 例开发集 + 300 例测试集，按诊断类型分层（髋骨折、卒中、心衰、肺炎/脓毒症、关节置换等）。
- **注意**：同一 `subject_id` 的多次住院要放在同一个 split，防止泄漏；不要只挑"简单例子"；记录 `admission_type` 中 observation 的比例。

### Step 2 — 病历预处理与去泄漏（最关键的一步）
- **做法**：
  - 解析出院小结为 section（Chief Complaint, HPI, Hospital Course, Discharge Condition, Medications…）。
  - **删除/屏蔽**：`Discharge Disposition`、`Facility:`、`Discharge Instructions`、`Followup Instructions` 整段；正则清除 "rehab / extended care / SNF / nursing facility / ___ rehab / discharge to" 等句子。
  - 模拟"PA 提交时刻"：只保留出院前可获得的信息（结构化数据截取到 dischtime 前）。
  - 结构化特征：DRG、主要诊断、手术、ICU 天数、IV 抗生素天数（emar/prescriptions）、伤口/压疮相关、最近化验、年龄、既往从 SNF 入院（`admission_location`）。
- **注意**：写一个**泄漏检测器**——用简单关键词模型/TF-IDF 预测标签，若 AUC 异常高，说明还有泄漏；人工抽查 50 篇。`___` 是 MIMIC 去标识占位符，保留即可。

### Step 3 — 政策知识库（Policy RAG）
- **做法**：下载 Step 4 列出的公开文档 → 按**条款层级切块**（§ 编号为单位，300–800 tokens，带 metadata：source、section、effective date、URL）→ embedding（Bedrock Titan/Cohere 或本地 `bge`/`e5`）→ **hybrid 检索（BM25 + 向量）+ rerank**。
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
  - 模型分配：Evidence/Reviewer 用强模型（Opus/Sonnet），QA/格式化用 Haiku 降成本。
- **注意**：要求所有结论**引用原文 quote**，QA 用字符串匹配验证 quote 真实存在于 note 中（防幻觉）；prompt 中明确 Jimmo 原则（"无改善潜力"不是拒绝理由）；用 prompt caching 缓存政策条款和 system prompt；温度设 0；记录完整 trace（LangSmith / 本地 JSONL）便于审计。

### Step 6 — 标注与评估
- **做法**：
  - **Silver 评估**：在 300 例测试集上对比系统决定 vs `discharge_location`，报告 precision/recall/F1、按诊断分层的结果、pend 比例。
  - **Gold 评估**：人工（最好有临床背景）按 checklist 标注 100–150 例，评估逐条判定准确率。
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
