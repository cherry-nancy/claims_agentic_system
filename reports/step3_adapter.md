# 第 ③ 步报告：数据来源 adapter（等人工抽查）

- 日期：2026-11-08
- 分支：`zhijie-20261108`（基于 `d5fab9d`），目录 `D:\Repo\claims_agentic_system`
- 计划：`reports/step3_plan.md`（含「执行中的变更」）；队友分歧：`reports/teammate_diff_redaction.md`
- 状态：
  - 代码完成，独立审查做完，审查意见已全部处理（第 7 节）；
  - 3e 人工抽查页面已按最终规则生成，**等你抽查**；
  - 未提交。

## 1. 完成标准对照（设计 v8 第 12 节附注 3）

| 完成标准 | 状态 | 证据 |
|---|---|---|
| 残余去向词为 0 | 规则一致性检查：0（dev 病人全部 26,395 篇）。另做了独立宽网检查 + 人工阅读（见下方说明） | 4.3 |
| 人工抽查 50 篇通过 | **待你做** | 第 5 节 |
| 遮蔽后文本探针 AUC 明显下降 | 0.926 → **0.840**，置信区间不重叠 | 4.4 |
| 同一病例重跑 span ID 不变 | 通过：重建 100 例，hash 逐例相同；ID 在去泄漏前编号 | 4.5 |
| 证据统一格式、可得时间 ≤ T_pa | 通过：schema 校验；所有带时间戳的证据和时间线时间点 ≤ T_pa | 4.5 |
| 数据来源登记表就绪 | `knowledge/sources.yaml` v1，4 个来源 | 4.1 |

**关于"残余为 0"，要如实说明**：
- 规则一致性检查（`residual()`）是把同一套规则在处理后的文本上再跑一遍。它只能证明规则被一致地执行（包括半句遮蔽、`___` 的两种形式），**找不到规则不认识的说法**。第一版报告把它当成了"文本是干净的"的证据，这是错的，独立审查指出了这一点。
- 真正独立的检查分三层：
  1. **宽网扫描**（`wide_net()`）：与去泄漏规则无关，只要"出院 / 安排类词"和"地点 / 回家类词"出现在同一句就标出来，故意多标；
  2. **我人工阅读宽网的命中**：dev 100 例全部 33 条；全量 dev 中出院时段落的命中随机抽 40 条读了 3 轮；
  3. **你的 50 篇人工抽查**。
- 最后一轮抽读 40 条，剩下的基本都是用药史（"home lasix restarted at discharge"），没有新的去向安排。宽网仍有 3,088 条命中，其中 1,979 条在 HPI，属于入院前病史。规则不可能穷尽所有说法，剩下的长尾要靠人工抽查。

## 2. 做了什么

| subtask | 文件 | 说明 |
|---|---|---|
| 3a | `src/snf_pa/schemas.py` | `CaseBundle` 等，`extra="forbid"`，禁止字段清单 |
| 3a | `knowledge/sources.yaml`、`registry.py` | 4 个来源，各写明判断 T_pa 可得用的时间字段 |
| 3b | `src/snf_pa/adapters/timeline.py` | 住院起点、ED、观察医嘱、T_pa。前序住院取"出院前 30 天内出院的、且早于本次入院的住院"（42 CFR 409.30(b)(1)） |
| 3c/3d | `src/snf_pa/adapters/sources/discharge_note.py` | 切分和编号采用 Hui Li 的代码；段落按设计 3.5 / D-007；去泄漏规则见 4.3 |
| 3g | `sources/radiology.py`、`sources/facts.py` | 影像只取 IMPRESSION 且签署 ≤ T_pa；事实卡从本次就诊开始（含 ED 等床期间）到 T_pa |
| 3h | `src/snf_pa/adapters/mimic.py` → `data/sample/case_bundles/dev/*.json` | dev 100 例；时间线上晚于 T_pa 的时间点置空（计划出院日期例外）；test 不生成 |
| 3f | `research/leakage_probe.py` | dev 病人、不在 dev 抽样里的 4,000 例 |
| 3e | `research/review_page.py` | 50 篇盲审页 |
| 依赖 | `pyproject.toml`、`uv.lock` | scikit-learn 1.9.1 |

