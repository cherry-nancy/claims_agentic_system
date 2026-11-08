# 队友分支调查

- 日期：2026-11-08
- 我们的分支：`zhijie-20261108`（从 `zhijie-plan-1025` @ `7aa9d6e` 切出），目录 `D:\Repo\claims_agentic_system`
- 范围：**只做调查，不下采用与否的结论**（按用户要求）。采用 / 论证 / 分歧说明留到对应步骤开工时，按 CLAUDE.md「队友已经做过的工作」的流程做。
- 方法：`git fetch --all --prune` 后，只用 `git show` / `git diff` / `git log` 读远程分支，没有 checkout，没有改队友分支。两个分支各由一个 subagent 通读，我对关键结论逐条用 `git show` 复核（见第 5 节）。没有在队友代码上跑测试。

## 0. 远程分支一览

`git ls-remote --heads origin`（2026-11-08）：

| 分支 | head | 作者 | 说明 |
|---|---|---|---|
| `snf-prior-auth` | `8202079` | Hui Li | 初始项目（环境、`tests/`、初版计划）。是所有分支的共同起点，也是我们 `tests/test_sample.py`、`check_*.py` 的来源 |
| `snf-criterion-cards` | `9ac1584` | Hui Li | 从 `8560e4b`（设计文档的早期版本）分出，6 个 commit |
| `cfeng` | `b60f21e` | cfeng85 | 从 `8202079` 分出，5 个 commit |
| `main` | `d5daab2` | — | 空的初始 commit |
| `zhijie-plan-1025` / `zhijie-plan-1108` | `7aa9d6e` | 我们 | 两者指向同一 commit |

除 `snf-criterion-cards` 和 `cfeng` 外没有其他队友分支。

**编号提醒**：两位队友笔记里的 "Step 1/2/3…" 是初版计划 `plan/snf_pa_multi_agent_rag_plan.md` 的编号；`snf-criterion-cards` 里的 "D6–D11""Step 7" 是 `8560e4b` 版设计文档的编号（例如那一版的 D7 = 段落保留规则、D8 = realistic 消融、D9 = span ID、Step 7 = 政策 RAG）。下表按内容对应到我们第 12 节的 ①–⑨。

## 1. 工作对照表

