# SNF Prior Authorization：Multi-Agent + RAG 共识工作计划（2026-10-25）

> 本文件是**方案**，不含代码。由三位独立规划者（A：付款方 UM / Medicare 政策；B：MIMIC 数据工程；C：多智能体 / RAG / 评估）各自提案 → 一轮交叉辩论 → Fable 仲裁未决项与事实核查 → 三方终轮全部签字（SIGN-OFF: yes）后形成。
> 覆盖并修订 `plan/snf_pa_multi_agent_rag_plan.md`（旧计划保留不动，差异见 §9）。
> 数据范围：**MIMIC-IV v3.1（hosp/icu）+ MIMIC-IV-ED + MIMIC-IV-Note**，原始数据 `E:\project data\AgentResearch\raw` 只读。
>
> **v2 修订（同日，根据你对 §7 的回答）**：项目定位从"研究评估"转为"**side project，目标是做出一个能给投资人看的 demo 成品**"。新增 §0.1（你的回答带来的变化）、§0.2（产品定位与投资人视角）、§0.3（模型路线），并相应修改了 D2、D14、D16、Step 0、Step 9–11、§4、§5、§7。共识部分（审核逻辑、数据处理、评估方法）不变。
>
> **v3 修订（2026-10-26）**：模型路线定为"POC 用 Claude Code / OpenAI 订阅，后续切换 AWS Bedrock"；方案中不再设模型使用限制；不联系 PhysioNet。

---

## 0. 项目定位（一句话）

模拟 **Medicare Advantage（MA）计划的出院前（pre-service）SNF 入住 prior authorization**，审核标准使用 **Traditional Medicare 覆盖标准（42 CFR 409.30–409.36 + Medicare Benefit Policy Manual Ch.8）**。系统对每条标准逐条判定、由代码汇总决定，**永不签发最终的 medical-necessity 拒绝**。

为什么这样定位：
- Traditional Medicare（FFS）本身不对 SNF 做 PA；需要 PA 的是 MA。
- CMS-4201-F（§422.101(b)(c)）要求 MA 必须沿用 TM 的覆盖标准 → 政策语料统一、可引用。
- MIMIC 的 `insurance='Medicare'` 不区分 FFS/MA → 3-day rule 做成开关（见 D2）。

---

## 0.1 你的回答带来的变化（v2）

| 问题 | 你的回答 | 对计划的改动 |
|---|---|---|
| Q1 gold 标注者 | 后面会做一些标注 | gold 流程保留（Step 8）。顺序改为：先标 30 例 dev-gold 用于开发，test-gold 120 例后补；标注手册就是 criterion cards，现在就写好 |
| Q2 云端模型 | POC 用 Claude Code / OpenAI 订阅，后续换 AWS Bedrock（v3 定稿） | 见 §0.3 模型路线；模型接口可插拔，切换只改配置 |
| Q3 交付目标 | side project，做 demo 成品，按投资人视角 | 新增产品定位（§0.2）；demo 以**合成病例**为主（为展示能力专门设计，可控、可重复）；MIMIC 结果作为 Validation 页的真实数据验证；ablation 从完整网格缩到"讲故事需要的几组"（Step 10）；Step 11 扩成产品 demo |
| Q4 3-day 主模式 | 先按 strict_TM，但要留好口子 | 3-day 规则和相关假设全部放进**plan profile 配置文件**（D2），换规则只改 YAML，不改代码。这本身也是产品卖点：不同 MA 计划规则不同 |
| Q5 算力 | 不是问题 | test 保持 200；订阅模型做主力，本地 qwen3:14b 作为"可私有化部署"对照 |

---

## 0.2 产品定位与投资人视角（v2 新增）

### 推荐定位：医院侧的"出院 SNF 授权助手"为主线，payer 侧审核视图为第二视图
同一个引擎（逐条标准 × 病历证据 × 政策引用）可以服务两边，但讲给投资人的主线建议放在**医院侧（provider-side）**：

| | 医院侧：Discharge PA Copilot（推荐主线） | payer 侧：Reviewer Assist |
|---|---|---|
| 用户 | 医院 case manager / 出院计划员 | MA 计划的 UM 护士 / 医疗主任 |
| 做什么 | 出院前自动生成对标准的 PA packet；提前指出会被 PEND 的缺口（缺 PT 评估、缺认证等）；被拒后起草申诉信 | 预审病例，逐条给证据和条款，建议结论交人工 |
| 价值主张 | 首次提交通过率更高、等待授权的滞留天数更少、case manager 省时间 | 审核员省时间、决定一致、可审计 |
| 舆论与监管风险 | 低：帮病人拿到应得的覆盖 | **高**：nH Predict 诉讼、参议院 PSI 报告、OIG 发现 SNF 拒绝在申诉后 95% 被推翻，"AI 拒保"是负面标签 |

理由：
- 监管风向在推 PA 电子化和透明化：CMS-0057-F 的 72 小时 / 7 天决定时限自 2026-01-01 起适用；payer 的 Prior Authorization API（FHIR）须在 2027-01-01 前上线，并能返回批准、带具体理由的拒绝、或补材料要求；医院通过 API 电子提交 PA 可拿 MIPS 加分。医院侧需要一个能"按标准组织证据、电子提交"的工具。
- payer 侧已有大玩家（Optum/naviHealth、Cohere Health 2025 年 C 轮 9,000 万美元、WellSky 自 2026-01 起为部分 MA 计划管理 post-acute PA），而且 payer 侧 AI 正处于舆论风口。
- 引擎是中立的：本计划的核心设计（永不自动拒绝、逐条引用、Jimmo 护栏）在两边都成立，demo 里做两个视图正好展示"双边"潜力。

**已定（v3）**：暂时以医院侧为主线，payer 侧作为第二视图。不管选哪边，**引擎、数据处理、评估都不变**，变的只是 demo 的叙事和 UI。

### 两边共用什么、不同在哪
两边看的是同一套东西：同一份 Medicare 标准（C1–C7）、同一类病历证据、同一批政策条文。所以大约八成的系统是共用的，差别集中在"输入是什么、输出给谁、流程怎么走"。

| | 共用 | 医院侧 | payer 侧 |
|---|---|---|---|
| 标准与政策 | criterion cards、理由码、政策 RAG、Jimmo 等护栏 | 同 | 同 |
| 引擎 | Abstractor → Reviewer → Critic → Aggregator，逐条判定 + span 引用 | 同 | 同 |
| **输入** | — | 完整病历（EHR 里能拿到的都能用） | **只有医院提交的 packet**；没提交的就当不存在 |
| 输出 | 逐条结果 + 证据 + 条款 | "提交前准备度"：会不会被 PEND、缺什么、自动生成 RFI 发给自己的医生 / PT；packet 和申诉信 | 建议结论（批准 / 补材料 / 建议拒绝）+ 待 licensed reviewer 签署；NDMC 等通知 |
| 流程 | — | 出院前跑一次；被拒后起草申诉 | 按 CMS-0057-F 时限（72h / 7 天）排队；concurrent review（SNF 住进去后续审） |
| 关心的指标 | — | 首次提交通过率、等待授权的滞留天数、case manager 用时 | 审核员用时、决定一致性、申诉推翻率 |
| 监管压力 | — | 低 | 高（§422.566(d)、CMS 2024-02 FAQ） |

**设计上怎么体现**：
- 引擎不变；加一个 `view` 参数（`provider` / `payer`），只影响两件事：输入范围（payer 视图只用 packet 里的内容）和输出模板。
- demo 里可以演示**同一个病例从医院侧生成 packet，再原样送进 payer 视图审核**：两边对同一份证据给出一致的逐条结果。这正好讲"连接医院和保险两边"的故事，也说明为什么医院提前把材料做全会更快批下来。
- payer 视图只用提交的 packet，这本身也是一个有意义的对比：同一个病人，完整病历 vs 提交的 packet，结论差多少。这能说明医院侧工具的价值（packet 越完整，越少 PEND）。

