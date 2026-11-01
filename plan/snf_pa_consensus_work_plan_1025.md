# SNF 出院 Prior Authorization 审核系统：工作计划

| 项 | 内容 |
|---|---|
| 版本 | v4（2026-11-01），修订记录见附录 D |
| 分支 | `zhijie-plan-1025` |
| 状态 | 方案阶段，尚未写代码 |
| 数据 | MIMIC-IV v3.1（hosp / icu）+ MIMIC-IV-ED + MIMIC-IV-Note，只读 |

---

## 1. 目标

**一句话**：给定一位准备出院、拟转入 Skilled Nursing Facility（SNF，专业护理机构）的 Medicare 病人，判断他是否符合 SNF 覆盖的 prior authorization（PA，事先授权）要求；对符合的病人，帮医院准备 PA 申请材料包。

### 1.1 两个部分

| | Part 1：PA 资格审核（核心） | Part 2：PA 申请材料包 |
|---|---|---|
| 回答的问题 | 这个病人符不符合 Medicare SNF 覆盖标准？哪条符合、哪条不符合、为什么？ | 符合的话，提交给保险公司的材料怎么准备？ |
| 使用者 | **医院和保险公司都用** | 医院 |
| 输入 | 病人的住院病例 | Part 1 的审核结果 + 病例 |
| 输出 | 逐条标准结果 + 病历证据 + 政策条款 + 总体结论 | PDF 申请材料包 + FHIR 格式的电子申请 |
| 对应步骤 | Step 3–6（引擎），Step 8–13（真实数据验证） | Step 7 |

### 1.2 审核结果与后续动作

Part 1 对每条标准给出**逐条结果**，再由代码汇总成**总体结论**。

| 逐条结果（代码名） | 含义 |
|---|---|
| `MET` | 符合 |
| `NOT_MET` | 不符合 |
| `INSUFFICIENT` | 信息不足，无法判断 |

| 总体结论（代码名） | 含义 | 保险公司那边 | 医院那边（Part 2） |
|---|---|---|---|
| `APPROVE` | 所有标准都 `MET` | 建议批准 | 生成完整申请材料包 |
| `PEND_INFO` | 有标准 `INSUFFICIENT` | 向医院要补充材料 | 生成补材料清单（发给主治医生、PT 等）；补齐后重新审核，变成 `APPROVE` 再生成材料包 |
| `ADVERSE_RECOMMENDATION` | 有医疗必要性标准 `NOT_MET` | **不自动拒绝**，交给有执照的临床审核员决定 | 默认不生成，显示不符合的标准和理由；case manager 可人工覆盖后仍生成 |
| `TECHNICAL_NOT_MET` | 技术性条件不符合（如住院不足 3 个午夜） | 交非医师人员确认，并询问"过去 30 天是否有其他住院" | 同上 |

系统**永远不签发最终的拒绝决定**。

### 1.3 成功标准
1. 用 12–15 个合成病例完整演示 Part 1 和 Part 2，结果稳定、可重复。
2. 在 MIMIC 冻结测试集（200 例，其中 120 例有人工标注的 gold 标签）上给出 Part 1 的验证数字：逐条准确率、错误拒绝率、错误批准率。
3. Part 2 的材料包能"自洽"：交给保险视图重新审核，结论与医院侧一致（Step 7 的自检）。
4. 一套能给投资人看的 demo 和材料（Step 14）。

### 1.4 不在范围内
- 自动拒保。
- IRF（康复医院）等其他照护级别的判定。
- 真实医院系统对接（只做 FHIR 格式示意）。
- ROI 类指标（首次通过率、减少住院天数）：MIMIC 测不出，需要日后医院试点。

### 1.5 术语表

| 术语 | 说明 |
|---|---|
| MA / TM（FFS） | Medicare Advantage（商业保险公司经营的 Medicare 计划，需要 PA）/ Traditional Medicare（传统按服务付费的 Medicare，SNF 不需要 PA） |
| BPM Ch.8 | Medicare Benefit Policy Manual 第 8 章，SNF 覆盖的官方说明 |
| UM | Utilization Management，保险公司的用量审核部门 |
| case manager | 医院负责出院安排的人员 |
| home health | 居家医疗护理（另一种出院去向） |
| skilled nursing / skilled rehab | 必须由专业护士或治疗师提供的护理 / 康复 |
| daily basis | "每日"要求：护理每周 7 天，或康复每周至少 5 天 |
| practical matter | "实际上只能在 SNF 住院提供"这一要求 |
| custodial care | 生活照料（洗澡、穿衣等），不算 skilled |
| benefit period | Medicare SNF 福利的计算周期（每期最多 100 天） |
| Jimmo | Jimmo v. Sebelius 和解：不能因"无改善潜力"拒绝维持性的 skilled 服务 |
| nH Predict | 一款用住院天数预测做拒保的算法，引发诉讼，本项目明确不这样做 |
| plan profile | 一个 YAML 配置文件，写着某个保险计划的规则；本项目有 `strict_tm`（要求住院满 3 个午夜）和 `ma_waiver`（豁免 3 天） |
| `CaseBundle` | 审核引擎的**输入**：一个病例的全部内容（时间线、病历文本、结构化事实卡、影像报告） |
| 申请材料包 | Part 2 的**输出**：医院提交给保险公司的材料。保险视图审核时先把它转成 `CaseBundle` |
| `view` | 引擎参数：`provider`（医院视图）或 `payer`（保险视图） |
| T_pa | 模拟的 PA 提交时刻，默认出院前 24 小时；只用这之前的数据 |
| span ID | 病历中每个句子 / 条目的稳定编号，引用证据时只用编号 |
| 事实卡 | 由结构化数据生成的一句话证据，例如"出院前 48h 内静脉万古霉素已给 4 次" |
| gold / dev-gold / test-gold | 人工按标准逐条标注的"标准答案"；dev-gold 用于开发，test-gold 用于最终评估 |
| 主设定 / realistic 设定 | 主设定遮蔽会泄露出院去向的内容；realistic 设定加回 PT 的去向建议等，作对照 |
| POE | MIMIC 中的医嘱表（provider order entry），可查到"转为住院"医嘱的时间 |
| TEAM | CMS 2026 年起的一个支付模型，对部分手术豁免 3 天规则；本项目不采用 |
| NDMC | 保险公司拒绝时需发给病人的书面通知 |
| Fable | 规划阶段用来仲裁分歧的模型（附录 B） |

---

## 2. 背景与定位

### 2.1 为什么按"MA 的 PA 流程 + TM 的覆盖标准"来做
- TM 本身不对 SNF 做 PA；需要 PA 的是 MA 计划。
- CMS-4201-F（§422.101(b)(c)）要求 MA 必须沿用 TM 的覆盖标准，所以判定依据统一为 **42 CFR 409.30–409.36 + BPM Ch.8**，可以逐条引用。
- MIMIC 的 `insurance='Medicare'` 不区分 TM 和 MA，所以 3 天规则做成可配置的 plan profile（D2）。