| 我们的步骤 | `snf-criterion-cards`（Hui Li） | `cfeng`（cfeng85） |
|---|---|---|
| ① 环境与仓库修复 | `src/snf_pa/data/config.py`（`b31285a`）：路径常量，**写死**为仓库内 `data/mimiciv-3.1/...`；`.gitignore` 修正让 `src/snf_pa/data` 进 git。我们的 `tests/test_sample.py` 引用的正是这个模块 | `src/snf_pa/data/config.py`（`1c19996`）：读环境变量 `MIMIC_ROOT`（不是 `MIMIC_RAW_DIR`），默认 `<repo>/physionet.org/files`，目录布局 `mimiciv/3.1/hosp`、`mimic-iv-note/2.2/note`；不加载 `.env` |
| ② 队列 + Parquet 子集 | 队列与 300 例抽样、dev/test 划分：`cohort.py`、`build_sample.py`；产出 `data/sample/sample_cases.*`、`candidate_counts.csv`、`manifest.json`、`notes_raw.parquet`（已进 git）。**没有**大表 Parquet 子集 | 主样本 300 例 + 补充样本 160 例：`cohort.py`、`build_sample.py`、`build_supplement.py`。`data/` 整个被 gitignore，产出未提交。**没有**大表 Parquet 子集 |
| ③ MIMIC adapter | 出院小结切段、切句、span ID、去泄漏、strict / realistic 两种病历包：`sections.py`、`redact.py`、`build_packets.py`、`tests/test_redact.py`（`84832e0`）；泄漏检查 `leakage.py`、`leakage_pool.py`；50 例人工抽查 HTML `review_html.py` + `data/sample/review/`；报告 `reports/step2_leakage_report.md`。**没有** T_pa、事实卡、影像 | 去泄漏 `redact.py`（rules-v3）、span 表；泄漏检查 `leakage.py`（文本探针）、`leakage_llm.py`（LLM 审计）、`review.py`（50 例盲审页）；影像 `imaging.py`（IMPRESSION + 出院前截断）。**没有** `CaseBundle`、POE 时间线、事实卡 |
| ④ 规则引擎 | 无 | 无 |
| ⑤ criterion cards + 政策索引 | `policy_docs/criterion_cards.yaml`：16 张卡 + C3–C6 的 `evidence_hints`（`e279503`、`3aee82b`）；`policy_docs/SOURCES.md`；CMS 2024-02 MA FAQ（PDF + txt）；政策 RAG **只有计划**：`plan/step3_RAG_plan.md`、`plan/step3_notes.md`（`9ac1584`） | 29 张卡 `policy_docs/derived/criterion_cards_GENERATED.yaml`（标明 AI 草稿、未经人工审）；CFR / BPM / FAQ 切块 `rag/cfr.py`、`bpm.py`、`faq.py`；混合索引 + 版本化发布 `rag/index.py`、`build.py`；171 条检索评测集 `retrieval_eval_GENERATED.yaml`（标明 Claude 生成、待审）；LLM 查询拆分 `rag/decompose.py`；新增 CFR 原文 XML / PDF 若干；4 组测试 |
| ⑥ 网关 + reviewer + critic | 无 | 无 |
| ⑦ 冒烟 + silver | 无 | 无 |
| ⑧ gold + 正式评估 | 无（计划里提到 dev / test 检索评测各 20 条） | 无（初版计划改动里写了 test-gold 60、dev-gold 20–30） |
| ⑨ Part 2 | 无 | 无 |
| 其他 | 依赖新增 `pandas`、`scikit-learn` | `policy_docs/derived/snf_eligibility_requirements_GENERATED.md`（AI 生成的资格要求摘要）；改了初版计划 `plan/snf_pa_multi_agent_rag_plan.md`；依赖新增 3 项 |

两个分支都**没有**：`CaseBundle`、POE 住院起点 / C1、事实卡、大表 Parquet 子集、规则引擎、模型网关、agent。

## 2. 与设计文档的实质差异（事实，不含结论）

只列会影响结果的地方。"设计"指 `plan/snf_pa_consensus_work_plan_1025.md`（v7）。

### 2.1 队列与抽样（对应 ②；设计 3.2、10.1、附录 A）

| 项 | 设计 | `snf-criterion-cards` | `cfeng` |
|---|---|---|---|
| 入院年份 | 2011–2018 | 不过滤（`anchor_year_group` 未使用） | 不过滤 |
| 观察期入院 | **不能排除**（占 SNF 出院 23%） | 排除：`admission_type not ilike '%OBSERVATION%'`，且排除进过观察病房的（`cohort.py` L60、L80） | 主样本排除（`cohort.py` L94–95）；补充样本里有 `obs_to_inpatient` 20 例 |
| 住院午夜数 | C1 由规则引擎从 POE 住院医嘱起算；不足 3 午夜作为边界病例保留 | 作为纳入条件 `>= 3`，按 `admittime` 到 `dischtime` 的日期差算（`cohort.py` L56、L75） | 同左（`cohort.py` L55、L93）；补充样本有 `c1_short_*` 20 例 |
| 出院去向 | SNF + HHC、HOME、REHAB 对照 | SNF / HHC / HOME，无 REHAB（`config.py` L19–23） | 主样本同左；补充样本有 REHAB 40 例 |
| 其他条件 | Medicare、≥65、存活、有出院小结 | 相同 | 相同，另加出院小结 ≥500 字符（`cohort.py` L87） |
| 分层 | 临床场景 × 去向 × 边界 | 5 个主诊断类别 × 60（SNF 30 / HHC 18 / HOME 12） | 主样本同左；补充 160 例分 9 个场景 |
| 规模 | dev 100 / test 200（test-gold 120） | dev 171 / test 129 | 主 dev 171 / test 129；补充 dev 88 / test 72 |
| 划分方式 | **先按 `subject_id` 划分，再在各自范围内抽样**；划分文件冻结 | 先抽样，再在每个格子内按 hash 排名 `rn % 5 in (1,2)` 分到 test（`cohort.py` L138）；靠"每人只取一次住院"保证不跨 split | 同左思路；`build_sample.py` L41–43（后 40% 进 test）与 `config.py` L27–29（`% 5 in (1,2)`）写法不一致；无独立划分文件 |

