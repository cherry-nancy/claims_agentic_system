# 分歧记录：病历处理、去泄漏与时点（第 ③ 步）

- 对应：设计第 12 节第 ③ 步"数据来源 adapter"（设计 v8 3.3–3.6）
- 我们的计划：`zhijie-20261108`，`reports/step3_plan.md`；实现完成后补充 commit
- 队友：Hui Li `origin/snf-criterion-cards` @ `9ac1584`（病历处理代码 `84832e0`）；cfeng `origin/cfeng` @ `b60f21e`（去泄漏 rules-v3 `3b279cc`）
- 记录日期：2026-11-08

**整体背景**：出院小结是在病人出院**之后**写的，里面常常直接写着去向（"discharged to rehab""accepted at SNF"）。如果不处理就喂给模型，模型会直接"看答案"，所有评估结果都失效（标签泄漏）。同时，PA 是在出院前提交的，系统只能看到提交时刻 T_pa 之前的信息（CLAUDE.md 硬规则 2）。

这一步要做三件事：
1. 把病历切成可以引用的句子，并给每句一个 ID；
2. 删掉或遮蔽透露去向的内容；
3. 对带时间戳的数据按 T_pa 截断。

三人都做了前两件，但做法不同。

---

## 1. 句子 ID 在去泄漏之前编号，还是之后

**背景**：系统的每条证据都要引用句子 ID（硬规则 5），gold 标注也按句子 ID 记。设计 3.3 要求"同一份病历重跑，ID 不变"。去泄漏规则会反复修改：每次人工抽查发现漏网说法，都要加规则。

**Hui Li**：先给原文每一句编号，再去泄漏；被删的句子留下空号。
```python
# origin/snf-criterion-cards:src/snf_pa/data/redact.py L102-111
def index_note(text: str) -> list[Span]:
    """All sentences of the note with span IDs, before any redaction."""
```

**cfeng**：只给去泄漏后显示出来的句子编号，不留空号。
```
# origin/cfeng:src/snf_pa/data/redact.py L26-30（文件头说明）
IDs are numbered over the shown sentences only: numbering the original sentences would leave gaps where
text was removed, and the gaps would leak like markers do.
```

**我们**：**采用 Hui Li 的做法**（先编号）。谁定的：实现时的判断，依据设计 3.3。

**依据**：
- cfeng 的做法里，任何一条规则改动都会让后面所有句子重新编号。已有的 gold 标注、缓存的模型结果、trace 里的引用会全部对不上。
- cfeng 担心"空号泄漏"，这个顾虑成立，但影响很小。Hui Li 的统计里，回家病人的病历含遮蔽的比例（12.7%）反而高于去 SNF 的（7.3%），空号的有无并不指向 SNF。

**对结果的影响**：只影响 ID 的稳定性和可追溯性，不影响判定内容。

**待讨论**：如果担心空号，可以在给模型看的版本里不显示 ID 数字，只在内部映射。目前不做。

---

## 2. 哪些段落保留、哪些删除

**背景**：设计 3.5 列了保留和删除两张表。删除的理由有两种：段落本身就是写去向的（Disposition、Facility、Followup），或者写于 T_pa 之后、格式本身会泄露去向（出院用药）。

**Hui Li**（`redact.py` L17–18）：
- 总删 DISPO、FAC、DXDC、DCI、FU；
- MEDDC 只在 strict 模式删；
- HDR、PROC、FH、MEDADM 保留。

**cfeng**（`redact.py` L54–59）：
- **保留** Discharge Diagnosis；
- Discharge Instructions 里的 PT、Treatments Frequency、WOUND CARE、ANTICOAGULATION、ACTIVITY AND WEIGHT BEARING 几个子块**保留**；
- Discharge Medications 在 realistic（默认）模式保留，strict 模式删；
- 病历头只留 Service 和 Allergies。

**我们**：
- 按设计 3.5，DISPO、FAC、DCI、FU、DXDC、MEDDC **全删**，包括 cfeng 保留的子块；
- 设计没归类的 HDR、PROC、FH、MEDADM 建议保留，病历头只留科室和过敏史，**待用户确认**（`step3_plan.md` 第 8 节）。

**依据**：
- Discharge Diagnosis 和 Discharge Instructions 都写于出院时、给出院后用，不是 T_pa 时可得的信息。
- cfeng 保留的"PT""伤口护理"子块是出院后的照护指导，内容本身会随去向不同而不同（例如去 SNF 的病人会写由 SNF 护士换药）。

