# 第 ② 步报告：队列 + Parquet 子集

- 日期：2026-11-08
- 分支：`zhijie-20261108`（基于 `9e9a1ef`），目录 `D:\Repo\claims_agentic_system`
- 计划：`reports/step2_plan.md`。用户决定（2026-11-08）：年份规则 A（严格）；病人按 50 / 50 划分；分层抽样放在本步；Parquet 不建实验室 / chartevents 等表；设计文档两处更正；依赖 POE 的附录 A 计数留到第 ③ / ④ 步。
- 状态：2a–2f 全部完成并验证；划分文件、附录 A 期望值、设计文档 v8 已冻结；抽样文件待冻结（第 7 节）；独立审查见第 9 节。
- 期间的设计变化：设计文档升到 v8（可扩展结构、两维场景），见 `plan/decision_log.md` D-003 至 D-005。
- 队友分歧记录：`reports/teammate_diff_cohort.md`、`reports/teammate_diff_raw_data_access.md`（按 CLAUDE.md 新增的「分歧记录」规则）。

## 1. 完成标准对照

| 完成标准（设计 12 节附注 2） | 状态 | 证据 |
|---|---|---|
| 队列计数与附录 A 一致 | **8 个结构化计数全部一致**。附录 A 原来的"覆盖率按年份"一行复现不了，已按实测更正设计文档（你同意的改动）。依赖 POE 的 4 个数留到第 ③ / ④ 步 | 4.2 |
| 按 `subject_id` 生成 dev / test 划分文件 | 已生成 `data/splits/subjects.csv`，验证通过 | 4.4 |
| test 冻结 | **已冻结**（`subjects.csv`、`subjects.meta.json`） | 第 6 节 |
| （v8 新增）需求理由目录第一版 | `knowledge/needs.yaml` v1，12 条 | 第 7 节 |
| （v8 新增）dev 100 / test 200 抽样文件冻结 | 已生成并验证，**待冻结** | 第 7 节 |

## 2. 做了什么

| subtask | 文件 | 说明 |
|---|---|---|
| 2a guard 小修 | `.claude/hooks/guard.py`、`tests/test_hooks.py` | `git push … 2>&1` 不再把重定向当成 push 目标；先在 scratchpad 副本上测，再装回（装回后与测过的副本逐字节相同） |
| 2b 附录 A 测试 | `tests/expected/appendix_a.json`（受保护，待你冻结）、`tests/test_cohort_counts.py`（`slow`） | 用候选池模块里的同一套字段定义，算出附录 A 的 8 个数 |
| 2c 候选池 | `src/snf_pa/adapters/cohort.py` → `data/derived/cohort/pool.parquet`、`pool_counts.json` | 条件：Medicare、≥65、存活、有出院小结、严格年份 2011–2018、4 种去向。观察期、午夜数、从 SNF 入院只记录，不过滤 |
| 2d 划分 | `research/make_split.py` → `data/splits/subjects.csv`、`subjects.meta.json`（受保护）；`tests/test_split.py` | `sha256("snf-pa-split-v1:" + subject_id)` 前 8 位 / 16⁸ < 0.5 → dev。脚本拒绝覆盖已存在的划分 |
| 2f Parquet 子集 | `src/snf_pa/adapters/subset.py` → `data/derived/parquet/*.parquet` + `manifest.json` | 14 张表，过滤条件是候选池里的病人（保留这些病人的**全部**住院，供前序住院判断用）；不做 T_pa 截断 |
| 2e 草案 | `research/scenarios.py`、`reports/step2_scenarios_draft.md` | 只有场景定义和配额建议，**没有抽样** |
| 设计文档 | 3.2 两处、附录 A 一处 | 第 5 节 |
| CLAUDE.md | 「队友已经做过的工作」 | 新增「分歧记录」：只要和队友不一样就记录，写清背景、队友的选择、我们的选择、依据、影响、待讨论 |

## 3. 队友对照