### 投资人会问的问题，以及计划怎么回答

| 投资人问题 | 计划里的回答 / 产出 |
|---|---|
| 解决谁的什么痛点、谁付钱？ | §0.2 定位表；Step 11 第一张"问题"页（OIG 95% 推翻、CMS 7 天时限、2027 API） |
| 真的能用吗？准确率多少？ | MIMIC 研究验证：在 200 例真实去标识出院病例上的逐条标准准确率、错误拒绝率 / 错误批准率、补材料识别准确率（Step 10）；**只给汇总数字** |
| 安全吗？会不会乱拒？ | 设计上永不自动拒绝；反事实安全测试（Jimmo 测试：加一句"无康复潜力"不得转为拒绝）；引用 100% 可回溯 |
| 为什么现在？ | CMS-0057-F 2026/2027 两个时间点；MA 的 SNF 拒绝正被 OIG 和国会盯着 |
| 和竞品有何不同？ | 专注 post-acute / SNF；逐条可解释、可审计；规则可按 MA 计划配置（plan profile）；可私有化部署（本地模型）；对接 FHIR |
| 能接进医院系统吗？ | 内部 packet schema 和 FHIR 输入/输出适配（Step 9a）；demo 里导出 FHIR PAS 风格的 Bundle 和 PDF |
| 部署和数据安全？ | 正式运行走 AWS Bedrock（企业级云）；也可以用本地模型私有化部署（§0.3） |
| 护城河？ | 标准知识库（criterion cards + 理由码）、评估工具与 gold 集、未来试点数据的飞轮 |
| 还缺什么？ | 诚实地讲：MIMIC 无法证明 ROI（滞留天数、首次通过率），下一步需要一家医院试点 |

### 不要做的事
- 不要宣称"批准率提升 X%"这类 MIMIC 测不出的指标。
- 不要把产品讲成"自动拒保"。

---

## 0.3 模型路线（v3，按你的决定）

| 阶段 | 模型 | 用途 |
|---|---|---|
| **POC（现在）** | Claude Code 订阅、OpenAI（Codex / ChatGPT）订阅；本地 qwen3:14b 作为对照 | 开发、调 prompt、在 MIMIC 和合成病例上跑完整流程、做 demo |
| **后续** | AWS Bedrock 上的模型 | 替换 POC 的订阅模型，作为正式运行的模型后端 |

落地方式：
- **模型接口可插拔**（D18）：所有 LLM 调用走一个统一的 provider 接口，按角色配置（Abstractor、Reviewer、Critic 可以用不同模型）。从订阅切到 Bedrock 只改配置，不改引擎代码。
- **POC 怎么接订阅模型**：
  - Claude 侧：`claude -p "<prompt>" --output-format json --json-schema '<schema>'`，从返回 JSON 的 `structured_output` 字段取结果（没有这个字段就当失败重试）；JSON 里还带 `total_cost_usd` 和 usage，可直接记进 trace。**不要加 `--bare`**——bare 模式不读订阅登录，只认 `ANTHROPIC_API_KEY`。用 `--permission-mode dontAsk` 并只给最少的工具，让它只做"读 prompt、出 JSON"这一件事；另外在一个干净的空目录里调用，避免加载项目里的 hooks / CLAUDE.md。
  - OpenAI 侧：`codex exec "<prompt>" --output-schema ./schema.json -o ./out.json --ephemeral`（`--output-schema` 约束最终输出符合 JSON Schema，`-o` 把最终消息写进文件，`--ephemeral` 不保存会话文件）；需要事件流时加 `--json`（JSONL）。默认 sandbox 不写文件，正好适合只出 JSON 的调用。
  - 两者都封装成和 Ollama / Bedrock 同样的接口（输入 prompt + JSON schema，输出结构化 JSON），这样 ablation 里换模型也只改配置。
  - 订阅有调用频率和额度限制，批量跑 test 200 时要加限速和断点续跑（Step 9 的 checkpointer 正好可以用）。
- **Bedrock 切换时**：加一个 Bedrock provider（langchain-aws 已在依赖里），跑一遍同样的 test 集，对比结果是否一致，作为切换的验收。

Demo 的病例内容仍以**合成病例**为主（Step 8b），原因是产品层面的：每个合成病例都是为展示某个能力专门设计的，结果可控、可重复演示，也方便给投资人随意点开看。MIMIC 上的结果作为 Validation 页的真实数据验证。

---

## 1. 已核实的数据事实（只取聚合计数，规划者用 DuckDB 实测）

| 事实 | 数字 | 对计划的影响 |
|---|---|---|
| Medicare 住院 / 去 SNF | 244,576 / 42,312 | 候选池充足 |
| 去 SNF 且有出院小结 | 34,298（Medicare+SNF+≥65+存活+有 note：30,613） | 约 20% SNF 病例无 note |
| 出院小结覆盖（按 anchor 年份桶） | 2007–2018 各桶 68–75%；2019 桶 8.7%；**2020–2022：0%** | 2020–22 必须排除 |
| SNF 中 `OBSERVATION ADMIT` | 9,696（23%） | **不能排除**，是 3-midnight 边界核心 |
| POE "Admit to inpatient" 医嘱 | SNF+note 中 78% 有；2010–12 桶约 92%，2013 后约 99% | 可精确计算 inpatient 起点 |
| 观察→住院（POE 判定）的 SNF 住院 | 14,384，其中只有 8.5% 进过 Observation 病房 | 用 `transfers` 识别观察期会漏掉约 91% |
| 朴素口径 ≥3 午夜 → 按住院医嘱口径 | 38,828 → 37,337（约 3.8% 被高估） | C1 必须用医嘱口径 |
| <3 午夜却去 SNF | 3,484；其中 940（27%）30 天内有 ≥3 午夜的前序住院 | 不能简单"自动拒绝" |
| 从 SNF 入院（admission_location） | 2,693 | 边界层 |
| 出院小结长度 | P50 9.8k 字符（约 2.5–2.8k tokens），P99 约 7k tokens | 整份可放进 16k 上下文 |
| 出院小结写成时间 | storetime − dischtime：中位 −0.3h，P75 +3.6h，P95 +202h | 不是"决策时可得"的文件，只能作代理 |
| ED 关联 | ED 数据只覆盖约 2011–2019；SNF 中 17,147 例能连上 edstays | ED 特征为可选 |
| ICU | SNF 中 28% 有 icustays | chartevents 功能评分只覆盖少数 |
| omr | 只有血压、体重、BMI、身高、eGFR | **没有功能评分** |
| emar 覆盖（按年份桶） | 2007–09：0%；2010–12：4.8%；2013–15：79%；2016–18：99%；prescriptions 约 100% | 用药证据以 prescriptions 为主 |
| poe 会诊在 SNF/HHC/HOME/REHAB 中的出现率 | PT 89/73/32/97%；OT 25/15/6/61%；IV fluids 84/76/72/90% | 结构化信号区分度弱，文本为主；HHC 是难负例 |
| discharge_detail | 只有 `author` 字段 | 不是泄漏源 |

注意：MIMIC-IV-Note 官方页面没写覆盖年份，"2020–22 无 note"是基于计数的经验结论，报告中应如此表述。

---

## 2. 关键设计决策（三方共识 + 仲裁结果）