### 2.2 医院和保险公司：不同在哪
两边看的是同一套东西：同一份标准、同一类病历证据、同一批政策条文，所以 Part 1 的引擎共用。差别如下：

| | 医院 | 保险公司 |
|---|---|---|
| Part 1 输入 | 完整病历 | **只有医院提交的申请材料包**；没提交的就当不存在 |
| Part 1 结论怎么用 | 提交前预审：能不能批、哪条有问题 | 建议结论交审核员签字；按 CMS-0057-F 时限（72 小时 / 7 天）处理 |
| Part 2 | 生成申请材料包 | 不适用 |
| 关心的指标 | 首次提交通过率、等授权的滞留天数、case manager 用时 | 审核员用时、决定一致性、申诉推翻率 |
| 监管压力 | 低 | 高（§422.566(d)、CMS 2024-02 FAQ） |

暂以医院为主线讲故事，保险视图作为第二视图（实现方式见 D15）。

### 2.3 投资人视角

| 投资人会问 | 回答 / 对应产出 |
|---|---|
| 解决谁的什么痛点？ | MA 的 SNF PA 拒绝在申诉后 95% 被推翻（OIG 2026）；CMS 要求 72 小时 / 7 天内决定（2026-01-01 起）；2027 年起保险公司须提供电子 PA API |
| 准确率多少？ | MIMIC 冻结测试集上的逐条准确率、错误拒绝率、错误批准率（Step 13） |
| 安全吗？会不会乱拒？ | 永不自动拒绝；Jimmo 安全测试；每条结论都可追溯到病历原文和条款 |
| 为什么是现在？ | CMS-0057-F 的 2026 / 2027 两个时间点；SNF 拒绝正受 OIG 和国会关注 |
| 和竞品有何不同？ | 专注 SNF；逐条可解释、可审计；规则可按保险计划配置；可私有化部署；FHIR 输出 |
| 能接进医院系统吗？ | 引擎只认 `CaseBundle`，FHIR 适配器已做（Step 3）；输出 FHIR 申请（Step 7） |
| 部署和数据安全？ | 正式运行走 AWS Bedrock；也可用本地模型私有化部署（D14） |
| 还缺什么？ | ROI 需要医院试点才能证明 |

- 不宣称"批准率提升 X%"这类 MIMIC 测不出的指标。
- 不把产品讲成"自动拒保"。
- 主要竞品（上线前再核对）：Optum / naviHealth、WellSky（含 CarePort，自 2026-01 起为部分 MA 计划管理 post-acute PA）、Cohere Health（2025 年 C 轮 9,000 万美元）、Waystar、Infinitus。

---

## 3. 系统总览

### 3.1 数据流

```
   病例来源：MIMIC 适配器 │ FHIR 适配器 │ 保险视图：医院提交的申请材料包
                              ▼
                     CaseBundle（统一输入）
                              ▼
   ┌──────────── Part 1：PA 资格审核引擎 ────────────┐
   │ intake_rules       代码：C0–C2、时间线、T_pa         │
   │ abstractor         LLM：抽取证据，只输出 span ID     │
   │ criteria_reviewer  LLM：逐条判定 C3–C6               │
   │ aggregator         代码：按 plan profile 汇总总体结论 │
   │ critic             LLM：复核非 APPROVE + 随机 20% APPROVE │
   └──────────────────────────┬─────────────────────┘
                              ▼
          逐条结果 + 证据 + 条款 + 总体结论 + 结论说明
               ┌──────────────┴──────────────┐
          view=provider                 view=payer
               ▼                             ▼
   Part 2：申请材料包 / 补材料清单      审核员队列（人工签字）
```

### 3.2 审核标准

| ID | 标准 | 条文 | MIMIC 能否判定 |
|---|---|---|---|
| C0 | Medicare Part A 资格 | — | 代理：insurance + 年龄 ≥65 |
| C1 | 连续 ≥3 个住院午夜（出院日不算；ED 和观察期不算） | §409.30(a)；Ch.8 §20.1 | 代码计算 |
| C2 | 出院 30 天内入住 SNF | §409.30(b)；§20.2 | 假定满足 |
| C3 | SNF 照护针对住院期间治疗过的病情 | §409.31(b)(2) | 诊断 + 病历 |
| C4 | 需要 skilled nursing 或 skilled rehab | §409.31(a)、§409.32、§409.33；§30.2–30.4 | **核心 LLM 判断** |
| C5 | daily basis | §409.34；§30.6 | 推断 |
| C6 | practical matter | §409.35；§30.7 | 推断，常为 `INSUFFICIENT` |
| C7 | 医师认证 | §424.20；§40 | 无数据 → 假定已提交 |
| C8 | benefit period 剩余天数 | §409.61 | 只能看到本院 → 假定 |

**跨条护栏**（写进 critic 规则）：
- Jimmo：不能以"无改善潜力 / 已到平台期"拒绝。
- custodial care（§30.5）不算 skilled。
- 不能凭诊断本身推定 skilled。
- 不能用住院天数预测作拒绝依据。

### 3.3 标准 → MIMIC 数据来源

| 标准 | 主要表 / 字段 | 注意 |
|---|---|---|
| C0 | admissions.insurance；patients.anchor_age / anchor_year | 不区分 TM / MA |
| C1 | poe ⨝ poe_detail（Admit category）；admissions；transfers.careunit；edstays | ED 和观察期不计 |
| C2 / 前序住院 | admissions 自连接；admission_location | 只能看到本院 |
| C3 | diagnoses_icd；ED triage、diagnosis；出院小结 HPI / Hospital Course；影像报告 | 不用 drgcodes（出院后编码） |
| C4 / C5（护理） | prescriptions（+emar）给药途径；poe（PICC / TPN / 鼻饲 / 伤口 / 氧疗）；chartevents 压疮（仅 ICU）；病历 | 只用 T_pa 前；看持续性 |
| C4 / C5（康复） | poe PT / OT / Speech 会诊、Activity 医嘱；services；procedures_icd；病历功能描述 + Activity Status | PT 去向建议句按 D7 遮蔽 |
| C6 | Social History；ED arrival_transport；功能状态 | 常缺 → `INSUFFICIENT` |
| C7 | 无 | 假定已提交 |

---

## 4. 关键设计决策

由三位独立规划者辩论、仲裁后确定（附录 B），之后按项目负责人的确认做过调整（第 7 节）。决策依据中的数据见附录 A。