队列和划分逻辑**不采用**两位队友的实现，原因逐条写在 `reports/teammate_diff_cohort.md`：
- 都排除观察期入院；
- 都把 ≥3 午夜当纳入条件；
- 主样本都没有 REHAB；
- 都不限年份；
- 都是先抽样再划分。

场景码表参考了队友的类别 SQL，来源写在 `research/scenarios.py` 和草案里。

## 4. 命令与原始输出

### 4.1 guard 小修
```
$ SNF_PA_GUARD_UNDER_TEST=<scratchpad>/guard_new.py uv run pytest tests/test_hooks.py -q
30 passed in 17.88s
$ diff 装回的 guard.py  scratchpad 副本   → same
$ uv run pytest tests/test_hooks.py -q
30 passed in 17.86s
```

### 4.2 附录 A 计数
```
$ uv run pytest tests/test_cohort_counts.py -q -m slow
..   2 passed in 15.69s
```
`tests/expected/appendix_a.json`：

| 键 | 值 |
|---|---|
| medicare_admissions | 244576 |
| medicare_snf | 42312 |
| snf_with_note | 34298 |
| snf_note_age65_alive | 30613 |
| snf_observation_admit | 9696 |
| snf_naive_midnights_ge3 | 38828 |
| snf_naive_midnights_lt3 | 3484 |
| snf_from_snf | 2693 |

`snf_from_snf` 取自 `8560e4b` 版第 1 节，v7 附录 A 里没有这一项。

灵敏度检查（只在内存里改，不动文件）：把午夜数从"日历日差"改成"按 24 小时取整"，
```
mutated ge3 = 36318 expected 38828 -> test would FAIL (good)
```

### 4.3 候选池
```
$ uv run python -m snf_pa.adapters.cohort
year_rule: strict 2011-2018
HOME HEALTH CARE          admissions 17308  patients 10937  observation_type 2779  lt3_naive 3761  from_snf 59
HOME                      admissions 16335  patients 11053  observation_type 2860  lt3_naive 7830  from_snf 13
SKILLED NURSING FACILITY  admissions 15795  patients 10483  observation_type 2287  lt3_naive 1182  from_snf 756
REHAB                     admissions  2657  patients  2297  observation_type  304  lt3_naive  168  from_snf 24
total_admissions 52095   total_patients 26661
```
- 与计划阶段探查表的"A 严格"那一行完全一致。
- 两次构建的内容 hash 相同：`1288d2e8d6e0214ec555126ea31bddc2`。
- 不变量（`test_pool_invariants`）通过：
  - 没有 <65、没有院内死亡、全部有出院小结、全部是 Medicare、年份全在窗口内、只有 4 种去向、`hadm_id` 不重复；
  - 观察期、不足 3 午夜、从 SNF 入院的病例都保留在池里。

### 4.4 划分
```
$ uv run python research/make_split.py
wrote ...\data\splits\subjects.csv: 26661 subjects, dev 13544, test 13117
$ uv run python research/make_split.py      (再跑一次)
...subjects.csv already exists; the split is protected and is never regenerated.   exit=1
$ uv run pytest tests/test_split.py -q
4 passed   （每人一行；规则重算与文件一致；dev 比例 50.8%；病人集合 = 候选池病人集合）
```
按去向（住院数 / 病人数）：

| 去向 | dev | test |
|---|---|---|
| SNF | 7,980 / 5,298 | 7,815 / 5,185 |
| HHC | 8,716 / 5,567 | 8,592 / 5,370 |
| HOME | 8,336 / 5,642 | 7,999 / 5,411 |
| REHAB | 1,363 / 1,173 | 1,294 / 1,124 |

边界病例（住院数）：

| | 观察期类型 | 不足 3 午夜 | 从 SNF 入院 |
|---|---|---|---|
| dev | 4,124 | 6,615 | 425 |
| test | 4,106 | 6,326 | 427 |

只看了计数，没有看任何结果。