## 3. 需要你定的事

### 3.1 设计 3.4 的"`transaction_type='New'`"与数据不符（建议改设计）

| 口径（去 SNF 的 42,312 例 Medicare 住院） | 有住院医嘱（有出院小结的） | 先观察后住院 | 按医嘱 ≥3 午夜 |
|---|---|---|---|
| 附录 A | 78% | 14,384 | 37,337 |
| 只取 New、只取 Admit 子类 | 57.4% | 7,249 | 38,378 |
| New 或 Change、只取 Admit 子类 | 71.2% | 13,373 | 37,500 |
| **New 或 Change，Admit / Transfer / Postop / Discharge 子类** | **78.3%** | **14,384** | **37,337** |

- 附录 A 三个数按最后一行的口径精确复现。
- 观察转住院在 MIMIC 里记为 `Change`。
- 系统去掉了 Discharge 子类：出院医嘱下单在 T_pa 之后。代价是去 SNF 病例里有 14 例退回入院时间，按设计 6.2 最多判到 `INSUFFICIENT`。

**建议**把设计 3.4 改为："住院起点：最早的 'Admit to inpatient' 医嘱时间（ADT 的 Admit / Transfer / Postop 医嘱，New 或 Change 事务；观察转住院记为 Change）。出院医嘱下单于出院时，不用作住院起点。"

### 3.2 出院时段落删得更多了（请知悉）
为了堵住审查发现的漏洞，出院时段落（病程、Pertinent Results、出院状况）的规则放宽了：
- 提到 PCP、门诊、诊所、安排、传真、placement、CM / SW、家用设备 / 服务的句子，以及"TRANSITIONAL ISSUES"小标题之后的全部内容，一律删除。
- 结果：病程段保留 77% 的句子，PR 96%，HPI、出院状况约 100%。
- 被删的病程句子里有一部分是有用的临床信息（例如"出院前改了利尿剂剂量并安排了复查"），这是为了不泄漏付出的代价。
- 用药史（"home dose"）不删。

## 4. 命令与原始输出

### 4.1 schema 与登记表
`tests/test_schemas.py`：9 个禁止字段用例、hash 往返、登记表一致性（每个来源有 T_pa 时间字段和实现模块）。全部通过。

### 4.2 时间线
```
$ uv run pytest tests/test_timeline.py -q -m "slow or not slow"
7 passed
```
- 合成用例：ED 里下的住院医嘱；观察医嘱后用 Change 转住院；没有医嘱退回入院时间；只有出院医嘱带类别时不用它；10 小时短住院；前序住院按**本次出院**往前 30 天（一个"入院前 27 天、出院前 32 天"的前序住院必须排除）。
- 原始数据上复现附录 A：78% / 14,384 / 37,337，期望值在 `tests/expected/appendix_a_poe.json`（受保护，已冻结）。

### 4.3 出院小结
```
$ uv run pytest tests/test_discharge_note.py -q
18 passed
```
- 单元测试除最初的用例外，还加了独立审查和宽网阅读发现的 **20 多个真实漏网句式**（`REVIEW_HOLES` 19 条 + `test_care_arrangements_removed_but_home_meds_kept` 8 条）（都必须删），以及"出院时的状态描述""入院前病史""home dose 用药""PICC placement"必须保留的用例。

dev 病人全部出院小结（最终规则）：
```
26395 dev notes in 458s; spans 5444324, kept 4043723
RESIDUAL (must be 0): 0 {}
removals by scope/rule: section drop_section 1119843; sentence transitional_issues 149518, followup 37103,
  care_arrangement 23768, discharge_move 12458, place_snf 10056, place_home 7058, todo_item 2254, place+plan 2122,
  dispo_process 1100, discharge_self_care 620; clause place_snf 1486, followup 1192, place_home 939, care_arrangement 755,
  discharge_move 427, place+plan 88, dispo_process 48, discharge_self_care 31
kept destination words outside discharge-time sections: HPI 4608, PMH 187, MEDADM 113, PE 67, FH 40, SH 35, CC 25, PROC 9
wide-net hits by section: HPI 1979, HC 751, PR 162, PMH 104, PE 46, MEDADM 18, PROC 13, FH 8, CC 4, SH 2, COND 1 (total 3088)
sentences kept per section: HC 653817/845692 (77%), PR 1374098/1431220 (96%), COND 85628/85929 (100%),
  HPI 510343/512572 (100%), PMH 307965/309668 (99%)
```