### 4.1 判定规则
| # | 决策 |
|---|---|
| D1 | 总体结论四类（1.2 节），系统永不签发最终拒绝。 |
| D2 | 规则写在 plan profile 里，代码不硬编码。换规则或新增某个保险计划只加 YAML；每次运行把 profile 名和 hash 写进 trace。默认 `strict_tm`，`ma_waiver` 结果并列报告。TEAM 豁免不进实验。字段见下方。 |
| D3 | **C1 午夜数**从最早、未撤销的 POE "Admit to inpatient" 医嘱时间起算；医嘱后在 ED 等床的时间计入；ED 和观察期不计。没有该医嘱时退回入院时间并打标记，给出上下界；上下界跨过 3 → C1 为 `INSUFFICIENT`。 |
| D4 | **技术性不符**：在 `strict_tm` 下，同时满足 (a) 有未撤销的住院医嘱、(b) 午夜上下界都 <3、(c) 30 天内没有合格的前序住院，才判 `TECHNICAL_NOT_MET`；否则 C1 为 `INSUFFICIENT`。结论说明写明理由码和条款（§409.30(a)）。 |
| D5 | **C3–C6 对所有病例都跑**，包括 C1 不符的，这样切换 profile 只需重新汇总，不必重跑 LLM。 |

D2 的 profile 字段：

```yaml
three_day_rule: required          # strict_tm 为 required，ma_waiver 为 waived
qualifying_stay_lookback_days: 30
assume_no_other_qualifying_stay: true
auto_technical_noncoverage: true
physician_cert: assume_submitted
critic_approve_sample_rate: 0.2
```

### 4.2 数据与证据
| # | 决策 |
|---|---|
| D6 | **T_pa** = max(出院时间 − 24h, 住院起点)，−48h 做敏感性分析。结构化数据和影像报告只用 T_pa 之前的。 |
| D7 | **主设定的病历输入**：保留 CC / HPI / PMH / Social Hx / PE / Pertinent Results / Hospital Course + Discharge Condition（Activity / Mental Status，作为出院时功能状态的代理）。删除 Disposition / Facility / Discharge Instructions / Followup / Discharge Diagnosis / Discharge Medications。遮蔽去向句和 PT/OT"建议去 rehab/SNF"的半句。用药证据改用 T_pa 前的事实卡。 |
| D8 | **realistic 设定**：加回 PT/OT 建议句和去掉机构名后的 Discharge Medications；另做"去掉 Activity Status"的敏感性对照。 |
| D9 | **引用**：病历预先切成带 span ID 的句子 / 条目（如 `DS:HC:s14`、`RX:<pk>`）；LLM 只输出 span ID + ≤8 词的锚点短语；代码校验锚点在该 span 中并回填原文，模型无法编造引用。 |

### 4.3 引擎
| # | 决策 |
|---|---|
| D10 | **固定流程（LangGraph），不让 LLM 自由调度**，节点见 3.1 节。每例约 2.5–2.7 次 LLM 调用。编排、政策检索、结论说明都不是 agent（分别是代码、检索工具、模板）。 |
| D11 | **病历检索**：整份处理后的出院小结直接放进上下文；单病例 BM25 只用于影像报告、事实卡和超长病历。 |
| D12 | **解码**：abstractor 温度 0 + JSON schema 约束 + 重复惩罚 + 输出长度上限；criteria_reviewer / critic 温度 0 单次。自一致性 ×3 只有在 dev 上证明有用时才启用。 |
| D13 | **引擎与数据源解耦**：引擎只认 `CaseBundle`；MIMIC 和 FHIR 各写一个适配器；引擎代码里不出现 MIMIC 表名。 |
| D14 | **模型可插拔**：统一的 LLM provider 接口，按角色配置。POC 用 Claude Code 订阅和 OpenAI（Codex）订阅，本地 qwen3:14b 作私有化部署对照；之后切换 AWS Bedrock（M5），切换只改配置，在同一测试集上对比结果作为验收。 |
| D15 | **`view` 参数**：`provider` 用完整病历，输出接 Part 2；`payer` 只用申请材料包，输出接审核员队列。其余引擎逻辑相同。 |

### 4.4 评估
| # | 决策 |
|---|---|
| D16 | **队列**：Medicare、入院 ≥65 岁、出院存活、anchor 年份桶 2011–2018、有出院小结、每人只取一次住院；测试集只取有 POE 住院医嘱的病例。 |
| D17 | **规模**：dev 100（含 dev-gold 20–30）/ 冻结 test 200（含 test-gold 120，其中 30 例双人标注），共 300。 |
| D18 | **主指标**是 gold 上的逐条准确率和错误率，以出院去向为标签的指标只作参考。具体定义见 Step 13。 |

---

## 5. 工作计划

### 5.1 路线图

| 里程碑 | 步骤 | 能看到什么 |
|---|---|---|
| M0 地基 | Step 0–2 | 模型接口、审核标准卡片、两个 profile |
| M1 Part 1 跑通 | Step 3–6 | 合成病例上端到端出审核结论 |
| M2 Part 2 + Demo v1 | Step 7 + Step 14 的页面 1–4、6 | 可以给朋友或顾问看的 demo |
| M3 真实数据验证 | Step 8–13（先用 dev-gold 出初步数字） | Validation 页初步数字 |
| M4 投资人版 | test-gold 补齐并冻结；Step 14 其余部分 | 完整 demo + deck + 技术报告 |
| M5 迁移 | 加 Bedrock provider，同一测试集上对比，通过后切换 | 可部署的正式版本 |

**依赖**：M1、M2 只用合成病例，不依赖 MIMIC，可以先做；M3 可与 M1–M2 并行。Step 3 的 MIMIC 适配器要等 Step 9–11 完成后接上。

### 5.2 阶段 A：地基

#### Step 0 — 仓库整理与模型接口（1 天）
- **目标**：代码可复现、能入库；三种模型都能调用。
- **做法**：
  1. `.gitignore` 里的 `data/` 改为 `/data/`。现在它把 `src/snf_pa/data/` 也忽略了，抽样代码（`config.py`、`cohort.py`、`build_sample.py`）不在仓库里，别人 clone 后 `tests/test_sample.py` 会缺依赖。先确认本地文件还在，再入库。
  2. 数据路径统一配置：原始数据根目录 `E:/project data/AgentResearch/raw`（只读），读**未压缩的 `.csv`**；派生数据写仓库内的 `derived/`。`derived/`、`traces/`、`data/` 不进 git。
  3. 样本量对齐：`test_sample.py` 期望 300，`step 0 plan.txt` 写的是 50 → 按 D17 统一（Step 10 重抽后改测试）。
  4. 目录：`src/snf_pa/engine/`（审核引擎）、`src/snf_pa/adapters/{mimic,fhir}/`、`src/snf_pa/packet/`（Part 2）、`research/`（MIMIC 验证脚本）、`demo/`（合成病例与 UI）。现有空的 `agents/ graph/ rag/ tools/` 并入 `engine/`。
  5. LLM provider 接口：统一为"prompt + JSON schema → 结构化 JSON"，按角色配置模型。先实现三个：
     - Ollama（本地 qwen3:14b）；
     - Claude：`claude -p "<prompt>" --output-format json --json-schema '<schema>'`，结果在返回 JSON 的 `structured_output` 字段，没有就重试。**不要加 `--bare`**（它不读订阅登录）。用 `--permission-mode dontAsk`、尽量少的工具，在一个干净的空目录里调用；
     - OpenAI：`codex exec "<prompt>" --output-schema ./schema.json -o ./out.json --ephemeral`；
     - Bedrock 留好位置（`langchain-aws` 已在依赖里）。
  6. trace 统一写本地 JSONL（`traces/`）。
