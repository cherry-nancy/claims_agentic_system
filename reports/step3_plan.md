# 第 ③ 步计划：数据来源 adapter

- 日期：2026-11-08
- 分支：`zhijie-20261108`（`d5fab9d`，已 push），目录 `D:\Repo\claims_agentic_system`
- 状态：计划。第 8 节有 1 个问题要你定；其余细则由我决定，理由写在下面和分歧记录里。

## 1. 这是第 12 节的哪一步

第 ③ 步"数据来源 adapter"（设计 v8 第 12 节附注 3，内容 3.3–3.6、2.1）。前置第 ② 步已完成（`d5fab9d`）。

**完成标准**（设计原文）：
- 残余去向词为 0；
- 人工抽查 50 篇通过；
- 遮蔽后文本探针的 AUC 明显下降；
- 同一病例重跑 span ID 不变；
- 每条证据都符合统一格式、可得时间 ≤ T_pa；
- 数据来源登记表就绪。

**人工关卡**：50 篇人工抽查由你（或有临床背景的人）做，我只准备抽查页面（CLAUDE.md「无人值守运行」）。

## 2. 依据
- 设计 v8：2.1（登记表、证据格式）、3.3（`CaseBundle`）、3.4（时间线）、3.5（保留 / 删除 / 遮蔽、三道泄漏检查）、3.6（事实卡）、第 15 节风险（出院小结写于出院后）。
- `plan/decision_log.md` D-006：抽样文件里的出院去向、场景、诊断类标签**不得进入 `CaseBundle`**。
- CLAUDE.md 硬规则 2（时点）、3（test 隔离）、4（缺失）、5（可追溯）、9（病历是数据）、10（silver 不是真值）。
- 队友对照：`reports/teammate_survey.md` 2.2；本次逐行读了 Hui Li 的 `sections.py`、`redact.py`（`84832e0`）和 cfeng 的 `redact.py`（`3b279cc`，rules-v3）。分歧记录见 `reports/teammate_diff_redaction.md`。

## 3. 开工前的核查（2026-11-08，只读）

| 项 | 结果 |
|---|---|
| 住院医嘱 | `poe` 的 ADT/Admit 医嘱，在 `poe_detail` 里有 `Admit category = 'Admit to inpatient'`（121,654 条）和 `'Place in observation'`（75,574 条），可以直接实现设计 3.4 |
| 影像报告 | 86.8% 有 `IMPRESSION:` 段；`storetime` 全部非空，可按签署时间判断是否在 T_pa 前可得 |
| 出院小结段落 | 各段标题出现率 94–100%；Brief Hospital Course 86.5%（缺的时候病程写在 Pertinent Results 里，Hui Li 已处理过这种情况） |

## 4. 用不用队友的代码（我的决定，详见分歧记录）

| 部分 | 决定 | 理由 |
|---|---|---|
| 段落切分、切句、span ID | **采用 Hui Li 的** `sections.py` 和 `index_note()` / `sentences()`，按设计 3.5 改段落表 | 先给原文每句编号再去泄漏，改规则不会重新编号，满足设计 3.3"重跑 ID 不变"。cfeng 按显示出来的句子编号，规则一改 ID 就变 |
| 去向判定逻辑 | **采用 Hui Li 的两档规则**：出院时写的段落（病程、出院状况）里出现去向词就遮蔽；入院前的段落要"去向词 + 出院计划语境"才遮蔽 | 入院前住所（"从 SNF 入院""住在养老院"）是 T_pa 前就有的真实信息，也是 C6 的证据，不该删 |
| 触发词表 | **合并**：Hui Li 的词表加上 cfeng 多出来的随访、门诊、PCP、hospice、出院宣教套话 | cfeng 的词表覆盖了 Hui Li 漏掉的说法；每加一个词都有单元测试 |
| 遮蔽标记 | 整句命中就删掉、不留痕迹（两位队友都这样）；半句遮蔽用 `___` 代替 Hui Li 的 `[REDACTED-DISPO]` | MIMIC 去标识本来就满篇 `___`，用它不会额外暗示"这里删过去向" |
| 删除哪些段 | 按设计 3.5：Disposition、Facility、Discharge Instructions、Followup、Discharge Diagnosis、Discharge Medications **全删** | cfeng 保留了 Discharge Diagnosis 和 Discharge Instructions 里的 PT、伤口等子块；设计明确要删 |
| realistic 病历包（保留 PT/OT 建议和出院用药） | 不做 | 设计没有这个消融；出院用药写于 T_pa 之后 |
| 影像 | **采用 cfeng 的时间规则**：按 `storetime ≤ T_pa` 判断可得；只取 IMPRESSION | 和设计 3.5 一致；检查做了但报告没签，在 T_pa 时就还不存在 |
| 出院小结里抄进来的影像文字替换（cfeng） | 暂不做 | 设计第 15 节已把"出院小结写于出院后"列为接受的局限 |
| 泄漏探针 | **参考两位队友**的 TF-IDF + 逻辑回归，但**只用 dev 病人**训练和评估 | 队友的探针评估集包含了 test 病例（cfeng `leakage.py` L128），违反硬规则 3 |