**对结果的影响**：
- 保留这些子块，模型能看到更多照护需求信息，但也多了泄漏风险，而且混入了 T_pa 之后的信息。
- 结果会偏乐观，影响程度未评估。

---

## 3. 遮蔽怎么留痕迹

**背景**：整句删除不留痕迹，模型无从知道删过什么；但一个句子里只有半句讲去向时（例如 PT 说"需要两人协助转移，建议去 rehab"），前半句是有用的功能描述，要保留。

**Hui Li**：整句命中直接删除；PT/OT 句子里的半句替换为 `[REDACTED-DISPO]`（`redact.py` L14、L153–156）。

**cfeng**：只删除不插入，连半句也直接删掉，不留任何标记；列表删掉条目后重新编号（`redact.py` L14–19）。

**我们**：整句删除不留痕迹（两位队友相同）；半句遮蔽用 `___` 替换，不用 `[REDACTED-DISPO]`。不做列表重新编号。谁定的：实现时的判断。

**依据**：
- `[REDACTED-DISPO]` 这个标记本身就告诉模型"这里讲过去向"。
- MIMIC 去标识后本来满篇都是 `___`，用它不会额外暗示什么。
- 直接删半句又可能让句子读不通（"需要两人协助转移，"）。
- 列表重新编号需要改写原文，会让偏移量和原文对不上。

**对结果的影响**：很小。主要差别是 `[REDACTED-DISPO]` 可能成为一个泄漏信号。

---

## 4. 去向判定规则与触发词表

**背景**：同一个去向词在不同段落里意思不同。在病程里写"plan for rehab"是去向；在现病史里写"lives at nursing home""recently discharged from rehab"是入院前的住所和病史。后者是 T_pa 前可得的真实信息，也是 C6（是否只能在 SNF 提供）的证据。

**Hui Li**：两档规则。出院时写的段落（HC、COND、MEDDC）里出现任何去向词就遮蔽；其他段落要"去向词 + 出院计划语境"才遮蔽（`redact.py` L19–22、L114–129）。词表在 L26–53。

**cfeng**：对所有保留段落套同一套触发词（`redact.py` L84–105）。词表更宽：
- 随访和门诊（`outpatient`、`PCP`、`f/u`）；
- `hospice`；
- 出院宣教套话（"verbalized understanding""discharge teaching"）；
- 保险授权。

**我们**：采用 Hui Li 的两档逻辑，词表合并两人的（加上 cfeng 多出来的那些词）。谁定的：实现时的判断。

**依据**：
- cfeng 对所有段落一视同仁，会把现病史里"seen in outpatient clinic""per PCP"这类入院前信息也删掉，删多了。
- Hui Li 的词表漏了随访、宣教套话这些和去向强相关的说法。cfeng 的报告里，这些说法在两组病人中的分布差别很大。

**对结果的影响**：
- 用 cfeng 的做法，残余更少，但会误删入院前信息，C6 的证据变少；
- 用 Hui Li 的做法，保留入院前信息，但原词表有漏网说法（她的 strict 版本在 HPI 里仍有残余）。
- 合并后两边的问题都减轻。效果由第 ③ 步的三道检查验证。

**待讨论**：入院前住所（"从 SNF 入院"）要不要遮蔽？Hui Li 的报告提出过这个问题（她分支上的 `reports/step2_leakage_report.md` 第 6 节第 1 条：SNF 组 40 份、回家组 5 份）。我们按设计保留，因为这是真实可得的信息；如果文本探针显示它主导了预测，再讨论做敏感性分析。

---

## 5. realistic 病历包

**背景**：两位队友都做了两个版本。strict 删掉出院用药和 PT/OT 建议；realistic 保留清洗过的出院用药和 PT/OT 建议，作为消融实验。

**Hui Li**：`redact.py` L3–5、L174–175。**cfeng**：`redact.py` L21–24，realistic 是默认模式。

**我们**：不做 realistic。谁定的：设计 v8 没有这个消融（`8560e4b` 版设计里有，叫 D8，后来删掉了）。

**依据**：出院用药写于 T_pa 之后（设计 3.5），PT/OT 的去向建议就是答案本身。

**对结果的影响**：少一组对照。realistic 能说明"如果泄漏没清干净，结果会好多少"，有参考价值，但不是主结果。

**待讨论**：如果三人认为需要这个对照，可以作为第 ⑧ 步的额外配置加回来。

---

## 6. 影像报告按什么时间判断可得