| # | 决策 | 来源 |
|---|---|---|
| D1 | **输出四类**：`APPROVE` / `PEND_INFO`（附具体 RFI 清单）/ `ADVERSE_RECOMMENDATION`（→ licensed clinical reviewer 复核）/ `TECHNICAL_NOT_MET`（→ 非医师确认队列 + 自动 RFI）。系统永不签发终局拒绝。 | 共识 + 仲裁 O3 |
| D2 | **3-day rule 是开关**：`strict_TM`（主）与 `MA_waiver`（并列），两张决策表全量报告；两模式只差代码汇总，LLM 成本为零。TEAM 不进实验网格，只进 Tier-3 语料，并加"不得引用 TEAM 豁免"的负向检索测试。**v2：所有规则假设集中在 plan profile 配置文件**（如 `profiles/strict_tm.yaml`、`profiles/ma_waiver.yaml`），字段包括 `three_day_rule: required|waived`、`qualifying_stay_lookback_days: 30`、`assume_no_other_qualifying_stay: true`、`auto_technical_noncoverage: true`、`physician_cert: assume_submitted`、`critic_approve_sample_rate: 0.2`。Aggregator 和 Intake 只读 profile，代码里不出现硬编码规则；以后换模式或新增某个 MA 计划的规则，只加一个 YAML。每次运行把 profile 名和 hash 写进 trace。 | 仲裁 O4 + v2 Q4 |
| D3 | **C1 午夜数** 从最早的、未被撤销的 `poe_detail` "Admit to inpatient" ordertime 起算；医嘱后的 ED 滞留计入；ED 和观察期不计。无 POE 医嘱则退回 admittime 并打标记，给出上下界；上下界跨过 3 → UNCERTAIN → PEND。 | 共识（B 的数据） |
| D4 | **技术性不符**：strict_TM 下，(a) 有未撤销的住院医嘱，(b) 午夜上下界都 <3，(c) 30 天内无合格前序住院 → `TECHNICAL_NOT_MET`，不调 LLM 做决定；配置 `assume_no_other_qualifying_stay=True`（实验默认）；任一条件不满足 → PEND。决定信必须写明理由码和条款（§409.30(a)）。 | 仲裁 O3 |
| D5 | **medical-necessity 审查对所有病例都跑**（包括 C1 不符的），这样 MA_waiver 模式能直接复用。 | 仲裁 O3 |
| D6 | **PA 决策时点** `T_pa = max(dischtime − 24h, inpatient 起点)`，−48h 做敏感性分析。结构化数据和影像报告只用 T_pa 之前的。 | 共识 |
| D7 | **主实验的病历输入**：保留 CC / HPI / PMH / Social Hx / PE / Pertinent Results / Hospital Course + **Discharge Condition（Activity/Mental Status，标记为"出院时功能状态代理"，无条件保留）**；删除 Disposition / Facility / Discharge Instructions / Followup / Discharge Diagnosis / **Discharge Medications**；用正则遮蔽去向句；PT/OT"推荐去 rehab/SNF"的半句遮蔽，同句的功能描述保留。用药证据改用 T_pa 前的 prescriptions（+emar）fact cards。 | 仲裁 O1 |
| D8 | **realistic ablation**：加回 PT/OT 推荐句 + 去词后的 Discharge Medications；另做"去掉 Activity Status"的敏感性 ablation。 | 仲裁 O1 |
| D9 | **引用机制**：病历预先切成带稳定 ID 的句子 / 条目（如 `DS:HC:s14`、`RX:<pk>`）；LLM 只输出 span ID + ≤8 词的锚点短语；代码校验锚点确实在该 span 中，并回填原文 → 编造引用在结构上不可能。 | 共识 |
| D10 | **Agent 拓扑固定（LangGraph workflow，不做 LLM supervisor）**：Intake（代码）→ Abstractor（LLM）→ Criteria Reviewer（LLM，C3–C6 一个 schema）→ Critic（LLM，审所有非 approve + **随机 20% 的 approve**）→ Aggregator（代码）→ 模板决定信。每例约 2.5–2.7 次 LLM 调用。 | 共识 + 仲裁挑战 1 |
| D11 | **病历检索**：整份去泄漏后的出院小结直接进上下文；单病例 BM25（可选 hybrid）只用于影像报告、fact cards，以及超过约 8k tokens 的长尾 note。 | 共识 |
| D12 | **解码**：Abstractor `/no_think`、T=0、Ollama `format`=JSON schema、`repeat_penalty`≈1.1、硬 `num_predict` 上限；Reviewer/Critic 主表 T=0 单次。Self-consistency ×3（T=0.7 / TopP 0.8 / TopK 20）只做**有门槛**的实验：dev 上"一致率对正确性的 AUROC > 0.65"且能降低 false-adverse 才在 test 启用并单列。记录 seed；说明 Ollama T=0 并非逐位确定。 | 仲裁 O2 |
| D13 | **队列**：Medicare、入院 ≥65、出院存活、anchor 桶 2011–2018、有出院小结、每人一次住院；dev 和 test 都限 2011–2018 且 test 只取有 POE 状态医嘱的病例；2008–2010 无 POE 病例只做"C1 UNCERTAIN"冒烟测试。 | 共识 + 仲裁挑战 5 |
| D14 | **规模**：dev 100（+ 项目组自标 dev-gold 20–30）/ 冻结 test 200（内嵌 gold 120，其中 30 例双人标注），共 300，和 `tests/test_sample.py` 的 N=300 对齐。 | 仲裁 O5 |
| D15 | **主指标（co-primary）**：gold 逐条标准准确率 + 成对的 false-adverse / false-approve 率 + over-pend 率（均带 CI，**按 3-day 模式分别报告**）；反事实测试；引用可解析率 / 支持率。silver（discharge_location）AUROC 只作次要。 | 共识 + 仲裁挑战 3 + C 的澄清 |
| D16 | **模型路线（v3）**：POC 用 Claude Code / OpenAI 订阅（headless CLI 封装成 provider），本地 qwen3:14b 作对照；后续切换 AWS Bedrock。trace 写本地 JSONL；派生数据和 trace 不进 git（体积和仓库整洁）。 | v3 |
| D17 | **（v2 新增）引擎与数据源解耦**：引擎只认内部的 `PAPacket` schema；MIMIC 和 FHIR（合成病例）各写一个 adapter 转成 `PAPacket`。引擎代码里不出现任何 MIMIC 表名。这样同一引擎既能跑研究验证，也能跑 demo，以后接医院 EHR 只需加一个 adapter。 | v2 |
| D18 | **（v2 新增）模型可插拔**：统一的 LLM provider 接口（本地 Ollama / Bedrock / 其他 API），按角色配置（Abstractor、Reviewer、Critic 可以用不同模型）。POC 阶段 demo 和 MIMIC 验证都用订阅模型做主力，本地 qwen3:14b 作为"可私有化部署"对照；之后加 Bedrock provider。 | v2 Q2/Q5 + v3 |

---

## 3. Step-by-step 工作计划

时间线是粗估，前提是一人全职、本地算力；以 Step 1 吞吐基准为准再调整。

### Step 0 — 仓库卫生（0.5–1 天）
**目标**：让代码可复现、能入库。
**做法**
1. `.gitignore`：`data/` 改为 `/data/`。现在这条规则把 `src/snf_pa/data/` 也忽略了，所以 Step 1 的 cohort 代码（`config.py`、`cohort.py`、`build_sample.py`）**不在 repo 里**，`tests/test_sample.py` 引用的 `snf_pa.data.config` 在别处 clone 后会缺失。先确认这些文件在本地是否还存在，再入库。
2. 统一数据路径配置：RAW 根目录为 `E:/project data/AgentResearch/raw`，读取**未压缩 `.csv`**（旧计划写的是 `.csv.gz`）；派生数据写 repo 内 gitignored 的 `derived/`。
3. 对齐 N：`test_sample.py` 期望 N=300（每类 60、batch 1=50），`step 0 plan.txt` 写的是 50 → 统一按 D14 重新定义测试断言（Step 5 重抽后改）。
4. `.env` 加 `LLM_BACKEND=local|bedrock` 开关（已有 `LLM_PROVIDER`，沿用即可）。
5. trace 统一写本地 JSONL（`traces/`，已在 .gitignore）。
6. **（v3）LLM provider 接口**：定义统一接口和配置（provider 名、模型、按角色分配），先实现 Ollama、Claude Code headless（`claude -p`）、Codex（`codex exec`）三个 provider；Bedrock provider 留好位置。
7. **（v2）目录分家**：`src/snf_pa/engine/`（产品引擎，不依赖 MIMIC）、`src/snf_pa/adapters/{mimic,fhir}/`、`research/`（MIMIC 验证脚本）、`demo/`（合成病例与 UI）。现有空的 `agents/ graph/ rag/ tools/` 可以并入 `engine/`。
**完成标准**：新 clone 后 `pytest` 可运行（缺数据时 skip）；`git ls-files` 里有 cohort 代码；三个 provider 都能对同一个合成 prompt 返回合法 JSON。