### 4.5 Parquet 子集
```
$ uv run python -m snf_pa.adapters.subset
admissions      rows=   108,497 cols=16      3.3 MB    2.6s
patients        rows=    26,661 cols= 6      0.1 MB    0.5s
transfers       rows=   433,696 cols= 7      8.0 MB    5.2s
services        rows=   120,086 cols= 5      1.4 MB    1.0s
diagnoses_icd   rows= 1,602,643 cols= 5      4.4 MB    7.7s
procedures_icd  rows=   167,626 cols= 6      1.0 MB    1.6s
drgcodes        rows=   167,412 cols= 7      1.1 MB    1.1s
poe             rows=11,520,126 cols=12     99.0 MB   90.7s
poe_detail      rows= 1,457,487 cols= 5      7.3 MB    8.2s
prescriptions   rows= 4,531,915 cols=21    109.2 MB   52.5s
icustays        rows=    21,126 cols= 8      0.6 MB    0.4s
edstays         rows=    72,797 cols= 9      1.6 MB    1.2s
discharge       rows=    89,939 cols= 8    277.8 MB   19.8s
radiology       rows=   511,238 cols= 8    154.9 MB   11.1s
$ du -sh data/derived/parquet   → 639M
```
独立核对（scratchpad 脚本，按全部字段为文本重新读原始表，不经过 `subset.py`）：
```
spot-check subjects: [10000764, 14998385, 19999287]   （候选池最小 / 中位 / 最大 subject_id）
14 张表 raw 行数 == parquet 行数，outside_pool=0，总行数 == manifest   → 全部 OK
pool admissions missing from admissions.parquet: 0; pool admissions without a discharge note in subset: 0
ALL OK
全量独立计数：admissions raw 108497 = parquet 108497；poe_detail raw 1457487 = parquet 1457487
```

### 4.6 全量 pytest（含 slow）
```
$ uv run pytest -q -rs
FAILED tests/test_protected_files.py::test_frozen_file_unchanged[plan/snf_pa_consensus_work_plan_1025.md]
1 failed, 43 passed, 1 skipped in 34.30s
```
这个失败是预期的：设计文档按你同意的内容改了，hash 变了。你重新冻结后就会通过。我没有改回文档，也没有动 `data/PROTECTED.sha256`。

## 5. 设计文档改动（你同意的第 5 项）
- 3.2 纳入条件：写明严格年份规则的计算方法。
- 3.2：SNF "约 3 万例" → "15,795 例住院 / 10,483 人；不限年份时为 30,613 例"。
- 附录 A 出院小结覆盖：换成按 `anchor_year_group` 和按估算年份两种口径的实测值，并注明原数字无法复现、2026-11-08 更正。

## 6. 冻结（2026-11-08 已完成）

冻结的方式改了（用户决定）：由 Claude 运行 `tools/freeze.py`，guard 把每次运行都送到用户的权限确认框，用户点"允许"才执行。冻结仍然必须经过用户；Claude 不能悄悄重新冻结。guard 改动先在 scratchpad 副本上测过（30 passed），装回后与副本逐字节相同。

```
$ uv run python tools/freeze.py data/splits/subjects.csv data/splits/subjects.meta.json tests/expected/appendix_a.json plan/snf_pa_consensus_work_plan_1025.md
（用户在确认框中允许）
added  data/splits/subjects.csv  68a002484615
added  data/splits/subjects.meta.json  f4ead4c3436a
added  tests/expected/appendix_a.json  3f61f6083aff
updated  plan/snf_pa_consensus_work_plan_1025.md  4c9477c8bbb4
$ uv run pytest -q -rs
SKIPPED [1] tests\test_sample.py:8: sample not built yet (design step 2)
47 passed, 1 skipped in 34.29s
```

设计文档冻结的是 v8（可扩展结构写入正文后的版本，见 `plan/decision_log.md` D-004）。

## 6a. 当时等用户的事（已处理，保留记录）