- **完成标准**：新 clone 后 `pytest` 可运行（缺数据时跳过）；抽样代码已入库；三个 provider 对同一个合成 prompt 都返回合法 JSON。

#### Step 1 — 速度基准（半天）
- **目标**：知道每个模型跑一例要多久。
- **做法**：用合成病例测每个 provider 的单次调用耗时和单例总耗时（长调用约 4k 输入 + 1k 输出；短调用约 1.5k 输入），以及订阅的额度消耗。本地模型显式设 `num_ctx=16384`。
- **注意**：Arc 140V 上 llama.cpp 有不稳定报告；订阅有速率限制，要估算批量跑 200 例需要多久。
- **完成标准**：每个模型的"秒 / 调用"和"分钟 / 例"写进 manifest。

#### Step 2 — 审核标准卡片与 plan profile（2–3 天）
- **目标**：把法规翻译成机器可用、可引用的标准；这同时就是 gold 标注手册。
- **做法**：
  - 为 C0–C8 各写一张 YAML 卡片：定义、条文 ID、2–3 个正例和反例（取自 BPM §30.2–30.4）、版本 / 生效日期。
  - 拒绝理由码表：每个码对应一条标准和一个 CFR 条款（CMS-0057-F 要求写明具体理由）。
  - 写 `profiles/strict_tm.yaml` 和 `profiles/ma_waiver.yaml`。
- **注意**：核对本地 `policy_docs/bp102c08.pdf`（Rev. 12283，2023-10-05）是否最新；按 2026 年规则判定；措辞用"licensed clinical reviewer"（§422.566(d) 原文为 physician *or other appropriate health care professional*）。
- **完成标准**：C0–C8 都有卡片；理由码表和两个 profile 完成。

### 5.3 阶段 B：Part 1 审核引擎（先在合成病例上跑通）

#### Step 3 — `CaseBundle` 与适配器（2–3 天）
- **目标**：所有病例来源都转成统一输入。
- **做法**：
  - 定义 `CaseBundle`（Pydantic）：人口学；时间线（入院、观察医嘱、住院医嘱、ED 时段、出院、T_pa）；带 span ID 的分段病历；事实卡（带来源主键或 FHIR resource id）；影像报告；`source`（mimic / fhir / submitted_packet）。
  - FHIR 适配器：FHIR Bundle → `CaseBundle`（合成病例走这里，以后接医院 EHR 也走这里）。
  - MIMIC 适配器：Step 9–11 的产物 → `CaseBundle`（阶段 D 完成后接上）。
- **完成标准**：合成病例能转成合法的 `CaseBundle`。

#### Step 4 — 合成病例库（3–5 天）
- **目标**：给开发、单元测试和 demo 提供专门设计、结果可控的病例。
- **做法**：写 12–15 个合成病人，每个展示一项能力：

| 病例 | 展示的能力 | 预期总体结论 |
|---|---|---|
| 髋骨折术后，需每日 PT + 抗凝注射 | 典型批准 | `APPROVE` → 生成材料包 |
| 肺炎后体能下降，病历里没有 PT 评估 | 发现缺口 | `PEND_INFO`；补上 PT 评估后变 `APPROVE` |
| 只需要协助洗澡穿衣 | 识别 custodial care | `ADVERSE_RECOMMENDATION` |
| 住院 2 个午夜 | 技术性不符；切换 profile | `TECHNICAL_NOT_MET`；`ma_waiver` 下进入医疗审查 |
| 先观察后住院，卡在 3 午夜边界 | C1 按住院医嘱计算 | 视时间而定 |
| 帕金森，"已到平台期"，需维持性 skilled therapy | Jimmo 陷阱 | `APPROVE` 或 `PEND_INFO`，绝不 `ADVERSE_RECOMMENDATION` |
| 新鼻饲管 + 伤口负压治疗 | 每日 skilled nursing | `APPROVE` |
| 卒中，独居，无照护者 | practical matter 满足 | `APPROVE` |
| 心衰，可以回家接受 home health | practical matter 不满足 | `ADVERSE_RECOMMENDATION` 或 `PEND_INFO` |
| 其余：IV 抗生素疗程、从 SNF 入院、认知障碍等 | | |

  - 格式：FHIR 风格 JSON Bundle（Patient、Encounter、Condition、MedicationRequest、ServiceRequest、Observation；出院小结放在 DocumentReference）。
  - 生成：用 Claude Code / Codex 按场景写，人工审校临床合理性；可参考 MIMIC 出院小结的写法；人口学可用 Synthea 生成。
  - 刻意放入缺失信息、矛盾记录和长病历，避免 demo 效果好于真实情况。
- **完成标准**：全部病例通过 FHIR 适配器；预期结论写成 pytest 回归测试。

#### Step 5 — 政策检索（RAG）（3 天）
- **目标**：判定时能检索并引用到具体条款。
- **语料分级**：
  - Tier 1（有约束力）：42 CFR 409.30–36、409.60–61、424.20；422.101(b)(c)、422.566、422.568、422.570–572、422.138。
  - Tier 2（官方指导）：BPM Ch.8（重点 §20、§30）；CMS 2024-02-06 MA coverage criteria FAQ；Jimmo 和解说明；Parts C&D 申诉指南；NDMC 要求。
  - Tier 3（只作背景，判定时不得引用）：CMS-0057-F；TEAM 3 天豁免；WISeR（只适用 TM、不含 SNF）；州法；OIG / 参议院报告。
- **做法**：以 `tests/check_rag.py` 已有的切块、bge-m3、BM25、RRF 为基础；按 § 切块，§409.33 和 §30.2–30.4 的举例列表整段保留；metadata 含 tier、生效日期、URL。以标准卡片直接绑定条文为主、检索为辅；recall@5 < 0.9 时再加 reranker。
- **完成标准**：约 40 条"问题 → 应命中的条款"测试集 recall@5 ≥ 0.9；Tier 3 不被引用的测试通过。

#### Step 6 — 审核引擎（LangGraph）（5–7 天）
- **目标**：实现 3.1 节的 Part 1 流程。
- **做法**：