### Step 1 — 吞吐基准（半天，第 1 周，与 Step 2/3 并行）
**目标**：用实测数字决定后面所有规模。
**做法**：用**合成病例**（不碰 MIMIC）测 qwen3:14b Q4 在 Arc 140V 上的 prompt 处理速度和生成速度（`ollama run --verbose`）；分别测 Abstractor 式长调用（约 4k 输入 + 1k 输出）和 Reviewer 式短调用（约 1.5k 输入）。
**注意**：llama.cpp 社区有 140V 上不稳定的报告；IPEX-LLM 已归档，默认走 Vulkan 后端。显式设置 `num_ctx=16384`。
**决策规则**：每例超过 5 分钟 → 锁定 2–3 次调用、test 缩到 150；如果还慢，抽取改用 qwen3:8b、判定保留 14B。
**v2**：你说算力不是问题，所以这一步只用来定"本地私有化部署"那条线的速度；同时测 Claude Code / Codex 订阅 provider 的单例耗时和额度消耗，作为 demo"每例用时"KPI 的依据（投资人会问"多久出结果"），也用来估算批量跑 test 200 需要多久。
**完成标准**：得到每个候选模型"秒/调用"和"分钟/例"的估计，写进 manifest。

### Step 2 — 政策规格化：criterion cards + 拒绝理由码（2–3 天，第 1 周并行）
**目标**：把法规翻译成机器可执行、可引用的标准；这同时就是 gold 标注手册。
**做法**：写 YAML checklist，每条带定义、条文 ID、2–3 个正例和反例（取自 BPM §30.2–30.4）、版本或生效日期。

| ID | 标准 | 条文 | MIMIC 能否判定 |
|---|---|---|---|
| C0 | Medicare Part A 资格 | — | 代理：insurance + 年龄 ≥65 |
| C1 | 连续 ≥3 个 inpatient 午夜（出院日不算；ED 和观察期不算） | §409.30(a)；Ch.8 §20.1 | 确定性（Step 4） |
| C2 | 出院 30 天内入住 SNF | §409.30(b)；§20.2 | 假定满足 |
| C3 | SNF 照护针对住院期间治疗过的病情 | §409.31(b)(2) | 诊断 + note |
| C4 | 需要 skilled nursing 或 skilled rehab | §409.31(a)、§409.32、§409.33；§30.2–30.4 | **核心 LLM 判断** |
| C5 | daily basis：nursing 每周 7 天，或 rehab 每周 ≥5 天 | §409.34；§30.6 | 推断 |
| C6 | practical matter：只能在 SNF 住院环境提供 | §409.35；§30.7 | 推断，常 PEND |
| C7 | 医师认证 | §424.20；§40 | 无数据 → 配置为"假定已提交" |
| C8 | benefit period 剩余天数 | §409.61 | 只能看到院内 → 假定 |

**跨条护栏**（同时写进 Critic 规则）：
- Jimmo：不能以"无改善潜力 / 已到平台期"拒绝；维持性 skilled therapy 可覆盖。
- custodial care（§30.5）不算 skilled。
- 不能凭诊断本身推定 skilled。
- 禁止用 LOS 预测（nH Predict 式）做拒绝依据。

**拒绝理由码表**：每个码对应一条 criterion 和一个 CFR 条款（CMS-0057-F 要求写明具体理由）。
**注意**：核对本地 `policy_docs/bp102c08.pdf`（Rev. 12283，2023-10-05）是不是 CMS 当前最新版；按"2026 年审核员"的规则判定；PHE 期间的 3-day 豁免已在 2023-05-11 结束；措辞用"licensed clinical reviewer"（§422.566(d) 原文是 physician *or other appropriate health care professional*）。
**完成标准**：C0–C8 每条都有 YAML、条文锚点和正反例；理由码表完成。

### Step 3 — 一次性 Parquet 抽取（2–3 天，第 1 周并行）
**目标**：之后所有步骤都不再读 raw CSV。
**做法**
- DuckDB：`memory_limit=16GB`，`temp_directory` 放 SSD，threads 8；**不用 pandas**。
- 先建 `cohort_hadm.parquet`（候选池超集，约 4 万 hadm_id），再对每张大表 `COPY (SELECT 所需列 FROM read_csv(...) WHERE hadm_id IN pool) TO derived/x.parquet`（zstd，按 hadm_id 排序）。
- 涉及的表：
  - hosp：admissions、patients、transfers、services、diagnoses_icd、procedures_icd、prescriptions、pharmacy、emar（与 pharmacy 用 pharmacy_id 连接取 route；只算 event_txt ∈ Administered/Started/Delayed Administered）、poe + poe_detail、labevents（itemid 白名单：WBC、Hb、Cr、INR、白蛋白、血糖、乳酸）、microbiologyevents（可选）
  - icu：icustays、chartevents（单次扫描，stay_id ∈ 候选池且 itemid ∈ 白名单：Braden Activity/Mobility 224056/224057、Gait/Transferring 227345、Ambulatory aid 227343、Risk for Falls 223754、压疮系列、OT Notes 227848 等）
  - ED：edstays、triage、diagnosis（vitalsign、medrecon 可选）
  - note：discharge、radiology、radiology_detail
- **不要抽 drgcodes 作为输入**（出院后编码，属于泄漏），只用于分析。
**注意**：`read_csv` 的 `max_line_size` 要调大（note 有长行）；`*_detail` 表显式指定类型；写 manifest（行数、源文件 mtime / sha）。
**完成标准**：Parquet 总量 <5GB；manifest 可复现 §1 的计数。

### Step 4 — 确定性时间线与资格引擎（tools，不用 LLM；3 天）
**目标**：给每个 hadm 生成可解释的 `status_timeline` 和 C0–C2 判定。
**做法**
- `ip_order_t`：最早、未撤销（transaction_type='New'）的 "Admit to inpatient" ordertime；`obs_order_t`："Place in observation"；观察病房时段来自 transfers；ED 时段来自 edstays 或 admissions.edregtime/edouttime。
- `inpatient_midnights = date(dischtime) − date(coalesce(ip_order_t, admittime))`，同时给出上界和下界；医嘱被撤销后重新下的 → UNCERTAIN。
- `T_pa`（D6）。
- `prior_qual_stay`：admissions 按 subject 自连接，30 天内有 ≥3 午夜的出院。
- 标记从 SNF 入院、60 天内曾从 SNF 出院（benefit period 背景）。
- 年龄：anchor_age + (入院年 − anchor_year)。
**注意**：
- 真实年份由 anchor_year_group 推算，有 ±2 年误差，写进局限性。
- 院外住院在 MIMIC 里看不到 → 走 RFI，不直接拒绝。
- 所有工具只返回 T_pa 之前的数据，**在工具层强制截断**。
**完成标准**：每条规则都有单元测试；C1 的 MET / NOT_MET / UNCERTAIN 分布有报告；能复现 §1 中"38,828 → 37,337"等数字。

### Step 5 — 队列重建与抽样（2 天）
**目标**：按"审核难度"分层，而不只是按诊断分层；冻结 test。
**纳入**：见 D13。
**分层**
- 临床场景：骨科术后（髋骨折 / LEJR）、卒中、**内科病后 deconditioning**（操作定义：非手术主诊断 + 有 PT 会诊 + 不属骨科或卒中；MA 拒绝最集中，提高权重）、心衰、伤口 / IV 抗生素 / 新鼻饲管。
- 去向：SNF；HHC（难负例，过采样）；HOME（有无 PT/OT 会诊）；REHAB/IRF 独立小层（dev 20 / test 20，按 SNF 标准评估，预期 C4/C5 多为 MET；不当负例，不计入 silver F1；IRF 级别判断 §412.622 不在范围内）。
- 边界层（过采样）：观察→住院；<3 午夜去 SNF（有 / 无 prior_qual_stay）；从 SNF 入院；ICU vs 非 ICU。
- 髋骨折负例极少（1,017 去 SNF vs 9 回家 / 46 HHC）→ 单独报告，不计入总体。
**规模**：D14。主结果用分层不加权；逆抽样权重投影到 Medicare-SNF 总体只作次要。
**注意**：每人一次住院，按 subject_id 切分；test 冻结后开发过程中不能偷看。
**完成标准**：manifest 写清每个格子的候选数和抽样数；`test_sample.py` 按新设计更新并通过。