1. **冻结 4 个文件**（在你自己的终端运行，我被禁止运行这个工具）：
   ```bash
   uv run python tools/freeze.py data/splits/subjects.csv data/splits/subjects.meta.json tests/expected/appendix_a.json plan/snf_pa_consensus_work_plan_1025.md
   ```
   - 前三个是新冻结。
   - 设计文档是重新冻结：先看一下 `git diff plan/` 是否符合你同意的内容。
2. **确认 2e 场景定义和配额**：`reports/step2_scenarios_draft.md`，尤其是脓毒症、肺炎归哪一类，以及外科类（`other`，2.2 万例）不抽样。
3. 确认后，我抽 dev 100 / test 200、写入 `data/splits/`，再请你冻结一次；然后做独立审查、补完本报告并 commit。

## 7. 需求理由目录与分层抽样（2e）

### 7.1 做了什么（这些细则由 Claude 决定，用户授权自行决定）

| 文件 | 内容 |
|---|---|
| `knowledge/needs.yaml` v2（hash `288cc9628a16`；v2 = 审查后修正，见第 9 节） | 12 种需求理由。<br>**服务类 6 种**：静脉抗菌药 `iv_therapy`、营养支持 `nutrition_support`、伤口护理 `wound_care`、PT/OT `rehab_therapy`、言语吞咽 `speech_therapy`、氧疗或 BiPAP `respiratory`。服务类每条都对应 42 CFR 409.33 的具体段落（已对照 `policy_docs/42cfr409_subpartD.xml` 核对段落编号）。<br>**状况类 6 种**：髋骨折、急性卒中、压疮、痴呆、帕金森、体能下降。 |
| `src/snf_pa/registry.py` | 读取并校验目录：ID 唯一；诊断类规则不得标成"T_pa 前可得"（ICD 码出院后才编）；服务类必须引用条款 |
| `src/snf_pa/needs.py` | 按目录给住院打标签。三种规则：`poe_order`（医嘱，只取 New、入院到 T_pa 之间）、`iv_drug`（处方，在 T_pa 前 48 小时内仍在用）、`diagnosis`（任意位置）。T_pa 暂用 `max(出院 − 24h, 入院)`，第 ③ 步换成住院医嘱起点 |
| `research/scenarios.py` | 两维场景（设计 10.1），按优先级取一个：<br>1. 骨科术后：髋骨折标签或髋 / 膝置换手术；<br>2. 卒中：急性卒中标签；<br>3. 伤口 / 静脉用药：伤口护理、静脉抗菌药或压疮标签；<br>4. 心衰：只看第一诊断；<br>5. 内科病后体能下降：本次住院从未在外科服务（按 `services` 表）；<br>其他：不抽。 |
| `research/sample.py` | 每个场景：dev SNF 8 / HHC 5 / HOME 4 / REHAB 3，test 加倍。<br>每格约 25% 名额留给边界病例。<br>每人最多一次住院。<br>最稀缺的格子先抽。<br>名额不够时依次挪到同场景的 HHC、SNF。<br>hash 顺序：`sha256("snf-pa-sample-v1:" + hadm_id)`。<br>拒绝覆盖已有文件。 |
| `data/splits/dev_cases.csv`、`test_cases.csv`、`sample.meta.json` | 受保护，待冻结 |

几个具体决定和理由：
- **静脉抗菌药按"T_pa 前 48 小时内仍在用"判定**，不按"住院期间用过"判定。出院前还在用的静脉药，才可能延续到 SNF。这个规则也会包含术后预防用药；骨科场景优先级更高，不受影响。
- **心衰只认第一诊断**：任意位置出现心衰的占候选池 29%。
- **伤口护理标签只是提示**：42 CFR 409.33(d)(4) 把非感染伤口的换药列为非 skilled 照护，是否构成 skilled 需求由 reviewer 判。
- **诊断类标签只用于抽样和报告**，不会成为审核证据（硬规则 2）。

### 7.2 结果

候选池按场景 × 去向（住院数）：