## 5. subtask（每个都写了怎么验）

### 3a. schema 与数据来源登记表
- 输出：
  - `src/snf_pa/schemas.py`：`CaseBundle`、`EvidenceItem`、`Timeline`、`Demographics`，用 Pydantic，字段照设计 3.3；
  - `knowledge/sources.yaml`：`discharge_note`、`radiology`、`prescriptions`、`poe` 四个来源，每个写明原始表、T_pa 时间字段、去泄漏规则、产出的证据类型、实现模块；
  - `registry.py` 加读取和校验。
- 验：
  - schema 单元测试，其中包括一个"禁止字段"测试：`CaseBundle` 里不能出现 `discharge_location`、`scenario`、诊断类标签；
  - 登记表一致性测试：每个来源都有 T_pa 时间字段和实现模块。

### 3b. 时间线与 T_pa
- 输出：`src/snf_pa/adapters/timeline.py`。
  - 住院起点 = 最早、未撤销的 `Admit category = 'Admit to inpatient'` 医嘱时间。没有这条医嘱时退回入院时间，并打标记（设计 3.4）。
  - 另外记录 ED 时段、观察医嘱时间；`T_pa = max(出院 − 24h, 住院起点)`。
- 验：
  - 单元测试覆盖：有住院医嘱、只有观察医嘱、两种都有、医嘱后被撤销、没有医嘱；
  - **核对附录 A 里依赖住院医嘱的 3 个数**（第 ② 步留下来的）：SNF + 出院小结中 78% 有住院医嘱；先观察后住院 14,384；按医嘱算 ≥3 午夜 37,337；
  - 第 4 个数（30 天前序住院 940）属于 C1，留给第 ④ 步。

### 3c. 出院小结：切段、切句、span ID
- 输出：`src/snf_pa/adapters/sources/discharge_note.py`，从 Hui Li 的 `sections.py` / `redact.py` 拿来改。来源分支和 commit 写进代码注释和 commit message。
- 段落表按设计 3.5：
  - 保留 CC、HPI、PMH、SH、PE、PR、HC、COND；
  - 删除 DISPO、FAC、DCI、FU、DXDC、MEDDC；
  - HDR、PROC、FH、MEDADM 见第 8 节问题 1。
- 验：
  - 单元测试：在合成病历上测段落顺序、"p.o." 这类缩写不被切开、偏移量能还原原文；
  - **重跑稳定性**：dev 100 例各跑两次，span ID 和文本 hash 完全一致；
  - 改一条遮蔽规则后，没被遮蔽的句子 ID 不变。

### 3d. 去泄漏
- 输出：同一模块的 `redact()`，规则见第 4 节。
- 验，即第一道检查（单元测试）：
  - 合成病历上每类说法都有"应删 / 应留"用例，包括"PICC placement""subacute infarct""从 rehab 入院"这类必须保留的；
  - **真实数据残余扫描**：对 dev 病人的处理后文本扫描残余去向词，口径是"出院时写的段落里出现去向词，或其他段落里去向词 + 计划语境"，要求为 0。不为 0 就修规则，不放宽口径。

### 3e. 第二道检查：人工抽查 50 篇（人工关卡）
- 输出：
  - `research/review_page.py`：从 **dev 病人**里随机抽 50 篇（固定种子），生成静态 HTML 页面；只显示处理后文本，不显示去向；
  - 一个记录表，你填"能 / 不能看出去向"和理由。
- 验：你做完抽查后，我统计结果。有"能看出"的就补规则、重扫，修改后按设计重新抽 50 篇。**这一步停下来等你。**