### Step 6 — 病历处理、去泄漏、span 索引与 fact cards（4–5 天）
**目标**：为每例生成"PA packet"，带稳定的 span ID。
**做法**
1. 出院小结按标题切成 section，保留字符偏移，再切到句子级，分配 span ID。按 D7 决定保留和删除哪些段落。
2. 去向句遮蔽正则：rehab、extended care、SNF、nursing facility、"___ facility"、discharge to、placement、screened、accepted at、bed offer、case management arranged、PT recommends [去向]。
3. 影像报告：只取 charttime ≤ T_pa 的，按 FINDINGS/IMPRESSION 切块；radiology_detail 的 exam_name 作元数据。
4. **结构化 fact cards**：每条标准一个 SQL 模板，输出一句话 + 主键，例如"T_pa 前 48h 内 IV vancomycin 已给药 4 次"。量化（天数、医嘱是否仍在执行），不要只给 0/1。
   - 用药以 prescriptions 为主，emar 只作补充，卡片标 `emar_available`。
   - 其他来源：poe（PICC、Tubefeeding、TPN、Wound Care、O2/BiPAP、PT/OT/Speech 会诊、Activity 医嘱）、procedures_icd、services、transfers、edstays（arrival_transport），ICU 病例加 chartevents。
5. **PA packet 缺口表**：对每例记录缺哪些真实 packet 字段（PT/OT 评估、家庭支持、医师认证…）。

**泄漏检测（三个都做）**
- TF-IDF+LR 预测 silver（SNF vs HHC），整体做一次，**逐段**也做一次。其中 Discharge Medications 单段 AUC > 0.70 → 确认删除（第 1 周的 tie-breaker）；同时按去向统计 "RX … Disp … Refills" 行的出现率。
- 让 LLM 直接"猜去向"，看命中率。
- 人工抽查 50 篇，**只在本地 IDE 里看，不进任何 LLM 对话**。

**注意**：MIMIC-IV-Note 没有逐日 progress note，"PA 提交时刻"的模拟不完全真实，如实写进局限性；`___` 是去标识占位符，保留。
**完成标准**：残余去向词命中为 0；strict / realistic 两套 packet 可复现；每张 fact card 都能用主键回查。

**标准 → 数据源映射**

| 标准 | 主要表 / 字段 | 截止与注意 |
|---|---|---|
| C0 | admissions.insurance；patients.anchor_age/anchor_year | 不区分 FFS/MA，也不区分残障类 Medicare |
| C1 | poe ⨝ poe_detail(Admit category)；admissions；transfers.careunit；edstays | ED 和观察期不计 |
| C2 / prior stay | admissions 自连接；admission_location | 只看得到院内 |
| C3 | diagnoses_icd（视作提交时的诊断码）；ED triage.chiefcomplaint、ed.diagnosis；note HPI/Hospital Course；radiology | 禁用 drgcodes |
| C4/C5 nursing | prescriptions(+emar) 给药途径；poe（PICC/TPN/Tubefeeding/Wound/O2）；chartevents 压疮（ICU）；note | ≤T_pa；要看持续性 |
| C4/C5 rehab | poe PT/OT/Speech 会诊、Activity；services ORTHO/NSURG；procedures_icd；note 功能描述 + Activity Status | PT 去向推荐句按 D7 遮蔽 |
| C6 | note Social History；ED arrival_transport；功能状态 | 常缺 → PEND |
| C7 | 无 | 配置为"假定已提交" |

### Step 7 — 政策 RAG 语料与检索评测（3 天）
**目标**：小而精、分级、引用锚定到条款号（约 200–400 个 chunk）。
**语料分级**
- **Tier 1 有约束力**：42 CFR 409.30–36、409.60–61、424.20；422.101(b)(c)、422.566、422.568、422.570–572、422.138。
- **Tier 2 指导**：BPM Ch.8（重点 §20、§30）；CMS 2024-02-06 MA coverage criteria FAQ（含算法 / AI 条款）；Jimmo 和解的 CMS 说明；Parts C&D 的 coverage determination 和申诉指南；NDMC 通知要求。
- **Tier 3 只作背景，不得作为判定依据**：CMS-0057-F；TEAM 3-day 豁免（MLN MM14098）；WISeR（只适用 TM、不含 SNF，入库是为了防止误引）；州 AI/PA 法规（§422.402 规定 MA 优先于州法，只作背景）；OIG/PSI 报告。
**做法**
- 以 `tests/check_rag.py` 已有的 CFR/BPM 切块、bge-m3、BM25、RRF 为基础；按 § 切块，§409.33 和 §30.2–30.4 的示例列表整段保留；metadata 包括 tier、生效日期、URL。
- 主力是 criterion card 直接绑定条文，检索只作补充。
- 只有 recall@5 < 0.9 时才加 reranker（可以用 LLM 做 pointwise 打分）。
**检索评测**：约 40 条"问题 → gold § ID"，测 recall@5 和 nDCG；外加负向测试：判定时不得引用 Tier 3（特别是 TEAM 和 WISeR）。
**完成标准**：recall@5 ≥ 0.9；负向测试通过。

### Step 8 — Gold 标注（2–4 周，与 Step 9 并行，**必须在调 prompt 之前完成**）
**做法**
- 标注手册 = Step 2 的 criterion cards。
- 每例逐条标注 MET / NOT_MET / INSUFFICIENT，加证据 span ID，再给出整体决定（**按 strict_TM 和 MA_waiver 两种模式分别**汇总）。
- 120 例 test gold，其中 30 例双人独立标注，算 Cohen's κ；目标是 C4–C6 的 κ ≥ 0.6，达不到本身就是一个发现（标准有歧义）。
- dev-gold 20–30 例由项目组自己标，用于调 prompt。
- **v2 顺序**：先标 30 例 dev-gold（开发用），test-gold 120 例在你有时间或找到临床标注者后补；在 test-gold 完成之前，Step 10 只报 dev 上的初步数字，并明确标注为"初步"。
- 标注工具：一个简单的标注页面（同 demo 技术栈），逐条标准点选 + 选中 span。
- 标注者看到的是同一份遮蔽后的 packet，不看系统输出（避免锚定效应）；**不能用云端 LLM 做预标注**。
**完成标准**：gold 文件冻结，κ 有报告。

### Step 8b — 合成 demo 病例库（v2 新增；3–5 天，可与 Step 6–8 并行）
**目标**：给 demo、开发调试和单元测试提供一批专门设计的、结果可控的真实感病例。
**做法**
- 写 12–15 个合成病人，每个都按"展示一个能力"来设计：

| 病例 | 要展示的能力 | 预期结果 |
|---|---|---|
| 髋骨折术后，需每日 PT + 抗凝注射 | 典型批准，证据齐全 | APPROVE |
| 肺炎后体能下降，PT 建议辅助步行，但病历里没有 PT 评估 | 提前发现缺口、生成补材料清单 | PEND_INFO |
| 只需要协助洗澡穿衣，无 skilled 需求 | custodial care 识别 | ADVERSE_RECOMMENDATION → 人工 |
| 住院 2 个午夜 | 技术性不符，以及换成 MA_waiver profile 后的结果变化 | TECHNICAL_NOT_MET / 换 profile 后进入医疗审查 |
| 先观察后转住院，跨过 3 个午夜的边界 | C1 按住院医嘱口径计算 | 视时间而定 |
| 帕金森，"已到平台期，无改善潜力"，但需要维持性 skilled therapy | **Jimmo 陷阱**：不得因此拒绝 | APPROVE 或 PEND，绝不 ADVERSE |
| 新鼻饲管 + 伤口 VAC | 每日 skilled nursing | APPROVE |
| 卒中，独居，无照护者 | practical matter（C6） | APPROVE |
| 心衰，可以回家接受 home health | practical matter 不满足 | ADVERSE_RECOMMENDATION 或 PEND |
| …（其余覆盖 IV 抗生素疗程、从 SNF 入院、认知障碍等） | | |