| 场景 | SNF | HHC | HOME | REHAB |
|---|---|---|---|---|
| ortho_postop | 1,301 | 397 | 13 | 213 |
| stroke | 538 | 342 | 329 | 587 |
| wound_iv | 7,912 | 7,545 | 4,831 | 1,135 |
| heart_failure | 487 | 1,202 | 554 | 38 |
| medical_decond | 4,298 | 6,322 | 8,413 | 357 |
| other（不抽） | 1,259 | 1,500 | 2,195 | 327 |

标签出现率（占该去向住院的 %）：

| 标签 | SNF | HHC | HOME | REHAB |
|---|---|---|---|---|
| rehab_therapy | 84.8 | 65.6 | 23.8 | 94.9 |
| iv_therapy | 44.1 | 35.9 | 23.7 | 38.9 |
| respiratory | 40.7 | 32.6 | 18.4 | 49.7 |
| wound_care | 29.5 | 20.4 | 8.6 | 37.6 |
| dementia | 19.0 | 7.3 | 2.8 | 6.9 |
| speech_therapy | 17.5 | 6.2 | 2.0 | 31.8 |
| nutrition_support | 7.4 | 3.3 | 0.7 | 17.2 |
| pressure_ulcer | 5.4 | 1.7 | 0.2 | 3.8 |
| hip_fracture | 4.8 | 0.3 | 0.0 | 5.5 |
| acute_stroke | 3.4 | 2.0 | 2.0 | 22.4 |
| parkinson | 2.9 | 1.7 | 0.9 | 4.3 |
| debility | 0.8 | 0.6 | 0.3 | 1.0 |

PT/OT 会诊 SNF 84.8% vs HOME 23.8%，与附录 A 的 PT 会诊出现率（89 / 32%）方向一致。

最终版本是按审查意见修正后重抽的（第 9 节）：
```
$ rm data/splits/dev_cases.csv data/splits/test_cases.csv data/splits/sample.meta.json   （未冻结；用户在确认框中允许）
$ cd research && uv run python sample.py
dev: 100 cases -> ...\data\splits\dev_cases.csv
test: 200 cases -> ...\data\splits\test_cases.csv
needs catalog: {'version': 2, 'hash': '288cc9628a16'}
dev  cells off-quota: []
test cells off-quota: []
$ uv run python sample.py        （再跑一次）
sample files already exist; they are protected and are never regenerated.   exit=1
$ uv run pytest tests/test_sample_cases.py tests/test_needs.py tests/test_split.py -q
11 passed
```

- 20 个格子全部按配额填满，没有任何格子缺额。
- 最紧的格子：骨科术后 × HOME，dev 只有 5 人可选、要 4 个；test 9 人可选、要 8 个。
- 边界病例：dev 38 / 100，test 71 / 200。
- 髋骨折：dev 11，test 19。
- `test_sample_cases.py` 检查了：
  - 样本量；
  - dev 只来自 dev 病人、test 只来自 test 病人；
  - 病人不重复；
  - 每格数量与 meta 一致；
  - 独立重抽结果与文件逐例相同。

样本中各标签的病例数：

| 标签 | dev | test |
|---|---|---|
| rehab_therapy | 69 | 147 |
| respiratory | 42 | 72 |
| iv_therapy | 32 | 67 |
| wound_care | 25 | 46 |
| acute_stroke | 20 | 40 |
| speech_therapy | 19 | 38 |
| hip_fracture | 11 | 19 |
| dementia | 9 | 34 |
| nutrition_support | 4 | 15 |
| parkinson | 3 | 10 |
| pressure_ulcer | 4 | 2 |
| debility | 1 | 1 |

### 7.3 一个没按原话做的地方
之前在对话里说过"抽完检查每个标签的病例数，太少就补抽"。实际**没有补抽**：
- 补抽会让 test 超过设计规定的 200 例，也会改变按场景分层的比例。
- 压疮、体能下降这类标签在候选池里本来就少（压疮占 SNF 的 5.4%，体能下降不到 1%）。
- 后果：这几个标签在样本里太少，**不能单独报告指标**；报告时会写明 n。
- 如果以后需要按这些标签评估，可以另抽一个"标签补充集"作为新的受保护文件，不动已冻结的 300 例。要不要做由用户决定。