### 4.4 文本探针
4,000 例（2,000 SNF + 2,000 非 SNF），按病人分组 5 折交叉验证，bootstrap 1,000 次：
```
$ uv run python research/leakage_probe.py      （最终规则）
raw            AUC 0.926  95% CI [0.917, 0.933]
redacted       AUC 0.840  95% CI [0.829, 0.851]
redacted_noPA  AUC 0.839  95% CI [0.828, 0.850]
top features (redacted):
 toward_snf:     fall, fracture, assistance, dementia, walker, with assistance, hip, confused, wheelchair, walker or,
                 cane, requires assistance, aid walker, to chair, rehab, or cane, ambulatory requires, ...
 toward_not_snf: ambulatory independent, independent, symptoms, ambulatory, status ambulatory, coherent level,
                 and coherent, coherent, status clear, clear and, rdw 12, pcp, he, transplant, asthma, cancer, ...
```
- 各版本规则下的处理后 AUC：0.844（初版）→ 0.843 → 0.840（最终）。
- 剩下的预测力主要来自功能状态和病情（跌倒、骨折、需要协助、助行器 / 轮椅、痴呆 / 意识混乱；对侧是独立行走、意识清楚），这正是 SNF 判定本来要看的信息。
- `redacted_noPA`（再删掉入院前段落里所有带去向词的句子）只差 0.001，说明保留入院前病史不造成泄漏。
- "pcp" 仍在非 SNF 一侧，来自 HPI 里的病史（出院时段落已全部删除 PCP 句）。

### 4.5 CaseBundle
```
$ uv run python -m snf_pa.adapters.mimic dev
100 bundles; evidence per case min/median/max = 51/167/308
$ uv run pytest tests/test_case_bundles.py -q
9 passed
```
- 证据（最终）：出院小结 15,050、影像 718、医嘱事实卡 172、处方事实卡 39。
- `test_case_bundles.py` 检查：
  - 与 dev 抽样一一对应、无 test 病例；
  - hash 一致；
  - 证据可得时间 ≤ T_pa；
  - **时间线所有时间点 ≤ T_pa（计划出院日期除外）**；
  - **前序住院在本次出院前 30 天内**；
  - ID 唯一；
  - 无禁止字段和诊断类标签；
  - 无被删段落、规则一致性残余为 0；
  - 已声明假设；
  - **完整重建，hash 逐例相同**。
- 事实卡独立复核：按 provenance 回查原表重新计数，202 / 202 一致。复核发现 `pharmacy_id` 不唯一，provenance 已加药名。这次复核是在审查修正前做的；修正后 POE 卡多出的 9 张来自 ED 等床期间的医嘱，没有重新复核。

### 4.6 全量快速测试
```
$ uv run pytest -q
109 passed, 1 skipped
```

## 5. 人工抽查（人工关卡）
- 页面：`D:\Repo\claims_agentic_system\data\derived\review\review.html`（不进 git），用你自己的浏览器打开；已按最终规则重新生成。
- 50 篇来自 dev 病人（25 去 SNF、25 不去，打乱，不显示去向）。每篇选"看不出 / 看得出：SNF / 看得出：回家"，看得出就写下哪句话。填完点"导出 CSV"，把文件发给我。
- 判泄漏的标准：文字说出了去向安排（床位、接收机构、随访、出院指导、家里的设备和服务）。凭病情推测的不算。
- 有看得出的，我补规则、重扫，按设计重新抽 50 篇。