- 格式：每个病例是一个 FHIR 风格的 JSON Bundle（Patient、Encounter、Condition、MedicationRequest、ServiceRequest、Observation、DocumentReference 放出院小结文本），通过 FHIR adapter 转成 `PAPacket`。这样 demo 看起来是"从 EHR 拉数据"。
- 生成方式：用 Claude Code / Codex 按场景写，人工审校临床合理性；可以参考 MIMIC 出院小结的写法和 section 结构，让文本更像真实病历。结构化部分可选用 Synthea 生成人口学和基础病史再手工补充。
- 每个病例附"预期结果"和预期证据，作为 demo 的回归测试。
**完成标准**：12–15 个病例全部通过 FHIR adapter；预期结果写成 pytest 回归测试。

### Step 9a — 内部 packet schema 与 adapters（v2 新增；2–3 天）
- 定义 `PAPacket`（Pydantic）：病人人口学、encounter 时间线（admit / 住院医嘱 / 出院 / T_pa）、按 section 切好的带 span ID 的文本、fact cards（带来源主键或 FHIR resource id）、影像报告、`source`（mimic / fhir）。
- `adapters/mimic/`：Step 4–6 的产物 → `PAPacket`。
- `adapters/fhir/`：FHIR Bundle → `PAPacket`。以后接医院 EHR（真实 FHIR）也走这里。
- 输出侧：决定结果可导出为 PDF 决定信 / packet，以及一个 Da Vinci PAS 风格的 FHIR Bundle（Claim + ClaimResponse 草稿），用于 demo 中"可以电子提交"的叙事。只做到格式示意，不追求通过官方 IG 校验。

### Step 9 — Agent 实现（LangGraph；5–7 天）

```
START → load_case [tool]
      → intake_rules [code: C0–C2, status_timeline, T_pa]
      → build_packet [tool: span index + fact cards + 单病例 BM25]
      → abstractor [LLM, T=0, no_think, JSON schema]
            按 §409.33 类别输出证据：{span_id, anchor_phrase, claim, assertion(present/absent/possible)}
      → citation_resolver [code: 校验锚点 ∈ span，回填原文；失败 → 该证据作废]
      → criteria_reviewer [LLM, T=0; 输入 = 证据列表 + C3–C6 criterion cards + policy_search]
            每条：{status: MET|NOT_MET|INSUFFICIENT, evidence_ids, policy_refs, rationale}
      → aggregator [code: 按 strict_TM / MA_waiver 两种模式汇总 → 四类结果]
            ├─ 非 APPROVE，或随机 20% 的 APPROVE → critic [LLM]
            │      检查：缺少证据 ≠ 反面证据；Jimmo / improvement standard；custodial；
            │      证据与结论是否矛盾；漏掉的 fact-card skilled 信号；拒绝理由是否具体；是否用了禁止的依据
            │      → 可退回 reviewer 最多 1 次
            ├─ ADVERSE_RECOMMENDATION → interrupt(human_review) [checkpointer]
            ├─ TECHNICAL_NOT_MET → 非医师确认队列 + RFI
            └─ PEND_INFO → RFI 清单（模板 + LLM）
      → letter [模板；APPROVE：初始授权 N 天 + concurrent review 日期；
                PEND：缺失项；ADVERSE：拟拒绝理由 + 条款 + 待 licensed reviewer 签署]
```

- **State（Pydantic）**：`CaseState{case_id, eligibility{midnights_lo/hi, ip_order_t, T_pa, prior_qual_stay, flags}, packet_ref, evidence[], criteria: dict[cid, CriterionResult], decision{strict_TM, MA_waiver}, critic_findings, human_review, cost{tokens, sec}}`。
- **LLM 统一接口**：本地 / Bedrock 一行配置切换；tenacity 重试（解析失败最多 2 次）；输出长度上限。
- **Trace**：只写本地 JSONL（每个节点的输入 ID 和输出 JSON，不复制原文），不用 LangSmith。
- **注意**：Orchestrator、Policy RAG、Letter 都**不是 agent**（分别是状态机代码、检索工具、模板）。按信息瓶颈拆分，不按人类岗位拆分。
- **完成标准**：dev 20 例端到端跑通，schema 100% 合法，span ID 100% 可解析，没有解析失败。
- **v2/v3**：引擎只吃 `PAPacket`；合成病例和 MIMIC dev 都可以直接用订阅模型跑和调试。批量运行时给订阅 provider 加限速、重试和断点续跑（checkpointer）。人工复核和 RFI 也要做成 API（FastAPI），供 demo UI 调用。

### Step 10 — 评估与 ablation（1–2 周，主要是机器时间）

**指标定义**（每项都按 strict_TM / MA_waiver 分别报告）
- **false-adverse**：系统给 ADVERSE，而 gold 整体为 APPROVE。
- **false-approve**：系统给 APPROVE，而 gold 任一核心标准为 NOT_MET 或 INSUFFICIENT。
- **over-pend**：系统给 PEND，而 gold 为 APPROVE。
- **co-primary**：gold 逐条标准准确率 / macro-F1（约 480 个判定，按病例做 cluster bootstrap）+ 上面三个率（带 95% CI）。
- **反事实测试**：
  - 删掉 skilled 证据 → 应变成 PEND 或 ADVERSE；
  - 午夜数改为 2 → 应判 TECHNICAL_NOT_MET（strict_TM）；
  - 加一句"no rehab potential" → **不得**转为拒绝（Jimmo）；
  - 删掉 Activity Status → 看敏感性。
- **引用**：可解析率；support 率（LLM-judge + 30 例人工）；遗漏率（用 gold span 召回测，因为 LLM-judge 看不出"漏写"）。
- **校准**：只在启用 self-consistency 时做 risk-coverage / ECE。
- **次要**：silver AUROC（SNF vs 无服务 HOME；SNF vs HHC），按诊断层和年代分层；pend 是否合理（缺的信息在 packet 里确实没有）。
- **公平性**：按 race、language、sex、年龄段比较 adverse 率和 pend 率；gold 上看 equalized odds；控制 note 长度。
- **成本**：每例耗时和 token 数。
- **否定 / 不确定抽取**：用 `mimic-iv-ext-entitycoding` 的 assertion 标注单独评估 Abstractor（只读使用）。

**Ablation 矩阵**（全部用 qwen3:14b，记录 token 数；完整网格只在 gold 120 上跑，A0 和 A5 跑全部 200）

| ID | 配置 | 要回答的问题 |
|---|---|---|
| A0 | 结构化特征 + TF-IDF LR | 到底需不需要 LLM；silver 测的是不是去向 |
| A1 | 单次调用、整份 packet、不给政策 | 模型凭"常识"能做到多少 |
| A2 | A1 + 全部 criterion cards | 政策文本的价值 |
| A3 | 单 agent ReAct + 两套检索工具 | 有工具的单 agent |
| A3+SC | A3 自一致性，token 数与 A5 对齐 | **控制算力的关键对照** |
| A4 | 按标准扇出（C3–C6 各自抽取 + 判定），无 critic | 拆分本身的价值 |
| A5 | 默认系统（D10） | 完整系统 |
| A6 | A5 换强模型（POC：Claude / OpenAI 订阅；后续：Bedrock） | 天花板，以及 14B 的差距 |