## 8. 冻结抽样文件
待冻结：`data/splits/dev_cases.csv`、`data/splits/test_cases.csv`、`data/splits/sample.meta.json`（通过权限确认框，由用户允许）。

## 9. 独立审查

按 CLAUDE.md，一个全新的 agent 只看设计文档 v8、CLAUDE.md 和本步 diff，做了只读审查：
- 它复跑了 `pytest -q`（54 passed, 1 skipped）和 `pytest -m slow`；
- 它核对了年份规则的字符串解析、候选池计数、10 组医嘱类型都真实存在、时间窗口只用 T_pa 前的信息、抽样的确定性和病人唯一性，**结论是这些都没有问题**。

提出的问题和处理：

| # | 问题 | 是否成立 | 处理 |
|---|---|---|---|
| 1 | "手术住院"在 ICD-9 和 ICD-10 用两套规则，同一种床旁操作（PCI、胃镜、透析、中心静脉置管、腹腔穿刺）在两个年代分到不同类别。大部分做过操作的内科病人进不了"内科病后体能下降"，且年代不均（ICD-9 85% 被排除，ICD-10 59%） | 成立，影响抽样代表性 | 改按 `services` 表（住院期间是否在外科服务）。两个年代被排除的比例变为 28% / 27%；medical_decond 候选从 14,387 增到 19,390 |
| 2 | 髋骨折标签收了"后续就诊 / 后遗症"编码（ICD-10 第 7 位 D/G/K/S），有 22 例只有这类编码却进了骨科术后 | 成立，影响小 | 只收第 7 位 A/B/C（needs v2） |
| 3 | 设计 3.6 写 `tube_line`，目录里是 `nutrition_support` | 成立（我自己的不一致） | 设计 3.6 改为 `nutrition_support`，注明 PICC 第 ③ 步再加（D-006，设计文档已重新冻结） |
| 4 | 部分测试测不出错：年份窗口用同一表达式自查；没有固定候选池规模；时间窗口和下界没有边界用例 | 成立 | 加独立的年份重算、`tests/expected/pool_counts.json`（受保护，已冻结）、窗口边界 / 入院前医嘱 / 第 7 位编码 / PB 途径用例 |
| 5 | 抽样文件还没冻结 | 与报告一致 | 第 8 节冻结 |
| 6 | 抽样文件含出院去向、场景、诊断类标签，第 ③ 步 adapter 不得把这些列放进 `CaseBundle` | 成立（给后续的约束） | 写进 D-006 和第 10 节 |
| 7 | 静脉途径漏了 `PB` | 成立，影响可忽略 | 补上（needs v2） |

修正后：抽样文件尚未冻结，在用户确认后删除重抽（第 7.2 节）。全量 pytest（含 slow）58 passed, 1 skipped。

guard 同时做了一处调整（用户此前的方向："不需要我决定的事别让我手动做"）：
- **已冻结的文件**：仍然一律拒绝修改；
- **受保护但还没冻结的文件**：改为弹窗由用户允许。

先在 scratchpad 副本上测过（31 passed），装回后逐字节相同。

## 10. 没做或没验的
- **给第 ③ 步的硬约束**：`dev_cases.csv` / `test_cases.csv` 里的 `discharge_location`、`scenario`、`needs`、`hip_fracture` 是出院后或标签信息，adapter 只能用它们选病例，不能放进 `CaseBundle`。
- 附录 A 依赖 POE 的 4 个数（78%、14,384、37,337、940）未核对，按你的决定留到第 ③ / ④ 步。
- 本步的独立审查还没做（等 2e 完成后连同全部 diff 一起审）。
- 原始数据目录在系统层面仍然可写（L0 ACL 未设）。
- `tests/test_sample.py` 的去留（旧抽样方案的测试）还没定，见 `reports/teammate_diff_raw_data_access.md` 第 4 条。
