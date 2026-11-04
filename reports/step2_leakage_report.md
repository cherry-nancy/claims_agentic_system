# Step 2 病例预处理与去泄漏：结果报告

只含汇总数字，不含任何病历文本或病例级数据。
- 原始 JSON：`data/sample/step2_build_report.json`、`leakage_report.json`、`llm_guess_report_*.json`，均为本地文件，不入库。
- 代码：`src/snf_pa/data/{sections,redact,build_packets,leakage,leakage_pool,llm_guess,review_html}.py`。
- 测试：`tests/test_redact.py`。

## 1. 数据与产出

- **样本**：300 份出院小结，150 例去 SNF、150 例回家；每个诊断类别内各占 50%。
- **病例池（held-out 检查用）**：2655 份，其中 1483 例去 SNF。
  - 排除了样本中的病人。
  - 每人只取一次住院。
  - 每个（类别 × 去向）组合最多取 300 例。
- **span 数量**：

| | 句子 span 数 |
|---|---|
| 原始（all） | 63,040 |
| strict（主实验） | 48,742 |
| realistic（消融） | 54,304 |

- **span ID** 格式为 `DS:{节}:s{序号}`（D9）。同一个 ID 在两个 packet 里指的是同一句话。

## 2. 去泄漏规则（D7/D8）

| 处理 | strict | realistic |
|---|---|---|
| 整节删除：Discharge Disposition、Facility、Discharge Diagnosis、Discharge Instructions、Followup | 删 | 删 |
| Discharge Medications | 删 | 保留，但去掉 RX / Disp / Refills 行 |
| 出院时写的节（Hospital Course、Discharge Condition；没有 Hospital Course 时也包括 Pertinent Results）：出现去向词的句子 | 整句删除 | 整句删除 |
| 其余节（HPI、Social History 等）：出现去向词，**并且**谈的是这次出院计划 | 整句删除 | 整句删除 |
| PT/OT 的建议句 | 只遮住含去向的分句，功能描述保留 | 原样保留 |

- **整句删除的句子直接从 packet 中去掉，不留标记。** 早期版本留了 `[REDACTED-DISPO]` 标记，结果 SNF 病历里的标记更多，标记本身就泄露了结局。
- **只有临床含义的词不算去向词**：如 "PICC placement"、"subacute infarct"。
- **入院前的居住地保留**：如 HPI 里写 "lives in a nursing home"。这是做 PA 审核时可以合法知道的信息，属于 C6 证据。

strict packet 的删除计数（按真实去向分）：

| 规则 | 回家 | SNF |
|---|---|---|
| 整句删除：SNF/康复类去向词 | 40 | 150 |
| 整句删除：回家类去向词 | 62 | 4 |
| 整句删除：其他出院安排语句 | 1 | 4 |
| PT/OT 句只遮分句 | 27 | 14 |
| 含遮挡标记的病历占比 | 12.7% | 7.3% |

## 3. 泄漏检查 1：TF-IDF + 逻辑回归

- **模型**：词的 1–2 元组 TF-IDF，加逻辑回归，用来预测病人是否去 SNF。
- **两种评估方式**：
  - 在样本内做 5 折 × 5 次重复交叉验证（CV）；
  - 在病例池上训练，再预测 300 例样本（held-out），bootstrap 1000 次求 95% 置信区间（CI）。

整份病历的 AUC：

| Packet | CV AUC (sd) | held-out AUC [95% CI] |
|---|---|---|
| 原始 | 0.689 (0.070) | 0.793 [0.743–0.841] |
| **strict** | **0.537 (0.078)** | **0.652 [0.596–0.710]** |
| realistic | 0.615 (0.072) | 0.707 [0.650–0.760] |

AUC 不会降到 0.5，这在意料之中：去 SNF 的病人本来就病得更重、功能更差。所以判断去泄漏是否成功，要看**剩下的信号是不是临床信息**。

**被删掉的节单独预测的 held-out AUC（原始文本）：**

| 节 | AUC |
|---|---|
| Discharge Disposition | 0.952 |
| Discharge Medications | 0.850 |
| Discharge Instructions | 0.606 |
| Discharge Diagnosis | 0.571 |
| Facility | 0.544 |