```
START → load_case          [代码：读取 CaseBundle，按 view 限定输入范围]
      → intake_rules       [代码：C0–C2、时间线、T_pa；读 plan profile]
      → abstractor         [LLM：按 §409.33 类别抽证据 {span_id, anchor_phrase, claim, assertion}]
      → citation_resolver  [代码：校验锚点、回填原文；失败的证据作废]
      → criteria_reviewer  [LLM：输入证据 + C3–C6 卡片 + 政策检索；
                            每条输出 {MET | NOT_MET | INSUFFICIENT, evidence_ids, policy_refs, rationale}]
      → aggregator         [代码：按 profile 汇总总体结论；可同时算多个 profile]
      → critic             [LLM：所有非 APPROVE + 随机 20% APPROVE；最多退回 criteria_reviewer 1 次
                            检查：缺证据 ≠ 反面证据；Jimmo；custodial；证据与结论矛盾；漏看的 skilled 信号；拒绝理由是否具体]
      → explain            [模板：结论说明 + 理由码 + 补材料清单]
      → view=provider → Step 7（Part 2）
        view=payer    → 审核员队列（ADVERSE_RECOMMENDATION 用 interrupt 等人工签字）
```

  - State：`CaseState{case_id, view, profile, eligibility, evidence[], criteria{cid: 逐条结果}, decision{profile: 总体结论}, critic_findings, human_review, cost}`。
  - 解析失败最多重试 2 次；批量运行加限速和断点续跑（checkpointer）。
  - FastAPI 接口：提交病例、查结果、人工复核、补材料后重审。
- **完成标准**：全部合成病例跑出预期结论；schema 100% 合法；span ID 100% 可解析。

### 5.4 阶段 C：Part 2 申请材料包

#### Step 7 — 申请材料包生成（4–6 天）
- **目标**：对 `APPROVE` 的病例生成可提交的材料；对 `PEND_INFO` 的病例生成补材料清单。触发规则见 1.2 节。
- **材料包内容**：
  1. 病人与住院概要（诊断、手术、住院经过要点）。
  2. 时间线：入院、住院医嘱、午夜数、拟出院和入住 SNF 日期。
  3. 逐条标准：结果 + 病历原文证据（由 span ID 回填）+ 条款引用。
  4. 拟在 SNF 提供的 skilled 服务：项目和频率（对应 C4 / C5，如"每日 PT 60 分钟、每周 5 天"）。
  5. 功能状态与照护环境（对应 C6）。
  6. 医师认证占位（待签字）。
  7. 附件清单：相关病历节选、影像报告、用药记录。
- **格式**：
  - PDF（给人看）。
  - FHIR Bundle（Da Vinci PAS 风格的 Claim，支持材料放在 supportingInfo），只做格式示意，不追求通过官方校验。
- **补材料清单**：按 `INSUFFICIENT` 的标准列出具体需要什么、建议找谁（主治医生、PT、社工）；补齐后一键重审。
- **自检**：把生成的材料包转成 `CaseBundle`，用 `view=payer` 重跑 Part 1，结论应与医院侧一致；不一致说明材料包漏了关键证据。
- **完成标准**：合成病例中所有 `APPROVE` 都生成材料包且自检一致；`PEND_INFO` 病例补材料后能变 `APPROVE` 并生成材料包；MIMIC 测试集上报告自检一致率（Step 13）。
- **后续扩展**（不在本期）：保险拒绝后自动起草申诉信。

### 5.5 阶段 D：用 MIMIC 真实数据验证 Part 1

#### Step 8 — 一次性抽取 Parquet（2–3 天）
- **目标**：之后的步骤不再读原始 CSV。
- **做法**：
  - DuckDB：`memory_limit=16GB`，临时目录放 SSD，8 线程；不用 pandas。
  - 先建候选池 `cohort_hadm.parquet`（约 4 万个住院），再把每张大表按候选池过滤、只取需要的列，存成 zstd Parquet（按 hadm_id 排序）。
  - hosp：admissions、patients、transfers、services、diagnoses_icd、procedures_icd、prescriptions、pharmacy、emar（与 pharmacy 关联取给药途径；只计 Administered / Started / Delayed Administered）、poe + poe_detail、labevents（白名单：WBC、Hb、Cr、INR、白蛋白、血糖、乳酸）。
  - icu：icustays、chartevents（单次扫描，itemid 白名单：Braden Activity / Mobility 224056 / 224057、Gait / Transferring 227345、Ambulatory aid 227343、Risk for Falls 223754、压疮系列、OT Notes 227848 等）。
  - ED：edstays、triage、diagnosis。note：discharge、radiology、radiology_detail。
  - drgcodes 不作为输入（出院后编码），只用于分析。
- **注意**：`read_csv` 调大 `max_line_size`；`*_detail` 表显式指定类型；写 manifest（行数、源文件 mtime / sha）。
- **完成标准**：Parquet 总量 <5GB；manifest 能复现附录 A 的计数。

#### Step 9 — MIMIC 时间线（2–3 天）
- **目标**：从 MIMIC 表里取出时间点，填进 `CaseBundle`。C1 的计算在引擎的 intake_rules 里。
- **做法**：
  - 住院医嘱时间：最早、未撤销（`transaction_type='New'`）的 "Admit to inpatient"；观察医嘱："Place in observation"；观察病房时段来自 transfers；ED 时段来自 edstays 或 admissions.edregtime / edouttime。
  - 前序住院：同一病人 30 天内有 ≥3 午夜的出院。
  - 标记：从 SNF 入院、60 天内曾从 SNF 出院。
  - 入院年龄：anchor_age + （入院年 − anchor_year）。
- **注意**：真实年份由 anchor 年份桶推算，有 ±2 年误差；院外住院看不到，走补材料询问，不直接判不符；所有数据按 T_pa 截断，在适配器层强制。
- **完成标准**：每条规则有单元测试；能复现"38,828 → 37,337"（附录 A）。

#### Step 10 — 队列与抽样（2 天）
- **目标**：按审核难度分层抽样，并冻结测试集。纳入条件见 D16，规模见 D17。
- **分层**：
  - 临床场景：骨科术后（髋骨折 / 关节置换）、卒中、内科病后体能下降（非手术主诊断 + 有 PT 会诊 + 非骨科非卒中；MA 拒绝最集中，加大权重）、心衰、伤口 / IV 抗生素 / 新鼻饲管。
  - 出院去向：SNF；home health（难负例，多抽）；HOME（分有无 PT / OT 会诊）；REHAB / IRF 小层（dev 20 / test 20，按 SNF 标准评估，预期 C4 / C5 多为 `MET`，不当负例）。
  - 边界层（多抽）：先观察后住院；<3 午夜去 SNF（分有无前序住院）；从 SNF 入院；ICU / 非 ICU。
  - 髋骨折几乎都去 SNF（1,017 去 SNF，9 回家，46 home health）→ 单独报告，不计入总体。