## 6. 没做或没验的
- 人工抽查（等你）。
- 设计 3.4 的措辞修改（等你同意，3.1）。
- `tests/expected/appendix_a_poe.json` 已冻结（2026-11-08，确认框允许）。
- test 200 例不生成。
- 出院小结写于出院后，是设计接受的局限。
- 44 / 306 份 dev 影像报告没有 `IMPRESSION:` 标题，不产生证据（覆盖缺口，不是泄漏）。
- 第 ② 步的抽样标签（`src/snf_pa/needs.py`）对医嘱用的是 `ordertime >= admittime`，没有包括 ED 等床期间。只影响抽样（已冻结），不影响 bundle，不改。

## 7. 独立审查

一个全新的 agent 只看设计 v8、CLAUDE.md 和本步 diff，做了只读审查（复跑 pytest：103 passed / slow 5 passed）。

| # | 发现 | 是否成立 | 处理 |
|---|---|---|---|
| 1 | **dev bundle 里仍有去向句**："Mr ___ is discharged to rehab in stable condition"（PR）、"Pt will be discharge with home ___"、"discharged with order for home hospital bed"、"discharged to recover further at home" 等；`residual()` 用同一套规则，看不出 | 成立，严重 | 见下 |
| 2 | 前序住院窗口锚定在本次**入院**，法规是从前序出院到 SNF 入院 30 天（42 CFR 409.30(b)(1)）；dev 25667636 列了一个出院前 32 天的前序住院 | 成立 | 改为锚定本次**出院**，并且 ≤ T_pa；合成用例覆盖"入院前 27 天、出院前 32 天" |
| 3 | 时间线里有晚于 T_pa 的时间点（21310760 的 admittime、ed_outtime） | 成立 | bundle 里置空（计划出院日期例外）；加测试 |
| 4 | 事实卡丢掉了 ED 等床期间的医嘱（只从 admittime 起算） | 成立 | 从 ED 到达 / 住院医嘱 / 入院三者最早的时间起算；POE 卡 163 → 172 |
| — | 测试空心：残余检查、前序住院测试锁定了 bug、没有测 ED 等床和 T_pa 之后的时间点 | 成立 | 全部补上 |
| — | 设计 3.4 与代码不一致 | 已知 | 等你同意改设计（3.1） |

第 1 条的处理经过了几轮，每一轮都是"修 → 全量扫描 → 宽网抽读"：

| 轮次 | 发现 | 根因 / 修正 |
|---|---|---|
| a | 审查给出的 8 个句子 | PR 改为始终算出院时段落（Hui Li 原规则只在没有病程标题时才算；骨科模板把病程写在 PR）；新增 `discharge_move`（"discharged to / with / on""ready for discharge""home" 靠近 "discharge"） |
| b | 宽网读 dev 100 例全部 33 条：约 12 条是泄漏 | **主要根因是换行**：MIMIC 病历是硬换行的，"follow-up\nwith"、"discharged to\nrehab" 跨行，规则里的空格匹配不上。cfeng 的代码处理了这一点（"Spaces match any whitespace"），我移植时漏了。所有触发词改为空格匹配任意空白 |
| c | 剩 12 条，其中 3 条泄漏（appointment arranged、"would follow-up with"、"On discharge, she will…"） | 补规则 |
| d | 全量扫描残余变成 116 | 两个 bug：`therap\w*` 匹配到 "therapeutic"，把用药句送进了半句遮蔽；MIMIC 的 `___` 和我们的遮蔽符号一样，规则在两种形式下结果不同。修正：therapy 词收窄；规则同时检查两种形式；半句遮蔽后仍命中就整句删 |
| e | 全量宽网抽读 40 条：仍有"home O2 was arranged""followed in the ___ clinic""faxed to her PCP""placement discussed with CM, SW""hospital bed at home" | 改为结构性规则：出院时段落里提到 PCP / 诊所 / 门诊 / 安排 / 传真 / CM / SW / 家用设备与服务就删；TRANSITIONAL ISSUES 小标题之后全删；`[ ]` 待办行删 |
| f | 抽读 40 条剩 2 条（"sent home""appropriate for home d/c"） | 补上；剩下的都是用药史，长尾交给人工抽查 |

## 8. 评审后重做（2026-11-09）

第 ② 步按团队评审重做后（不含 REHAB、按住院划分和抽样，D-008），本步的产出按新的 dev 重做。规则和代码只多了两处修正（见下）。上面第 1–7 节是重做前的记录，保留不删。