- Disposition 和 Discharge Medications 都超过计划里定的 0.70 阈值，证明删掉它们是对的。
- Discharge Medications 为什么能预测：回家的病人有处方行（RX/Disp/Refills），在 SNF 病历里则少得多。

**strict packet 保留的节，held-out AUC 都 ≤ 0.69：**

| 节 | AUC |
|---|---|
| Discharge Condition | 0.685 |
| Hospital Course | 0.648 |
| MEDADM、PE、HPI、PR | 0.61–0.62 |
| 其余 | ≤ 0.58 |

- Discharge Condition 的信号来自 "Activity Status"，比如 "ambulatory independent" 与 "wheelchair / with assistance"。这是功能状态，属于合法的 C4/C5 证据，保留。

**strict packet 预测力最强的特征（病例池模型）：**
- **偏向 SNF**：fracture、fall、dementia、hip fracture、delirium、wheelchair、confused、with assistance、femur、to chair。
- **偏向回家**：ambulatory independent、independent、pcp、outpatient、dyspnea、cough。
- 这些都是临床和功能信息。原始病历里排在前面的 "extended care"、"to rehab"、"home with"、"disp/refills" 已经全部消失。

## 4. 泄漏检查 2：残留关键词与节的出现率

- **strict packet 里仍然出现 SNF 类去向词的病历，几乎都在 HPI**：去 SNF 的病历有 40 份，回家的有 5 份。
  - 这些都是入院前的居住地或既往康复史，按规则有意保留（见第 6 节的待决事项）。
- **其他节只零星出现**：每节每组 ≤ 2 份。
- **节的出现率本身也会泄漏**：Facility 节在 SNF 病历中 100% 出现，在回家病历中只有 72%。所以 Facility 整节删除。删除之后，保留下来的各节在两组间的出现率差别都 ≤ 5 个百分点。

## 5. 泄漏检查 3：本地 LLM 猜结局（无结论）

做法：只给模型看 packet，让它猜病人去了 SNF 还是回家。原始病历作为阳性对照，因为里面写着 Discharge Disposition，合格的模型应当接近全对。

| 模型 | Packet | n | 准确率 | AUC | 平均每例秒数 |
|---|---|---|---|---|---|
| medgemma:4b | 原始（阳性对照） | 20 | 0.50 | 0.26 | 83 |
| medgemma:4b | strict | 60 | 0.50 | 0.44 | 70 |
| gemma4（关闭 thinking） | 原始（阳性对照） | 10 | 0.60 | 0.52 | 257 |

- **两个模型都没通过阳性对照。**
  - medgemma:4b 把 80 例全部猜成了 HOME。
  - gemma4 在两句话的合成病历上答得对，但在几千词的真实病历里找不到 Disposition 那一行。
- **结论**：这台笔记本上的本地模型不能做这项检查。strict 上的 0.50 **不能**当作"没有泄漏"的证据。
- **以后**：接入 Bedrock（Claude / DeepSeek）后补做这项检查，用环境变量 `SNF_GUESS_MODEL` 切换模型。仍然先跑阳性对照。

## 6. 结论与待决事项

**结论：**
- strict packet 已去掉所有明确的出院去向信息。
- 剩下的预测信号（held-out AUC 0.65）来自骨折、跌倒、痴呆、行动依赖等临床和功能信息，这正是 SNF 准入标准 C3–C5 要评估的内容。

**待决事项：**
1. **HPI 中的入院前居住地**（SNF 组 40 份 vs 回家组 5 份）：目前保留。可以另做一组"连这些也遮住"的敏感性分析。
2. **Social History 节大多只有 `___`**（中位长度 3 个字符）：C6（照护者与居家条件）的证据主要只能从 HPI 找，预计 C6 会经常判为 PEND（证据不足、待补充）。
3. **人工复核**：50 例 dev 病例的复核页面在 `data/sample/review/index.html`（本地，不入库）。
4. **LLM 猜结局检查**：等接入更大的模型后补做（见第 5 节）。