- **注意**：每人只取一次住院；主结果按层不加权，加权推算到总体只作次要；测试集冻结后开发中不能看。
- **完成标准**：manifest 写清每层候选数和抽样数；`test_sample.py` 按新设计更新并通过。

#### Step 11 — 病历处理与去泄漏（4–5 天）
- **目标**：生成 MIMIC 病例的 `CaseBundle` 内容，并确保不泄露出院去向。
- **做法**：
  1. 出院小结按标题切段、保留字符偏移，再切到句子，分配 span ID；按 D7 保留和删除段落。
  2. 遮蔽去向句：rehab、extended care、SNF、nursing facility、"___ facility"、discharge to、placement、screened、accepted at、bed offer、case management arranged、PT recommends [去向] 等。
  3. 影像报告：只取 T_pa 之前的，按 FINDINGS / IMPRESSION 切块。
  4. 事实卡：每条标准一个 SQL 模板，输出一句话 + 主键。要量化（天数、是否仍在用），不只是有 / 无。用药以 prescriptions 为主，emar 作补充（卡片标 `emar_available`）。
  5. 记录每例缺了哪些真实申请材料会有的内容（PT / OT 评估、家庭支持、医师认证等）。
- **泄漏检测**：
  - TF-IDF + 逻辑回归预测出院去向（SNF vs home health），整体和逐段各做一次；Discharge Medications 单段 AUC > 0.70 即确认删除；统计 "RX … Disp … Refills" 行在各去向的出现率。
  - 让 LLM 直接猜去向，看命中率。
  - 人工抽查 50 篇。
- **注意**：MIMIC 没有逐日病程记录，"PA 提交时刻"的模拟不完全真实，写进局限。
- **完成标准**：残余去向词为 0；主设定和 realistic 设定两套输入可复现；每张事实卡能按主键回查。

#### Step 12 — Gold 标注（2–4 周，可与 Step 13 前半并行）
- **目标**：得到逐条标准的人工"标准答案"。
- **做法**：
  - 标注手册就是 Step 2 的标准卡片。
  - 每例逐条标注 `MET` / `NOT_MET` / `INSUFFICIENT` + 证据 span，再分别按 `strict_tm` 和 `ma_waiver` 给出总体结论。
  - 先标 30 例 dev-gold；test-gold 120 例在有时间或找到临床标注者后补，其中 30 例双人独立标注，算 Cohen's κ（目标 C4–C6 κ ≥ 0.6）。
  - 标注者看同一份处理后的输入，不看系统输出。
  - 标注工具：一个简单页面，逐条点选 + 选中 span。
  - 在 MIMIC dev 上调 prompt 要在 dev-gold 标完之后进行。
- **完成标准**：gold 文件冻结；κ 有报告。test-gold 完成前，Step 13 的数字标为"初步"。

#### Step 13 — Part 1 评估（1–2 周，主要是机器时间）
- **目标**：给出 Validation 页和技术报告需要的数字。
- **指标**（每项按 profile 分别报告，带 95% 置信区间）：
  - 错误拒绝率：系统给 `ADVERSE_RECOMMENDATION`，gold 为 `APPROVE`。
  - 错误批准率：系统给 `APPROVE`，gold 有核心标准为 `NOT_MET` 或 `INSUFFICIENT`。
  - 过度补材料率：系统给 `PEND_INFO`，gold 为 `APPROVE`。
  - 逐条准确率 / macro-F1：约 480 个判定，按病例做 bootstrap。
  - 反事实安全测试：删掉 skilled 证据 → 应变 `PEND_INFO` 或 `ADVERSE_RECOMMENDATION`；午夜数改为 2 → 应判 `TECHNICAL_NOT_MET`；加一句"no rehab potential" → 不得转为拒绝（Jimmo）；删掉 Activity Status → 看敏感性。
  - 引用：可解析率；支持率（LLM 评审 + 30 例人工）；遗漏率（用 gold span 召回测）。
  - 公平性：按种族、语言、性别、年龄段比较 `ADVERSE_RECOMMENDATION` 率和 `PEND_INFO` 率。
  - Part 2 自检一致率（Step 7）。
  - 次要：以出院去向为标签的 AUROC（分层）；每例耗时和成本。
- **对照实验**（必做；编号沿用完整设计，A2–A4 为可选）：

| ID | 配置 | 回答的问题 |
|---|---|---|
| A0 | 结构化特征 + TF-IDF 逻辑回归 | 到底需不需要 LLM；去向标签测的是不是资格 |
| A1 | 单次 LLM 调用，整份病历，不给政策 | 模型凭常识能做到多少 |
| A5 | 完整系统，本地 qwen3:14b | 私有化部署版本的水平 |
| A6 | 完整系统，订阅强模型（Claude、OpenAI 各一次） | 上限，以及两家比较 |

  - 可选（以后写论文时做）：A2（A1 + 全部标准卡片）、A3（单 agent + 检索工具）、A3+SC（与完整系统算力对齐的自一致性）、A4（每条标准单独抽取和判定）、检索方式对照、完整公平性分析。
- **统计**：配对 McNemar、配对 bootstrap；决策级 n=120 只能检出约 10–12 个百分点以上的差异。
- **完成标准**：Validation 页所需数字全部来自冻结的测试集。

### 5.6 阶段 E：Demo 与投资人材料

#### Step 14 — 产品 demo（2–3 周）
- **目标**：一个能现场跑、5–8 分钟讲完的 demo，演示病例用 Step 4 的合成病例。
- **技术栈**：后端 FastAPI 包住引擎和材料包生成；前端先用 Streamlit，需要更像产品时换 React / Next.js；POC 本地运行，之后部署到 AWS（模型换 Bedrock）。
- **页面**：
  1. 病例队列：待出院病人列表，每行显示总体结论和"还缺什么"。
  2. 审核详情（Part 1）：
     - 逐条标准清单 C0–C8（C2、C7、C8 显示为"假定"），绿 / 黄 / 红；
     - 点任一条，右侧高亮病历原文，并弹出条款原文；
     - 时间线：入院、住院医嘱、午夜数、T_pa；
     - profile 下拉框（`strict_tm` ↔ `ma_waiver`），切换后结论即时变化。
  3. 补材料清单：`PEND_INFO` 时显示，补齐后重审。
  4. 申请材料包（Part 2）：预览、下载 PDF 和 FHIR Bundle。
  5. 保险视图：同一病例在保险侧的审核结果 + 待审核员签字；与医院侧对比。
  6. 审计轨迹：每一步用了哪个模型、哪个 profile、耗时、引用了哪些 span 和条款。
  7. Validation 页：Step 13 的指标与安全测试结果。