### 2.2 时点与病历处理（对应 ③；设计 3.3–3.6）

| 项 | 设计 | `snf-criterion-cards` | `cfeng` |
|---|---|---|---|
| T_pa | `max(出院 − 24h, 住院起点)`，所有数据按它截断 | 未实现（`plan/step 2_notes.md` L50 推迟） | 只用在影像：`signed <= dischtime − 24h`（`imaging.py` L164），没有 `max(·, 住院起点)`；另有 −48h 敏感性分析 |
| 删除的段 | Disposition、Facility、Discharge Instructions、Followup、Discharge Diagnosis、Discharge Medications | DISPO、FAC、DXDC、DCI、FU 总删；MEDDC 只在 strict 删，realistic 保留并清掉 RX / Disp / Refills 行（`redact.py` L17–18） | **保留** Discharge Diagnosis 和 Discharge Instructions 里的 PT、伤口护理、抗凝、活动负重等子块（`redact.py` L54–59）；Discharge Medications 在 realistic（默认）保留并去掉 PRN 和 RX 行，strict 删 |
| 遮蔽方式 | 遮蔽去向句；PT/OT 建议去向的半句遮蔽，同句功能描述保留 | 整句命中直接删除，**不留标记**；PT/OT 句内的半句留 `[REDACTED-DISPO]`；realistic 保留 PT/OT 建议；入院前住所、既往 rehab 史有意保留 | 一律删除、不留标记；子句级删除，列表重新编号；词表更宽（含 hospice、VNA、outpatient、PCP、case manager 等） |
| span ID | `DS:HC:s14`，稳定 | `DS:{code}:s{i}`，在遮蔽**前**编号（strict 有空号） | `DS:<CODE>:s<n>`，按遮蔽**后**显示的句子编号；规则一改就重新编号 |
| 影像 | 只取 IMPRESSION | 未处理 | 处理（见上） |
| 事实卡 | 有（3.6 节） | 无 | 无 |
| 泄漏检查 1：残余去向词 | 单元测试要求为 **0** | 单元测试只用合成病历；真实数据上 strict 残余**不为 0**：HPI 中 place_snf 在 snf=1 的 40 篇、snf=0 的 5 篇出现（`data/sample/leakage_report.json` 的 `residue_strict`，我已复核） | 单元测试只用合成病历；真实数据上残余率只报告不断言 |
| 泄漏检查 2：人工抽查 50 篇 | 有 | 页面已做，抽查未做 | 盲审页已做，结果未提交 |
| 泄漏检查 3：文本探针 | TF-IDF + LR，遮蔽前后 AUC 对比 | 有，另在 2,655 篇样本外池上训练；strict 整篇 held-out AUC 0.652 [0.596–0.710]，原文 0.793 | 有，在 3,000 篇样本外池上训练；评估集**没有排除 `split == 'test'`**（`leakage.py` L128，我已复核） |

### 2.3 criterion cards 与政策检索（对应 ⑤；设计第 4 节）