- RAG 子 ablation：政策侧（无 / 只用 card / 只用检索 / 两者都用）；病历侧（整份 vs chunk；BM25 vs hybrid）；引用方式（生成原文 + 字符串匹配 vs span ID）。
- 证据设定：strict（主）vs realistic；T_pa −24h vs −48h。

**v2 范围调整（demo 导向）**：必做的是能直接放进 pitch 的几组，其余作为可选研究附录。
- **必做**：A0（基线）、A1（单次 LLM、无政策）、A5（完整系统，本地 qwen3:14b）、A6（完整系统，订阅强模型；Claude 和 OpenAI 各跑一次，顺便比较两家）；反事实安全测试全套；引用可解析率；每例耗时和成本。
- 这几组讲的故事：基线 → 单个 LLM → 我们的系统，差多少；本地私有部署版和云端版差多少；安全测试全部通过。
- **可选**（以后写论文再做）：A2/A3/A3+SC/A4、RAG 子 ablation、公平性的完整分析（但 adverse/pend 率按 race/language 的简单分层建议必做，投资人和医院都会问偏见问题）。
- 结果做成一页"Validation"幻灯片和一份技术报告。
- **统计**：配对 McNemar、paired bootstrap 95% CI。决策级 n=120 只能检出约 10–12 pp 以上的差异，更小的差异报为"无显著差异"。

### Step 11 — 产品 demo 与投资人材料（v2 扩写；2–3 周）
**目标**：一个能现场跑、5–8 分钟讲完的成品 demo，演示病例用 Step 8b 的合成病例。

**技术栈**
- 后端：FastAPI，包住引擎（提交病例、查询状态、人工复核、RFI、导出）。API 优先本身就是"可集成"的证据。
- 前端：先用 Streamlit 快速迭代；如果要更像产品，再换一个简单的 React/Next.js 页面（同一后端）。
- 部署：POC 本地运行（模型走订阅 provider）；之后部署到 AWS，模型换 Bedrock。

**页面**
1. **病例队列**：今天待出院的病人列表，每行显示预测结果（批准 / 缺材料 / 建议拒绝 / 技术性不符）和"还缺什么"。
2. **病例详情**：
   - 逐条标准清单（C1–C7），绿 / 黄 / 红；
   - 点任一条，右侧高亮病历原文 span，并弹出对应条款原文（CFR / BPM 段落号）；
   - 时间线：入院、住院医嘱、午夜计数、T_pa；
   - plan profile 下拉框（strict_TM ↔ MA_waiver），切换后结果即时变化，展示"规则可配置"。
3. **补材料（RFI）**：自动生成发给主治 / PT 的补材料请求清单。
4. **输出**：PDF 的 PA packet / 决定信；FHIR PAS 风格 Bundle 下载。
5. **审核员视图**（payer 侧）：同一份证据，展示"建议结论 + 待 licensed reviewer 签署"，以及 Critic 的检查结果。
6. **审计轨迹**：每一步用了哪个模型、哪个 profile、多少秒、引用了哪些 span 和条款。
7. **Validation 页**：MIMIC 研究验证的汇总指标（只有数字和图表）+ 安全测试结果 + "私有化部署 vs 云端"对比。

**Demo 脚本（5–8 分钟）**
1. 问题（30 秒）：MA 的 SNF PA 拒绝在申诉后 95% 被推翻；CMS 要求 7 天内决定，2027 年起要电子 API。
2. 打开队列，选一个髋骨折病例：一键生成，展示逐条证据和条款，导出 packet（1.5 分钟）。
3. 选肺炎体能下降病例：系统提前指出"缺 PT 评估"，生成 RFI——这是医院最在乎的"别被 PEND 卡住"（1 分钟）。
4. Jimmo 陷阱病例：病历写了"无改善潜力"，系统没有拒绝，并解释原因（1 分钟）。
5. 切换 plan profile：2 个午夜的病例在 strict_TM 下是技术性不符，在 MA_waiver 下进入医疗审查（30 秒）。
6. 审核员视图 + 审计轨迹：展示可解释、可审计、永不自动拒绝（1 分钟）。
7. Validation 页：真实去标识数据上的准确率与安全测试；可本地部署（1 分钟）。
8. 下一步：寻找医院试点，FHIR 对接，迁移到 AWS Bedrock。

**投资人材料**（与 demo 配套）
- 10 页左右的 pitch deck：问题、为什么现在、产品、demo 截图、验证结果、竞品对比、商业模式假设（按病例收费 / 按床位订阅）、下一步里程碑。
- 一页技术报告摘要（MIMIC 验证方法与局限）。
- 竞品对比表（post-acute PA 相关）：Optum/naviHealth、WellSky（含 CarePort）、Cohere Health、Waystar、Infinitus 等。上线前再核对一次最新信息。

**局限性**（报告和问答里必须如实讲）：silver ≠ 覆盖决定；出院小结是出院后写的；缺 PT/OT 评估；FFS/MA 不可区分；院外住院不可见；anchor 年份有误差；MIMIC 无法证明 ROI，需要试点。
**完成标准**：12–15 个合成病例在 demo 中稳定运行（回归测试全过）；单例用时在可接受范围（以 Step 1 实测为准）；完整走一遍 demo 脚本不出错；Validation 页数字来自冻结的 test 结果。

---

## 4. 构建顺序与里程碑

**v2：side project 按里程碑走，不按周**。每个里程碑结束都有一个能看的东西。

| 里程碑 | 内容 | 能看到什么 |
|---|---|---|
| M0 地基 | Step 0（含 LLM provider 接口、目录分家）；Step 1 吞吐基准；Step 2 criterion cards + profile YAML | 规则知识库、可配置的 profile |
| M1 合成病例上跑通 | Step 8b 合成病例库；Step 9a schema + FHIR adapter；Step 7 政策 RAG；Step 9 引擎 | **用合成病例端到端出结果**（最早的可演示版本） |
| M2 Demo v1 | Step 11 的后端 + Streamlit 页面 1–4、6 | 可以给朋友 / 顾问看的 demo |
| M3 MIMIC 研究验证 | Step 3–6（Parquet、资格引擎、队列、packet 与去泄漏）；Step 8 先标 30 例 dev-gold；MIMIC adapter；Step 10 必做组 | Validation 页的初步数字（标为"初步"） |
| M4 投资人版 | test-gold 120 补齐后冻结结果；审核员视图、Validation 页、PDF/FHIR 导出；pitch deck | 完整 demo + deck + 技术报告 |
| M5 迁移 | 加 Bedrock provider，在同一 test 集上对比结果，通过后切换 | 可部署的正式版本 |

M1 和 M3 可以并行，都可以用 Claude Code / Codex 订阅来开发和运行。

---

## 5. 模型与数据管理（v3）
- 模型路线：见 §0.3（POC 订阅 → 后续 AWS Bedrock）。
- 派生数据（`derived/`）、trace（`traces/`）、`data/` 不进 git（现有 .gitignore 已包含），原因是体积大、会频繁重建。
- 原始数据目录 `E:\project data\AgentResearch\raw` 只读，所有派生结果写 repo 内的 `derived/`。
- Bedrock 迁移时要确认：目标模型在所选 region 可用，以及账户层面的相关设置（M5 里一并处理）。

---

## 6. 主要风险

| 风险 | 对策 |
|---|---|
| 没有真实 PA 标签，silver 测的是"去向" | gold 逐条标注为主；A0 基线揭示 silver 的含义 |
| 出院小结写于出院后、无 progress note | T_pa 截断结构化数据；删 Discharge Medications；局限性如实写明 |
| 缺 PT/OT 评估 | Activity Status 作代理；缺失 → PEND，不转拒绝；量化缺口 |
| 标签泄漏 | 三种泄漏检测 + strict/realistic 两套设定 |
| 本地算力和 Arc 驱动不稳定 | 第 1 周先做基准；2–3 次调用的拓扑；主力用订阅模型 |
| （v3）订阅额度和速率限制，批量跑会中断 | 限速 + 重试 + 断点续跑；Claude 和 OpenAI 两个 provider 互为备份 |
| （v3）订阅模型和之后的 Bedrock 模型结果不一致 | M5 在同一 test 集上对比，差异超出阈值就调 prompt 后再切换 |
| gold 标注人力 | 120 例 + 30 例双标；没有临床人员则降级表述 |
| 政策版本漂移 | 语料带生效日期，固定版本 |
| （v2）"AI 拒保"的舆论和监管风险 | 医院侧为主线；永不自动拒绝；Jimmo 安全测试写进 Validation 页 |
| （v2）合成病例太"干净"，demo 效果好于真实 | Validation 页只用 MIMIC 冻结 test 的数字；合成病例里刻意放入缺失信息、矛盾记录和长病历 |