```
$ uv run python -m snf_pa.adapters.mimic dev
100 bundles; evidence per case min/median/max = 39/184/538
证据：出院小结 16,674、影像 903、医嘱事实卡 173、处方事实卡 41；1 例退回入院时间（无住院医嘱）；15 例有 30 天内前序住院
$ uv run pytest tests/test_case_bundles.py -q
9 passed（含完整重建 hash 逐例一致）
$ （残余 + 宽网扫描，新的 dev 全部住院）
24778 dev notes in 424s; spans 5095111, kept 3786950
RESIDUAL (must be 0): 0 {}
wide-net hits by section: HPI 1882, HC 737, PR 174, PMH 106, PE 42, MEDADM 15, PROC 12, FH 6, CC 5, SH 3, COND 1 (total 2983)
sentences kept per section: HC 609789/788644 (77%), PR 1283126/1336992 (96%), COND 79624/79838 (100%),
  HPI 480425/482472 (100%), PMH 295709/297358 (99%)
$ uv run python research/leakage_probe.py
raw            AUC 0.964  95% CI [0.959, 0.969]
redacted       AUC 0.868  95% CI [0.857, 0.879]
redacted_noPA  AUC 0.866  95% CI [0.855, 0.877]
top features (redacted) toward_snf: assistance, fall, fracture, with assistance, rehab, wheelchair, to chair, dementia, confused, ...
                        toward_not_snf: ambulatory independent, independent, symptoms, ambulatory, status ambulatory, pcp, coherent, ...
$ uv run python research/review_page.py
wrote ...\data\derived\review\review.html (50 notes: 25 SNF)
$ uv run pytest -q
111 passed, 1 skipped
```

- **AUC 为什么比重做前高**：原文 0.926 → 0.964，处理后 0.840 → 0.868。非 SNF 组不再包含 REHAB 病人，而 REHAB 病人的病情和功能最像 SNF 病人，去掉后区分本身变容易了。去泄漏带来的降幅相当（0.096 vs 0.086），top features 仍是功能状态和病情。
- **宽网抽读**：
  - 第一轮读了 24 条，发现 2 条泄漏："d/c'ed home on IV ertapenem"（"d/c'ed" 的撇号写法没覆盖）、"plan for OT home evaluation"。已修，加了测试。
  - 还有 1 条弱信号（"inability to infuse antibiotic home, him living alone…"）留给人工抽查。
  - 修后再读 16 条，全是用药史。
- **人工抽查页已按新的 dev 重新生成**：之前生成的那份样本已作废，请用新的。

### 8.1 评审后重做的独立审查（2026-11-09）
一个新的 agent 只读审查了这次重做（复跑 `pytest -q` 111 passed、`-m slow` 5 passed），**没有严重问题**。已核对：
- REHAB 全部去掉；
- 没有代码再读 `subjects.csv`；
- 划分按 `hadm_id`、数字与报告一致；
- 样本只来自本 split，配额和缺额移动正确；
- 冻结清单一致；
- `--unfreeze` 拒绝清单本身和未冻结文件，并且经确认框；
- 设计 v9 与代码一致。

次要意见与处理：

| # | 意见 | 处理 |
|---|---|---|
| 1 | dev bundle 的前序住院里可能列出同一病人在 test 中的住院（100 例中 7 例，只含时间和午夜数） | 按住院划分的固有后果；设计 3.2 局限说明补了一句（D-008 范围内，已重新冻结） |
| 2 | 配额测试只和 meta 比对，配额本身没被固定 | 加 `test_quota_settings_pinned`：固定 SNF 8 / HHC 7 / HOME 5、test ×2、每场景 20 / 40 |
| 3 | 过时文字：测试 docstring、探针 population 标签、抽查页选项"SNF / 康复机构" | 已改；抽查页重新生成 |
| 4 | meta 的 `shortfall_moved_to` 只记最后一站 | 当前只有一次移动，不影响；改格式会改变已冻结的 meta，不改 |

```
$ uv run pytest -q
112 passed, 1 skipped
```