| 项 | 设计 | `snf-criterion-cards` | `cfeng` |
|---|---|---|---|
| 卡片字段 | 定义、条文原文、正反例、**查询词表（含同义词）** | 16 张，CFR 原文 + 中文摘要 + guardrail；**无查询词、无正反例**；C3–C6 另有 `evidence_hints`；无 C2、C7、C8 卡 | 29 张（10 张沿用 Hui Li 的），`*_verbatim` + 中文摘要；**无查询词、无病例级正反例**；明确不引 BPM 原文 |
| 索引语料 | Tier 1：409.30–36、409.60–61、424.20、422.101、422.566；Tier 2：BPM Ch.8、2024-02 FAQ、Jimmo。Tier 3 不进索引 | 计划只含 409 Subpart D + BPM §20/§30（`step3_RAG_plan.md` L14–36） | 另加 422.112 / .138 / .568 / .572 / .626（Tier 1）；**412.622（IRF）以 tier 3 进了索引**，`search()` 默认不过滤 tier（我已复核 `sources.py`）；Jimmo 未收 |
| 切块 | 以 § 为单位，300–800 tokens；§409.33 和 BPM §30.2–30.4 举例列表整段保留；带 `effective_date` | 计划：父子块 + 上下文标题 | 上限 800、无下限；§ 可以被拆开（如 `409.33(c)(1)-(c)(4)`、`§30.4 (part 2)`）；**无 `effective_date` 字段**；157 块 |
| 检索方法 | BM25 起步；recall@5 < 0.9 时先补同义词，再加向量 + RRF | 计划一开始就用 bge-m3 + BM25 + RRF，比较 27 种配置 | 已实现 BM25 + qwen3-embedding:0.6b + RRF；其计划里记录 BM25 单独 recall@5 = 0.89（45 题）；没有做"补同义词"这一步 |
| 谁发起检索 | **代码生成查询**，LLM 不发起检索 | reviewer 通过 `policy_search` 工具自己调（`step3_RAG_plan.md` L11） | `decompose.py`：**LLM（qwen3.5:9b）选规则并写查询**（L65–76，我已复核）；尚未接入任何流程 |
| 评测集 | 约 40 条，recall@5 | 计划约 40 条，dev / test 各 20 | 171 条（q46 以后 `author: claude`），recall@1/3/5 + MRR；5 条期望命中 412.622 |
| 索引版本 | 语料 hash + 切块参数 | 计划中 | 已实现：日期 + hash(模型 digest + 块文本)，manifest 记录源文件 sha256 和 git commit |

## 3. 我们计划里没有的工作（中性描述）

| 项 | 分支 | 是什么 |
|---|---|---|
| strict / realistic 两种病历包 | 两边都有 | realistic 保留清洗过的出院用药和 PT/OT 建议，作为消融。`8560e4b` 版设计里是 D8，v7 删掉了 |
| 样本外泄漏探针池 | 两边都有 | 2,655 / 3,000 篇不在样本里的出院小结，用来训练去向分类器，再在样本上测 AUC |
| 按段落的 AUC、段落出现率检查 | `snf-criterion-cards` | 例如 Facility 段在 SNF 病历中 100% 出现、回家病历 72% |
| LLM 猜去向探针 / LLM 泄漏审计 | 两边都有 | 本地小模型读处理后病历猜去向；Hui Li 的 medgemma:4b 在原文阳性对照上也失败（AUC 0.26） |
| 补充样本 160 例（9 个场景，含 REHAB 40 例） | `cfeng` | 覆盖观察转住院、不足 3 午夜等边界 |
| 影像复制文本检测 | `cfeng` | 用 3-gram 找出出院小结里抄进来的影像报告，替换为出院前已签发的 IMPRESSION |
| PRN 用药删除、−48h 敏感性 | `cfeng` | — |
| 额外 CFR 条款 | `cfeng` | 412.622（IRF）、422.112 / .138 / .568 / .572 / .626 |
| 向量模型比较、LLM rerank 尝试（已放弃） | `cfeng` | — |
| LLM 查询拆分 | `cfeng` | 见 2.3 |
| 卡片原文与切块逐字比对（计划） | `snf-criterion-cards` | 检查卡片 `text_verbatim` 是否出现在对应块里；`cfeng` 有类似测试（>50 条卡片原文能在块里找到） |
| 提及 TEAM / WISeR 的文本拦截（计划） | `snf-criterion-cards` | 防止 Tier 3 内容被引用 |
| AI 生成的资格要求摘要 | `cfeng` | `snf_eligibility_requirements_GENERATED.md` |
| 原始病历文本进 git | `snf-criterion-cards` | `notes_raw.parquet`、`pool_notes_raw.parquet`（17.6 MB）等，`data/sample/` 合计约 50 MB |