**背景**：影像报告在检查做完、医生签署之后才存在。PA 提交时，没签的报告看不到。

**Hui Li**：没有处理影像。

**cfeng**：按签署时间 `storetime`，缺失时退回 `charttime`，判断是否在出院前 24 小时之前（`origin/cfeng:src/snf_pa/data/imaging.py` L65、L164）。

**我们**：**采用 cfeng 的时间规则**，截止点用设计的 `T_pa = max(出院 − 24h, 住院起点)`；只取 IMPRESSION 段。实测 `storetime` 全部非空。

**对结果的影响**：一致，只差 T_pa 的定义（见第 8 条）。

---

## 7. 出院小结里抄进来的影像文字

**背景**：出院小结的 Pertinent Results 段常常抄进影像报告原文，包括 T_pa 之后的检查。

**cfeng**：用 3-gram 匹配找出抄进来的影像文字，替换成 T_pa 前已签署的 IMPRESSION（`imaging.py`）。

**Hui Li**：没有处理。

**我们**：暂不做。谁定的：设计第 15 节已把"出院小结写于出院后"列为接受的局限。

**对结果的影响**：Pertinent Results 里可能残留 T_pa 之后的影像结论，结果偏乐观，影响未评估。cfeng 的测试显示，截点换成 −24h 或 −48h，影像 AUC 基本不变（0.651 / 0.648，他的初版计划改动）。

**待讨论**：这是"我们计划里没有的"改进。如果第 ③ 步的文本探针显示 Pertinent Results 段泄漏明显，再考虑纳入。

---

## 8. T_pa 的定义

**背景**：T_pa 是假设的 PA 提交时刻，决定系统能看到哪些信息。

**Hui Li**：没有实现。

**cfeng**：`dischtime − 24h`，另做 −48h 敏感性分析（初版计划改动）。

**我们**：`max(出院 − 24h, 住院起点)`，住院起点取住院医嘱时间。谁定的：设计 3.1、3.4。

**依据**：住院不到 1 天的病例，`出院 − 24h` 会早于住院开始，没有意义。

**对结果的影响**：只影响极短住院的少数病例。

**待讨论**：cfeng 的 −48h 敏感性分析我们计划里没有，值得作为第 ⑧ 步的附加分析。

---

## 9. 泄漏探针用哪些病例

**背景**：文本探针用 TF-IDF + 逻辑回归预测去向，看去泄漏前后 AUC 降了多少（设计 3.5 第三道检查）。CLAUDE.md 硬规则 3 要求开发过程中不碰 test。

**Hui Li**：在 2,655 篇样本外的池子上训练，再在样本（含 test 129 例）上评估（`leakage_pool.py`）。

**cfeng**：在 3,000 篇样本外池子上训练，评估集是整个样本，**没有排除 `split == 'test'`**（`origin/cfeng:src/snf_pa/data/leakage.py` L124–130）。

**我们**：只用 dev 病人中不在 dev 抽样里的住院，做 5 折交叉验证；完全不碰 test。谁定的：硬规则 3。

**对结果的影响**：队友的做法等于在开发阶段看过 test 上的中间结果。之后再在 test 上报告正式结果，test 已经不是完全独立的了。

**建议**：队友的探针评估集排除 test 病例。

---

## 10. LLM 猜去向探针（我们计划里没有的）

**背景**：两位队友都用本地小模型读处理后的病历猜去向，作为另一种泄漏检查。

**Hui Li**：medgemma:4b、gemma4。原文阳性对照也没猜对（medgemma 原文 AUC 0.26），说明小模型本身做不了这个任务。**cfeng**：qwen3.5:9b，只用 dev（`leakage_llm.py` L81）。

**我们**：本步不做。谁定的：实现时的判断。

**依据**：
- 设计的三道检查（单元测试、人工抽查、文本探针）已覆盖；
- 队友的结果显示，小模型连原文都猜不准，阳性对照失败，这个探针的结论不可用。

**待讨论**：等第 ⑥ 步接上订阅模型后，可以用强模型做一次，作为人工抽查的补充。

---

## 实现与验证结果（2026-11-08 补充）