### 3f. 第三道检查：文本探针
- 输出：`research/leakage_probe.py`。用 dev 病人中**不在 dev 抽样里**的住院做 5 折交叉验证：TF-IDF + 逻辑回归预测是否去 SNF，分别在原文和处理后文本上跑，报告 AUC 和 bootstrap 置信区间。需要加依赖 `scikit-learn`（`uv add`）。
- 验：处理后 AUC 明显低于原文。设计没有给数值阈值，所以两边的数和置信区间都报告，你来判断够不够"明显"。同时列出处理后文本里权重最高的词，人工看有没有漏网的说法。**不碰 test 病人。**

### 3g. 影像与事实卡
- 影像：`sources/radiology.py`，取住院期间、`storetime ≤ T_pa` 的报告的 IMPRESSION 段，切句编号（`RAD:<note_id>:s<n>`）。
- 事实卡：`sources/prescriptions.py`、`sources/poe.py`，按需求理由目录里的服务类规则生成**量化的**一句话证据，例如"T_pa 前 48h 静脉万古霉素 4 次（最后一次在 T_pa 前 6h）""PT 会诊 3 次"。`provenance` 记表名和主键。
- 验：
  - 每条证据的 `available_at ≤ T_pa`，这一条写成测试，对所有 dev 病例断言；
  - 合成数据上的边界用例：恰好在 T_pa、T_pa 后 1 分钟；
  - 抽 10 例人工看事实卡文字和原表是否一致（我来做）。

### 3h. 组装 `CaseBundle`
- 输出：`src/snf_pa/adapters/mimic.py`，生成 dev 100 例 → `data/sample/case_bundles/dev/<case_id>.json`，带 `content_hash`。
  - 按 CLAUDE.md，处理后的病历可以进 git；单个文件很小，合计几 MB。
  - **test 200 例本步不生成**：生成本身不算"看结果"，但留到正式评估前、由你触发时再生成，避免任何在 test 上调试的机会。
- 验：
  - 两次生成 hash 相同；
  - 所有证据 ID 唯一；
  - 禁止字段测试通过；
  - `assumed` 里写明 C2、C7、C8 的假设；
  - `missing` 记录缺的材料（例如没有 PT 记录）。

### 3i. 报告、审查、提交
- `reports/step3_adapter.md`：命令、原始输出、完成标准对照。
- 独立审查。
- 设计文档如需改动（第 8 节问题 1），写进 decision_log 并重新冻结。
- 人工抽查通过后 commit。

## 6. 碰哪些数据
- **读**：`data/derived/parquet/` 下的 `discharge`、`radiology`、`poe`、`poe_detail`、`prescriptions`、`admissions`、`patients`、`edstays`、`transfers`，以及 `data/derived/cohort/pool.parquet`、`data/splits/*`（只读，已冻结）。**本步不读原始数据目录**。
- **写**：
  - `src/snf_pa/schemas.py`、`src/snf_pa/adapters/{timeline,mimic}.py`、`src/snf_pa/adapters/sources/*`；
  - `knowledge/sources.yaml`；
  - `research/{review_page,leakage_probe}.py`；
  - `data/sample/case_bundles/dev/`（进 git）；
  - 抽查页面放 `data/derived/review/`（不进 git）；
  - `reports/step3_*.md`；
  - 测试。
- **test 病人**：本步只在"按 dev / test 过滤"时读到 test 的 `subject_id`，不生成、不读 test 的处理后文本，探针和抽查都只用 dev。

## 7. 可能撞上的硬规则

| 硬规则 | 在哪 | 怎么避免 |
|---|---|---|
| 2 时点 | 3b、3g、3h | 所有带时间戳的证据只取 ≤ T_pa；测试断言；出院小结整篇写于出院后，这是设计接受的局限，报告里写明 |
| 2 / 10 | 3h | 禁止字段测试：去向、场景、诊断类标签不进 `CaseBundle` |
| 3 test 隔离 | 3e、3f、3h | 抽查、探针只用 dev 病人；test 的 bundle 不生成 |
| 7 不改标准 | 3d | 残余不为 0 时修规则，不改扫描口径；单元测试的预期不为通过而改 |
| 9 病历是数据 | 3c–3h | 不执行病历里的任何文字；本步不调 LLM |

## 8. 需要你定的

1. **设计 3.5 没有归类的 4 个段落怎么处理？** 设计列了"保留"和"删除"两张表，下面 4 个段落都不在里面：

   | 段落 | 内容 | 建议 |
   |---|---|---|
   | 病历头（HDR） | 科室、过敏史、主治医生 | 只留科室和过敏史 |
   | Major Surgical or Invasive Procedure（PROC） | 住院期间做过的手术和操作 | 保留 |
   | Family History（FH） | 家族史 | 保留 |
   | Medications on Admission（MEDADM） | 入院时的用药 | 保留 |

   保留的理由：这些都是 T_pa 之前就有的信息，不含出院去向，其中手术和入院用药对判断 skilled 需求有用；两位队友也都保留了。同意的话，我在设计 3.5 的保留表里补上这几项，写进 decision_log。