## 4. 与第 ① 步直接相关的发现

- 我们分支的 `tests/test_sample.py` 来自 `snf-prior-auth`（`8202079`），`import snf_pa.data.config`，而这个模块只在两个队友分支里有。所以我们分支上 `pytest` **收集阶段就报错**（实测输出见汇报）。Hui Li 的 `config.py` 正是它对应的版本（`SAMPLE_DIR`、`CATEGORIES`、`MIN_AGE`、`MIN_MIDNIGHTS`、`SEED`、`sql_path`）。
- `test_sample.py` 断言的是旧抽样方案：5 类 × 60、SNF/HHC/HOME、排除观察期、午夜数 ≥3、test 占 38–46%。这些与设计 3.2 / 10.1 不一致（见 2.1）。
- 读原始数据：Hui Li 写死仓库内路径；cfeng 用 `MIMIC_ROOT` + physionet 下载布局。两者都不是 CLAUDE.md 规定的 `MIMIC_RAW_DIR`。两者都读 `.csv.gz`。
- `chromadb`：`cfeng` 的 `pyproject.toml` 仍保留 `chromadb`；它的索引不用 chroma（`rag/index.py` 自己存向量）。

## 5. 复核记录

subagent 报告里的以下结论我用 `git show` 逐条看过原文：

| 结论 | 复核位置 |
|---|---|
| Hui Li 的 `config.py` 写死 `data/mimiciv-3.1`，读 `.csv.gz` | `origin/snf-criterion-cards:src/snf_pa/data/config.py` L4–8 |
| Hui Li 排除观察期、午夜数 ≥3 作为纳入条件、日期差算法 | `cohort.py` L56、L60、L75、`eligible_filter()` |
| Hui Li 删除段落集合 | `redact.py` L17–18 |
| Hui Li strict 残余计数 | `data/sample/leakage_report.json` → `residue_strict` |
| cfeng `MIMIC_ROOT` 及目录布局 | `origin/cfeng:src/snf_pa/data/config.py` L8–11 |
| cfeng 主样本排除观察期和不足 3 午夜 | `cohort.py` L93–95 |
| cfeng 影像截断 `dischtime − 24h` | `imaging.py` L164 |
| cfeng 412.622 以 tier 3 进索引 | `rag/sources.py` |
| cfeng LLM 生成检索查询 | `rag/decompose.py` L65–76 |
| cfeng 探针评估集不排除 test | `leakage.py` L124–130 |
| cfeng 保留 `chromadb` 依赖 | `origin/cfeng:pyproject.toml` L7 |

其余细节（测试条数、各项计数、笔记里的 TODO）来自 subagent 的通读，未逐条复核；在对应步骤开工、真正对照时再核。

## 6. 队友留下的开放问题（摘录）

- Hui Li：HPI 里的入院前住所要不要遮蔽（SNF 40 篇 vs 回家 5 篇）；Social History 大多是 `___`，C6 常会 PEND；50 篇人工抽查未做；T_pa、事实卡、正反例推迟；政策 RAG 全部未实现；`SOURCES.md` 与 `step3_RAG_plan.md` 对 BPM 版本核对的说法不一致。
- cfeng：LLM span 检测作为第三层（未做）；评测集还没有人写的题；Hospital Course / Discharge Condition 含 T_pa 之后的文字（列为已知局限）；卡片编号待确认；人工盲审结果缺失；样本文件名和划分规则前后不一致。