- **Demo 脚本（5–8 分钟）**：
  1. 问题（30 秒）：SNF 拒绝在申诉后 95% 被推翻；CMS 要求 7 天内决定，2027 年起要电子 API。
  2. 审核髋骨折病例：逐条结果、证据和条款，结论 `APPROVE`（1.5 分钟）。
  3. 一键生成申请材料包，预览 PDF 和 FHIR（45 秒）。
  4. 肺炎体能下降病例：结论 `PEND_INFO`，指出缺 PT 评估；补上后重审变 `APPROVE`（1 分钟）。
  5. Jimmo 陷阱病例：病历写了"无改善潜力"，系统没有拒绝，并解释原因（45 秒）。
  6. 切换 profile：2 个午夜的病例在两种规则下的不同结论（30 秒）。
  7. 保险视图：同一份材料包在保险侧得到一致结论；建议拒绝只能由审核员签字（1 分钟）。
  8. Validation 页：真实数据上的准确率与安全测试（1 分钟）。
  9. 下一步：医院试点、FHIR 对接、迁移到 AWS Bedrock。
- **投资人材料**：约 10 页 pitch deck（问题、为什么是现在、产品、demo 截图、验证结果、竞品、商业模式假设、里程碑）；一页技术报告摘要（验证方法与局限）；竞品对比表。
- **完成标准**：合成病例回归测试全过；完整走一遍 demo 脚本不出错；Validation 页数字来自冻结测试集。

---

## 6. 风险与局限

| 风险 / 局限 | 应对 |
|---|---|
| 没有真实 PA 标签；出院去向 ≠ 是否符合覆盖 | gold 逐条标注为主；A0 基线揭示去向标签测的是什么 |
| 出院小结写于出院后，没有逐日病程记录 | 结构化数据按 T_pa 截断；删 Discharge Medications；写进局限 |
| 缺 PT / OT 评估 | Activity Status 作代理；缺失时给 `PEND_INFO`，不转拒绝 |
| 标签泄漏 | 三种泄漏检测 + 主设定 / realistic 两套输入 |
| 订阅额度和速率限制 | 限速 + 重试 + 断点续跑；两家 provider 互为备份 |
| 订阅模型与 Bedrock 模型结果不一致 | M5 在同一测试集上对比，差异过大先调 prompt 再切换 |
| 本地算力和 Arc 驱动不稳定 | 主力用订阅模型；本地只作对照 |
| gold 标注人力 | 先 dev-gold；test-gold 后补；没有临床人员时降级表述 |
| 政策版本变化 | 语料带生效日期，固定版本 |
| "AI 拒保"的舆论风险 | 医院为主线；永不自动拒绝；Jimmo 测试放进 Validation 页 |
| 合成病例太"干净" | 刻意放入缺失、矛盾和长病历；验证数字只用 MIMIC |
| 其他局限 | TM / MA 不可区分；院外住院看不到；anchor 年份有误差；ROI 需要试点 |

---

## 7. 决策状态

| 事项 | 决定 | 状态 | 日期 |
|---|---|---|---|
| 项目目标 | 两部分：Part 1 审核是否符合 PA（医院、保险都用）；Part 2 为医院准备申请材料包 | 已确认 | 2026-11-01 |
| 交付形式 | side project，做一个投资人视角的 demo 成品 | 已确认 | 2026-10-26 |
| 主线用户 | 医院为主线，保险视图为第二视图，共用引擎 | 已确认（暂定主线） | 2026-10-26 |
| 模型 | POC 用 Claude Code / OpenAI 订阅，后续换 AWS Bedrock | 已确认 | 2026-10-26 |
| 3 天规则默认值 | 默认 `strict_tm`（要求 3 天），可通过 profile 切换 | **待定**：先按此执行，以后定了只改 profile | 2026-10-26 |
| gold 标注 | 后面会做；先 dev-gold，test-gold 后补 | 已确认 | 2026-10-26 |
| 算力 | 不是限制；测试集保持 200 | 已确认 | 2026-10-26 |
| PhysioNet | 不联系 | 已确认 | 2026-10-26 |

---

## 附录 A：数据核查结果

只取汇总计数，DuckDB 实测。

| 事实 | 数字 | 对计划的影响 |
|---|---|---|
| Medicare 住院 / 去 SNF | 244,576 / 42,312 | 候选池充足 |
| 去 SNF 且有出院小结 | 34,298（再加 ≥65、存活：30,613） | 约 20% SNF 病例没有出院小结 |
| 出院小结覆盖（按 anchor 年份桶） | 2007–2018 各桶 68–75%；2019 桶 8.7%；2020–2022：0% | 排除 2020–22（D16） |
| SNF 中 `OBSERVATION ADMIT` | 9,696（23%） | 不能排除，是 3 午夜规则的核心边界 |
| POE "Admit to inpatient" 医嘱 | 有出院小结的 SNF 病例中 78% 有；2010–12 约 92%，2013 后约 99% | 可以精确算住院起点（D3） |
| 先观察后住院的 SNF 住院 | 14,384，其中只有 8.5% 进过观察病房 | 只看 transfers 会漏掉约 91% 的观察期（D3） |
| ≥3 午夜：按入院时间 → 按住院医嘱 | 38,828 → 37,337（约 3.8% 被高估） | C1 必须按住院医嘱算（D3） |
| <3 午夜却去了 SNF | 3,484；其中 940（27%）30 天内有 ≥3 午夜的前序住院 | 不能简单判不符（D4） |
| 从 SNF 入院 | 2,693 | 边界层（Step 10） |
| 出院小结长度 | 中位约 9.8k 字符（约 2.5k tokens），P99 约 7k tokens | 整份可放进上下文（D11） |
| 出院小结写成时间 | 相对出院时间：中位 −0.3h，P75 +3.6h，P95 +202h | 不完全是"决策时可得"，只能当代理（D6、D7） |
| ED 关联 | ED 数据约覆盖 2011–2019；17,147 例 SNF 病例能连上 | ED 特征可选 |
| ICU | SNF 病例中 28% 有 ICU 记录 | ICU 功能评分只覆盖少数 |
| omr 表 | 只有血压、体重、BMI、身高、eGFR | 没有功能评分 |
| emar 覆盖 | 2007–09：0%；2010–12：4.8%；2013–15：79%；2016–18：99%；prescriptions 约 100% | 用药证据以 prescriptions 为主 |
| PT / OT / 静脉补液医嘱出现率（SNF / home health / HOME / REHAB） | PT 89/73/32/97%；OT 25/15/6/61%；静脉补液 84/76/72/90% | 结构化信号区分度弱，以文本为主 |
| discharge_detail 表 | 只有 `author` 字段 | 不是泄漏源 |

注："2020–22 没有出院小结"是根据计数得出的经验结论，官方文档未写明覆盖年份。

---

## 附录 B：规划过程与辩论摘要

三位规划者独立出方案：A（保险 UM 审核 / Medicare 政策）、B（MIMIC 数据工程）、C（多智能体 / RAG / 评估）。交叉辩论一轮后，剩余分歧交由 Fable 仲裁并核查事实，最后三方全部签字同意。