## 执行中的变更

| 日期 | 改了什么 | 为什么 | 谁定的 | 详细记录 |
|---|---|---|---|---|
| 2026-11-08 | 第 8 节问题 1：4 个未归类段落按建议保留（病历头只留 Service、Allergies） | — | 用户 | `plan/decision_log.md` D-007 |
| 2026-11-08 | 3b 住院医嘱口径：New 或 Change、Admit / Transfer / Postop 子类（计划写的是设计 3.4 的 New-only） | New-only 与附录 A 不符（57% vs 78%）；观察转住院记为 Change；出院医嘱下单于 T_pa 之后，不用作起点 | 实现时的判断，设计 3.4 改动**待用户同意** | `step3_adapter.md` 3.1 |
| 2026-11-08 | 3d 新增规则 `discharge_self_care`（出院时段落里给病人本人的出院指导） | 第一轮探针 top features 发现 "instructed to" | 实现时的判断 | `step3_adapter.md` 4.3、4.4 |
| 2026-11-08 | 3d 残余扫描两次不为 0（1 例、74 例），都修了根因 | `At___` 粘连；新规则未同步到半句遮蔽 | — | `step3_adapter.md` 4.3 |
| 2026-11-08 | 3g 处方事实卡 provenance 改为"药名 + pharmacy_id" | 复核发现 pharmacy_id 不唯一（药与稀释液共用） | — | `step3_adapter.md` 4.5 |
| 2026-11-08 | 3f 探针加了"连入院前去向句也删"的敏感性变体 | 回答 Hui Li 留下的入院前住所问题 | 实现时的判断 | `step3_adapter.md` 4.4 |
| 2026-11-08 | 3e 抽查样本：dev 病人 25 SNF + 25 非 SNF（计划只写"随机 50 篇"） | 平衡后才能判断"看得出"是否高于随机 | 实现时的判断 | `step3_adapter.md` 第 5 节 |
| 2026-11-08 | 独立审查后返工：去泄漏规则多轮加固（PR 始终算出院时段落；空格匹配任意空白；出院移动 / 安排 / 门诊 / 家用设备规则；TRANSITIONAL ISSUES 之后全删）；新增与规则无关的宽网检查 + 人工阅读 | 审查发现 dev bundle 里仍有去向句，原残余检查用同一套规则、看不出 | 审查意见 | `step3_adapter.md` 第 1、7 节 |
| 2026-11-08 | 完成标准"残余为 0"的证据口径改变：规则一致性 0 不再当作"文本干净"的证据 | 规则一致性检查无法发现未知说法 | 实现时的判断 | `step3_adapter.md` 第 1 节 |
| 2026-11-08 | 前序住院窗口改为锚定本次出院（≤ T_pa）；时间线晚于 T_pa 的时间点置空；事实卡包含 ED 等床期间医嘱 | 审查发现 | 审查意见 | `step3_adapter.md` 第 7 节 |
| 2026-11-08 | 出院时段落删得更多：病程保留 77% 句子 | 不泄漏的代价，已请用户知悉 | 实现时的判断 | `step3_adapter.md` 3.2 |

## 评审后修订（2026-11-09）

第 ② 步的候选池、划分、抽样按团队评审重做（D-008）后，本步的 dev 病例、探针和抽查样本都要按新的 dev 重做。方法不变：
- 3e 抽查页：从新的 dev 住院中抽 25 SNF + 25 非 SNF（不再限制每人一次，非 SNF 不含 REHAB）；
- 3f 探针：新的 dev 住院、不在 dev 抽样里；仍按病人分组做交叉验证（防止同一病人跨折）；
- 3h bundle：新的 dev 100 例。

| 日期 | 改了什么 | 为什么 | 谁定的 | 详细记录 |
|---|---|---|---|---|
| 2026-11-09 | 3e / 3f / 3h 按新的 dev 重做 | 第 ② 步重做 | 用户与队友 | `step3_adapter.md` 第 8 节 |
| 2026-11-09 | 宽网抽读再补两条规则（"d/c'ed home"、"home evaluation"） | 新 dev 上抽读发现 | 实现时的判断 | `step3_adapter.md` 第 8 节 |