---

## 7. 需要你决定的问题

### 已回答
1. gold 标注：后面会做一些 → 先 30 例 dev-gold，test-gold 后补（Step 8）。
2. 模型：POC 用 Claude Code / OpenAI 订阅，后续换 AWS Bedrock → §0.3（v3）。
3. 交付目标：side project，投资人视角的 demo 成品 → §0.2、Step 8b、9a、11。
4. 3-day 主模式：暂按 strict_TM，口子留好 → plan profile 配置（D2）。**仍是开放问题**，以后定了改 YAML 即可。
5. 算力：不是问题 → test 保持 200。
6. 不联系 PhysioNet（v3）。

7. 产品主线：暂以医院侧为主线，payer 侧作为第二视图，共用引擎（§0.2）。

---

## 8. 辩论过程摘要（谁主张什么、如何收敛）

| 议题 | 初始分歧 | 结果 |
|---|---|---|
| 观察期 / 午夜数 | A：transfers 上下界；B：POE 住院医嘱；C：transfers | B 用数据证明 transfers 会漏掉约 91% 观察期 → 三方采用 POE |
| 技术性拒绝 | B：<3 午夜直接 deny；C：可自动；A：一律不终审 | 仲裁：三条件齐备才判 TECHNICAL_NOT_MET + 非医师确认 + RFI |
| 引用 | A/B：生成原文 + 字符串匹配；C：span ID | 三方采用 span ID + 锚点短语 |
| 拓扑 | C：按标准扇出，约 25 次调用/例；A：3 个 LLM 角色 | 采用 A 的 3 角色；扇出改为 A4 ablation |
| 病历检索 | B：单病例 BM25 为主；C：整份进上下文 | 实测长度后采用整份进上下文 |
| 主指标 | A：false-adverse；B：silver F1；C：gold + 反事实 | gold + 成对的 false-adverse/false-approve + over-pend |
| Discharge Medications | A/B：保留；C：删除 | 仲裁：删除（格式泄漏），用药改用 fact cards；A/B 签字接受 |
| 解码 | C：Reviewer ×3 采样（引 Qwen3 文档）；A/B：T=0 | 仲裁：T=0 为主，自一致性设门槛；C 承认 Qwen 那条建议针对的是 thinking mode |
| 3-day 模式 / TEAM | 三种呈现方式 | 两张决策表零成本全量报告；TEAM 排除 |
| 州法 | A 原列为约束 | A 自我更正：§422.402 规定 MA 优先于州法 → 只作背景 |
| 仲裁追加 | — | Critic 抽审 20% APPROVE；改称"licensed clinical reviewer"；dev 也限 2011–2018 |

---

## 9. 与旧计划（`snf_pa_multi_agent_rag_plan.md`）的主要差异
1. 不再排除 observation 住院（旧计划会丢掉约 23% 的 SNF 病例，并造成偏倚）。
2. 午夜数改用 POE 住院医嘱口径；引入 T_pa；限定年代 2011–2018。
3. 6 个 agent → 3 个 LLM 角色 + 代码 / 工具 / 模板；最终决定由代码汇总。
4. 引用从"生成 quote + 字符串匹配"改为 span ID。
5. 主评估从 silver P/R/F1 改为 gold 逐条 + 成对错误率 + 反事实。
6. 规模从 2,000+300 改为 300（本地 14B 跑不动）。
7. 模型改为可插拔：POC 用 Claude Code / OpenAI 订阅 + 本地 qwen3:14b 对照，后续切换 AWS Bedrock（v3）。
8. 政策语料补充：§422.101(c)、§422.566(d)、CMS 2024-02 FAQ、CMS-0057-F（72h / 7 天，2026-01-01 起）、分级 Tier 1–3。
9. 工程问题：`.gitignore` 误伤源码、`.csv.gz` 路径、N=50 vs 300 不一致。

---

## 10. 主要来源
- 42 CFR 409 Subpart D（本地 `policy_docs/42cfr409_subpartD.xml`）；BPM Ch.8（本地 `policy_docs/bp102c08.pdf`）
- 42 CFR 422.566：https://www.law.cornell.edu/cfr/text/42/422.566 ；422.101：https://ecfr.io/Title-42/Section-422.101
- CMS-0057-F：https://www.cms.gov/priorities/burden-reduction/overview/interoperability/policies-and-regulations/cms-interoperability-and-prior-authorization-final-rule-cms-0057-f/cms-interoperability-and-prior-authorization-final-rule-cms-0057-f
- CMS-4201-F：https://www.cms.gov/newsroom/fact-sheets/2024-medicare-advantage-and-part-d-final-rule-cms-4201-f
- OIG OEI-09-24-00331（2026-06，SNF PA 拒绝在申诉后 95% 被推翻）：https://oig.hhs.gov/reports/all/2026/medicare-advantage-organizations-overturned-nearly-all-appealed-prior-authorization-denials-for-skilled-nursing-facility-admission-raising-concerns-about-initial-denials/
- TEAM 3-day 豁免：https://www.cms.gov/files/document/mm14098-implementing-transforming-episode-accountability-model-skilled-nursing-facility-3-day-rule.pdf
- WISeR：https://www.kff.org/medicare/examining-the-potential-impact-of-medicares-new-wiser-model/
- Qwen3 采样建议：https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html
- MIMIC-IV-ED 2.2：https://physionet.org/content/mimic-iv-ed/2.2/ ；MIMIC-IV-Note 2.2：https://physionet.org/content/mimic-iv-note/2.2/ ；MIMIC-IV 3.1：https://physionet.org/content/mimiciv/3.1/
- 多智能体医疗必要性判定（BioNLP 2024）：https://arxiv.org/html/2404.17977v2
- 多智能体 vs 单智能体系统综述：https://pmc.ncbi.nlm.nih.gov/articles/PMC12407621/
- ArchEHR-QA 2025（verbatim 引用）：https://preview.aclanthology.org/setup/2025.bionlp-share.8
- llama.cpp Arc 140V 问题：https://github.com/ggml-org/llama.cpp/issues/18946
- （v2）CMS-0057-F fact sheet（2027 Prior Authorization API、X12 278 执法裁量）：https://www.cms.gov/files/document/fact-sheet-cms-interoperability-and-prior-authorization-final-rule-cms-0057-f.pdf ；时间线汇总：https://digitalhealth.folio3.com/blog/?p=15546 ；https://connextglobal.com/ms-prior-authorization-mandate-2027/
- （v3）Claude Code headless 模式（`-p`、`--output-format json`、`--json-schema`、`--bare` 不读订阅登录）：https://code.claude.com/docs/en/headless
- （v3）Codex 非交互模式（`codex exec`、`--output-schema`、`-o`、`--json`、`--ephemeral`）：https://developers.openai.com/codex/noninteractive
- （v2）WellSky 自 2026-01-05 起管理部分 MA 计划 post-acute PA：https://providerinfo.bcbsm.com/documents/alerts/2026/202602/alert-20260210-change-auth-snf-interrupted-stays.pdf
- （v2）参议院 PSI 关于 post-acute AI 拒绝：https://www.hcam.org/?p=15342
- （v2）Cohere Health C 轮：https://www.fiercehealthcare.com/ai-and-machine-learning/cohere-health-lands-90m-series-c-round-expand-ai-use-cases