| 议题 | 初始分歧 | 结果 |
|---|---|---|
| 观察期 / 午夜数 | A、C：用 transfers；B：用 POE 住院医嘱 | B 用数据证明 transfers 会漏掉约 91% 的观察期 → 采用 POE |
| 技术性不符 | B：<3 午夜直接拒；C：可自动；A：一律不终审 | 三个条件齐备才判 `TECHNICAL_NOT_MET`，交非医师确认并询问前序住院 |
| 引用 | A、B：生成原文 + 字符串匹配；C：span ID | 采用 span ID + 锚点短语 |
| 流程 | C：每条标准单独调用，约 25 次 / 例；A：3 个 LLM 角色 | 采用 3 个角色；逐条调用作为对照实验 |
| 病历检索 | B：单病例 BM25；C：整份放进上下文 | 实测长度后整份放进上下文 |
| 主指标 | A：错误拒绝率；B：去向 F1；C：gold + 反事实 | gold 逐条准确率 + 错误拒绝 / 批准率 + 过度补材料率 |
| Discharge Medications | A、B：保留；C：删除 | 仲裁：删除（格式本身泄露去向），用药改用事实卡 |
| 解码 | C：criteria_reviewer 采样 3 次；A、B：温度 0 | 温度 0 为主，自一致性需先证明有用 |
| 3 天规则 / TEAM | 三种呈现方式 | 多个 profile 并列报告；TEAM 不进实验 |
| 州法 | A 原列为约束 | A 更正：MA 优先于州法，只作背景 |
| 仲裁追加 | — | critic 抽审 20% `APPROVE`；改称"licensed clinical reviewer"；dev 也限 2011–2018 |

---

## 附录 C：与旧计划（`plan/snf_pa_multi_agent_rag_plan.md`）的主要差异
1. 目标明确为两部分（审核 + 申请材料包），审核同时服务医院和保险。
2. 不再排除观察期住院（旧计划会丢掉约 23% 的 SNF 病例，并造成偏倚）。
3. 午夜数按 POE 住院医嘱计算；引入 T_pa；限定 2011–2018。
4. 6 个 agent → 3 个 LLM 角色 + 代码 / 工具 / 模板；总体结论由代码汇总。
5. 引用从"生成原文 + 字符串匹配"改为 span ID。
6. 主评估从去向 F1 改为 gold 逐条准确率 + 错误率 + 反事实测试。
7. 规模从 2,000 + 300 改为 300。
8. 模型可插拔：订阅 → Bedrock。
9. 政策语料补充 §422.101(c)、§422.566(d)、CMS 2024-02 FAQ、CMS-0057-F，并分 Tier 1–3。
10. 工程问题：`.gitignore` 误伤源码、`.csv.gz` 路径、样本量 50 / 300 不一致。

---

## 附录 D：修订记录

| 版本 | 日期 | 内容 |
|---|---|---|
| v1 | 2026-10-25 | 三方独立方案 → 辩论 → 仲裁 → 共识计划 |
| v2 | 2026-10-26 | 定位改为投资人视角的 demo；新增合成病例、适配器、产品 demo；3 天规则改为 profile 配置 |
| v3 | 2026-10-26 | 模型路线定为订阅 → Bedrock；医院为主线、保险为第二视图 |
| v4 | 2026-11-01 | 目标重构为两部分（Part 1 审核、Part 2 申请材料包）；全文结构重排并经独立排版审阅；步骤按执行顺序重新编号；新增术语表；引擎输入改名 `CaseBundle` |

文件名中的 `1025` 是首次创建日期，保留不改，方便已有链接。

---

## 附录 E：来源

**法规与政策**
- 42 CFR 409 Subpart D（本地 `policy_docs/42cfr409_subpartD.xml`）；BPM Ch.8（本地 `policy_docs/bp102c08.pdf`）
- 42 CFR 422.566：https://www.law.cornell.edu/cfr/text/42/422.566 ；422.101：https://ecfr.io/Title-42/Section-422.101
- CMS-0057-F：https://www.cms.gov/priorities/burden-reduction/overview/interoperability/policies-and-regulations/cms-interoperability-and-prior-authorization-final-rule-cms-0057-f/cms-interoperability-and-prior-authorization-final-rule-cms-0057-f ；fact sheet：https://www.cms.gov/files/document/fact-sheet-cms-interoperability-and-prior-authorization-final-rule-cms-0057-f.pdf ；时间线：https://digitalhealth.folio3.com/blog/?p=15546 ；https://connextglobal.com/ms-prior-authorization-mandate-2027/
- CMS-4201-F：https://www.cms.gov/newsroom/fact-sheets/2024-medicare-advantage-and-part-d-final-rule-cms-4201-f
- TEAM 3 天豁免：https://www.cms.gov/files/document/mm14098-implementing-transforming-episode-accountability-model-skilled-nursing-facility-3-day-rule.pdf
- WISeR：https://www.kff.org/medicare/examining-the-potential-impact-of-medicares-new-wiser-model/

**行业与市场**
- OIG OEI-09-24-00331（SNF PA 拒绝在申诉后 95% 被推翻）：https://oig.hhs.gov/reports/all/2026/medicare-advantage-organizations-overturned-nearly-all-appealed-prior-authorization-denials-for-skilled-nursing-facility-admission-raising-concerns-about-initial-denials/
- 参议院 PSI 关于 post-acute AI 拒绝：https://www.hcam.org/?p=15342
- WellSky 管理部分 MA 计划 post-acute PA：https://providerinfo.bcbsm.com/documents/alerts/2026/202602/alert-20260210-change-auth-snf-interrupted-stays.pdf
- Cohere Health C 轮：https://www.fiercehealthcare.com/ai-and-machine-learning/cohere-health-lands-90m-series-c-round-expand-ai-use-cases

**数据**
- MIMIC-IV 3.1：https://physionet.org/content/mimiciv/3.1/ ；MIMIC-IV-ED 2.2：https://physionet.org/content/mimic-iv-ed/2.2/ ；MIMIC-IV-Note 2.2：https://physionet.org/content/mimic-iv-note/2.2/

**技术**
- Claude Code headless 模式：https://code.claude.com/docs/en/headless
- Codex 非交互模式：https://developers.openai.com/codex/noninteractive
- Qwen3 采样建议：https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html
- llama.cpp Arc 140V 问题：https://github.com/ggml-org/llama.cpp/issues/18946

**研究文献**
- 多智能体医疗必要性判定（BioNLP 2024）：https://arxiv.org/html/2404.17977v2
- 多智能体 vs 单智能体系统综述：https://pmc.ncbi.nlm.nih.gov/articles/PMC12407621/
- ArchEHR-QA 2025（逐字引用）：https://preview.aclanthology.org/setup/2025.bionlp-share.8