- 实现：`src/snf_pa/adapters/sources/discharge_note.py`（采用 Hui Li 的切分与编号，来源写在文件头）、`radiology.py`（采用 cfeng 的签署时间规则）、`timeline.py`。
- **第 4 条（入院前住所要不要遮蔽）有了数据**：文本探针在 dev 病人上做了敏感性分析，把入院前段落里所有带去向词的句子也删掉，AUC 从 0.844 变为 0.843（`reports/step3_adapter.md` 4.4）。保留入院前住所和康复史**不会**让模型更容易猜出去向，支持按设计保留。
- **第 4 条（词表）补充**：在两人词表之外新加了一条"出院时段落里给病人本人的出院指导"（"was instructed to complete / seek ..."），来自我们文本探针的 top features。"educated on" 这类教学用语保留，因为患者教育本身是 skilled 服务（42 CFR 409.33(a)(3)）。cfeng 的"discharge teaching / verbalized understanding"已并入。
- **第 9 条（探针用哪些病例）**：我们的探针只用 dev 病人中不在 dev 抽样里的 4,000 例住院，原文 AUC 0.926 → 处理后 0.844。与两位队友的数字口径不同（Hui Li 处理后 held-out 0.652、原文 0.793，用的是 300 例样本含 test），不能直接比较。

## 11. 住院起点用哪些医嘱（新增）

**背景**：C1（3 天住院规则）从住院医嘱时间起算午夜数（设计 3.4、6.2）。MIMIC 的住院 / 观察状态写在 `poe_detail` 的 `Admit category` 字段里。

**Hui Li**：没有用 POE，按 `admittime` 到 `dischtime` 的日期差计算（`origin/snf-criterion-cards:src/snf_pa/data/cohort.py` L56）。

**cfeng**：同上，`origin/cfeng:src/snf_pa/data/cohort.py` L55。

**我们**：最早的"Admit to inpatient"医嘱（Admit / Transfer / Postop 子类，New 或 Change 事务），没有就退回入院时间并打标记（`src/snf_pa/adapters/timeline.py`）。谁定的：设计 3.4；子类与事务类型由实现时按数据核查确定，设计措辞的修改待用户同意。

**依据**：按这个口径能精确复现附录 A 的 78% / 14,384 / 37,337。按日期差算，有 38,828 例去 SNF 的病例 ≥3 午夜，按医嘱只有 37,337 例，高估约 3.8%。

**对结果的影响**：用日期差会把部分观察期算进住院，C1 偏宽，`TECHNICAL_NOT_MET` 会被漏判。

## 12. Pertinent Results 是否一律算"出院时写的段落"（新增，独立审查后）

**背景**：两档规则里，"出院时写的段落"只要出现去向词就删；其他段落要有出院计划语境才删。有的病历模板（如骨科）把病程叙述写在 Pertinent Results 里，例如"Mr ___ is discharged to rehab in stable condition"。

**Hui Li**：只有在病历没有 Brief Hospital Course 标题时，才把 PR 当作出院时段落（`origin/snf-criterion-cards:src/snf_pa/data/redact.py` L160–161）。

**cfeng**：所有保留段落用同一套触发词，不分档（`redact.py` L84–105）。

**我们**：PR 一律算出院时段落（`discharge_note.py` 的 `BROAD`）。谁定的：实现时的判断，起因是第 ③ 步独立审查在 dev bundle 里发现上面那句。

**对结果的影响**：PR 里的化验和影像结论几乎不含去向词，保留率仍有 96%；堵住了模板差异造成的漏洞。

## 13. 触发词里的空格要匹配换行（新增）

**背景**：MIMIC 病历是硬换行的，"follow-up\nwith""discharged to\nrehab"会跨行。

**cfeng**：所有触发词里的空格都匹配任意空白（`origin/cfeng:src/snf_pa/data/redact.py` L83 注释、L105 `v.replace(" ", r"\s+")`）。

**Hui Li**：触发词用字面空格（`redact.py` L26–53），跨行的说法匹配不上。

**我们**：**采用 cfeng 的做法**。最初移植 Hui Li 代码时漏了这一点，是第 ③ 步独立审查后宽网阅读发现的主要漏洞根因。

**建议**：Hui Li 的分支同样受影响，建议也改。

## 14. 出院时段落里的照护安排与过渡事项（新增，两位队友都没有）

**我们**新增：出院时段落里提到 PCP、诊所、门诊、安排、传真、placement 讨论、CM / SW、家用设备与服务（"home O2 was arranged""hospital bed at home"）的句子删除；"TRANSITIONAL ISSUES"等小标题之后的内容和 `[ ]` 待办行全部删除。依据：宽网检查人工阅读发现这些句子大量残留，而且都是出院后的安排。代价：病程段句子保留率降到 77%。

**待讨论**：这批规则删得比较宽，三人可以讨论是否值得用更精细的规则换回部分临床信息。
