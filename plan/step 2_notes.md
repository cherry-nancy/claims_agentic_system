### what I did after pushing previous version of criterion_cards.YAML with the help of Claude code Sonnet model.
- changed to Opus 5.5 medium model and had it look at the criterion_cards.YAML file, it suggested some changes and I adopted them and pushed the result to criterion_cards, so it is up-to-date now.
- execute step 2: deleakage, 

分步做法
2.1 切 section（src/snf_pa/data/sections.py）
按 MIMIC 出院小结的固定标题切段，例如 Chief Complaint、History of Present Illness、Social History、Brief Hospital Course、Discharge Disposition、Facility、Discharge Condition、Discharge Instructions、Followup Instructions。每段保留在原文中的字符位置。
先只出一份统计：每个标题在 300 份里出现了几次、有多少份切不出来。不打印任何病历内容。根据统计补齐标题的各种写法。
完成标准： 每份至少切出 Hospital Course 和 Discharge Condition，切不出的列清单给你在 IDE 里看。
2.2 按 D7 决定段落去留
保留： Chief Complaint、HPI、既往史（PMH）、Social History、体格检查（PE）、Pertinent Results、Hospital Course、Discharge Condition（Activity Status 和 Mental Status 标为“出院时功能状态代理”）、Medications on Admission。
整段删除： Discharge Disposition、Facility、Discharge Instructions、Followup Instructions、Discharge Diagnosis、Discharge Medications。
2.3 句子级遮蔽（redact.py）
保留的段落里还会混着去向信息，最常见的是 Hospital Course 末尾的 “Transitional issues” 或 “Dispo” 小节。处理方法：

先切句，再按正则把命中的句子换成 [REDACTED-DISPO]。
SNF 一侧： rehab、extended care、SNF、nursing facility、___ facility、placement、screened、accepted at、bed offer、“PT recommends rehab”等。
回家一侧（最容易漏）： home with services、VNA、home PT、home health、discharged home、home with family。不遮蔽这些，模型看到 “VNA” 就知道是负例，同样是泄漏。
PT/OT 句子只遮蔽推荐去向的那半句，同一句里的功能描述保留（D7）。例如“需要一人协助转移，推荐去 rehab”，保留前半句。
每次遮蔽写一条日志：note_id、span、段落、命中的规则名。只写本地，汇总时只看计数。
同时生成两套 packet（D8）：
strict：主实验用；
realistic：加回 PT/OT 推荐句和去掉药名后的出院用药，做消融对比用。
2.4 切句、编 span ID（D9）
格式如 DS:HC:s14（出院小结 / Hospital Course / 第 14 句），并记录每句在原文中的字符位置。
遮蔽后的句子保留 ID，只换内容，这样两套 packet 的 ID 一致。
___ 是去标识占位符，原样保留。
2.5 泄漏检测（三种都做）
关键词残留： 遮蔽后，按去向统计正则残留命中数。目标是 0。
TF-IDF 加逻辑回归： 用病历文本预测出院去向，分别算遮蔽前和遮蔽后、整份和逐段的 AUC，并列出权重最高的词。
判断标准不是 AUC 降到 0.5。病得重的人本来就更常去 SNF，这是合法的临床信号。要看的是遮蔽后排前列的词是否都是临床词（fracture、assist、wound），而不是去向词（rehab、VNA）。
只有 300 份时 AUC 波动大（±0.05 左右）。建议额外用候选池里不在样本中的约 3000 份同类病历来训练检测器。数据只在本地，只看汇总数字。
按共识计划：如果 Discharge Medications 单段 AUC 大于 0.70，就确认删除该段。
让本地 LLM 猜去向： 用 Ollama 本地模型，不出本机。300 例全跑太慢（14B 每例约 1–2 分钟），建议先抽 dev 里的 60 例。命中率明显高于只看诊断的基线，就说明还有泄漏。
另外，计划要求人工抽查 50 篇。这个由你来看：

我生成一个本地 HTML 对照页，高亮被删掉和被遮蔽的部分，放在 gitignored 的 data/ 下，你在浏览器里看。
我不读病历原文。
抽查只用 dev 集。test 集冻结，只看汇总计数。
2.6 输出与测试
输出（本地，gitignored）：
data/sample/packets_strict.parquet
data/sample/packets_realistic.parquet
data/sample/spans.parquet
data/sample/redaction_log.parquet
一份 leakage_report.json，只含汇总数字，可以入库。
测试： 用我编的假病历写单元测试，覆盖切段、遮蔽、span ID、两套 packet 的 ID 一致。测试不读 MIMIC。
入库： 只提交代码、测试和汇总报告。
暂不做，留到后面
结构化 fact cards（IV 抗生素天数、PICC、PT 会诊等）：需要先算出 PA 决策时点 T_pa（D6），而 T_pa 要用 POE 医嘱时间，这属于共识计划的 Step 3–4（Parquet 抽取和时间线引擎）。建议第二步只处理病历文本，fact cards 和工具层一起做。
正反例：Step 6 调 prompt 时再写。

两份计划冲突的地方（按共识计划处理）
问题	总计划	共识计划（采用）
DRG	当结构化特征	禁用：DRG 是出院后才编码的，本身就是泄漏
出院用药	保留 Medications	删除 Discharge Medications，改用 T_pa 前的处方数据
结构化数据截止	dischtime 前	T_pa = 出院前 24 小时（D6）

第二步的代码都写完了，也在 300 份病历上跑过。泄漏检测的三种做完了两种，第三种（让本地 LLM 猜去向）正在后台跑，约 2 小时。代码还没 commit。

新增代码（都在 src/snf_pa/data/ 下）

sections.py：按 17 个顶层标题切段。
redact.py：
合并被硬换行切断的续行，再切句、编 span ID；
删掉 6 段；
逐句遮蔽：Hospital Course、Discharge Condition 和用宽松规则；HPI、Social History 等入院前的段落只遮明确讲出院计划的句子；
PT/OT 句子只遮推荐去向的半句；
同时生成严格版和现实版两套 packet。
build_packets.py：主入口。
leakage.py、leakage_pool.py：关键词残留、TF-IDF 检测器、样本外病历池。
llm_guess.py：本地 LLM 猜去向。
review_html.py：生成人工抽查页面。
tests/test_redact.py：13 个测试，只用我编的假病历。全部 19 个测试通过，新代码 ruff 检查无问题。
结果（检测器在 2655 份样本外病历上训练，在 300 例上测试）

原文	严格版	现实版
预测去 SNF 的 AUC	0.79	0.65（95% CI 0.60–0.71）	0.71
被删的两段泄漏很强：Discharge Disposition 0.95，出院用药 0.85。
严格版剩下的信号主要是临床和功能信息（骨折、跌倒、痴呆、谵妄、轮椅、需要协助对比可独立行走），这是 C4–C6 本来就该依据的证据，不是泄漏。
调试中修掉的 4 个问题

[REDACTED-DISPO] 标记本身在 SNF 病例里更多。现在整句遮蔽的句子直接移除，不留标记。
原来按行切句，可病历大量句子被硬换行切断，遮掉前半句后剩下一个孤零零的 “condition.”，反而成了“回家”的标志。现在先合并续行再切句。
PICC placement、subacute infarct（亚急性梗死）被误当成去向词，现在不再遮蔽。
31 份病历没有 Hospital Course 标题，病程内容落在 Pertinent Results 里，现在这种情况下该段改用宽松规则。
需要你决定或注意的

HPI 里的入院前居住地： 写“从养老院、rehab 入院”的病历，SNF 组 40 份，回家组 5 份，预测力很强。我按“PA 审核时就知道的合法信息”保留了。如果你希望更保守，可以把它也遮掉，单独做一组对比。
Social History 基本被 MIMIC 去标识成了 ___： 所以 C6 需要的居住和照护者信息只能从 HPI 找，C6 挂起的比例会很高。
人工抽查： 用浏览器打开 D:\agenticAI\alex_project\snf\data\sample\review\index.html。一共 50 例 dev 病例，灰色是删掉的段落，红色是移除的句子，橙色是遮了半句（鼠标悬停能看到保留下来的文字）。请看两点：没高亮的文字里还有没有去向线索；有没有临床证据被误删。
模型改了： 本机跑 qwen3:14b 一例要 5 分钟以上，LLM 猜去向的测试改用 medgemma:4b。测试结束后我会把结果告诉你，再把只含汇总数字的报告整理好，等你说了再 commit。

测试跑完了，但这次结果不能用。medgemma:4b 这个模型本身没完成任务，所以得不出"去泄漏有没有效"的结论。

packet	例数	失败	准确率	AUC	每例秒数
strict（去泄漏后）	60	0	0.50	0.44	70
raw（原始病历，阳性对照）	20	0	0.50	0.26	83
为什么不能用：

阳性对照没过。 raw 病历里还留着 "Discharge Disposition" 那一节，结局几乎是明写的，正常模型在这里应该接近 100%。实际只有 0.50。
模型 80 例全猜了 HOME。 两个 packet、两种真实结局都是这样，0.50 只是因为样本一半是 SNF。
概率和答案对不上。 raw 里真实去向是 HOME 的病例，模型平均给出 p_snf = 0.83，却仍然回答 HOME。概率值也只用了 3–6 个固定数字，AUC 0.26 只是噪音，说明 4B 模型没在读病历。
结论：这个模型做不了这项检查。strict 的 0.50 不能拿来证明泄漏已经清干净。
目前能依赖的去泄漏证据（之前已经跑出来的）：

TF-IDF 模型的 held-out AUC（在病例池上训练，再预测 300 例样本）：原始病历 0.79，strict 降到 0.65，realistic 0.71。
strict 下最有预测力的词都是临床和功能信息，比如骨折、跌倒、痴呆、轮椅、"with assistance"，没有出院去向的字眼。
被删掉的几节确实是泄漏源：单独用 DISPO 一节预测，AUC 是 0.95；单独用出院用药（MEDDC）是 0.85。
下一步，三个选项：
换模型重跑。 先用 10 例原始病历快速测阳性对照（大约 15 分钟），过了才跑完整的 strict 测试。候选是 gemma4 或 meditron:7b；qwen3:14b 太慢（每例超过 5 分钟）。
改 prompt 后再试 medgemma。 要求模型先引用证据再给答案，并把 JSON 字段的顺序调成 p_snf 在前、guess 在后。小模型很可能还是不行。
暂时跳过 LLM 检查。 在报告里写明"LLM 检查无结论：本地 4B 模型没通过阳性对照"，先以 TF-IDF 的结果为准，等后面接上 Bedrock 或更大的模型再补做。
我建议选 1，先花 15 分钟看阳性对照能不能过，过了再跑完整测试。你决定后我再动手。汇总报告和第二步代码的 commit 也等你确认

gemma4 也没过阳性对照。

模型	原始病历 10 例	准确率	AUC	平均每例
gemma4（关闭 thinking 后）	0 例失败	0.60	0.52	257 秒（中位 87 秒，最慢一例 1774 秒）
关掉 thinking 后它能正常输出答案了，SNF 和 HOME 都会猜，不再一边倒。
但原始病历里写着 "Discharge Disposition"，10 例只对了 6 例，跟随机差不多。
用我写的两句话假病历测试时它全对，换成几千词的真实病历就找不到那一行了。这是本地小模型处理长上下文时的典型问题。
速度也成问题：如果跑 60 例 strict，大约要 4 小时。
我的判断： 用这台笔记本上的本地模型做"LLM 猜结局"这项检查不可行。阳性对照过不了，strict 上的结果怎么都没法解读。

下一步的选项：

A（推荐）：先跳过这项检查，在报告里如实记录。
写明：medgemma:4b 和 gemma4 都没通过阳性对照，准确率分别是 0.50 和 0.60，所以 LLM 检查无结论。
去泄漏结论先以 TF-IDF 的 held-out 结果为准：原始病历 0.79，strict 降到 0.65，主要特征都是临床信息。
以后接上 Bedrock（Claude 或 DeepSeek）时再补做这项检查，脚本已经支持换模型。
B：再试一次改 prompt。 把问题放到病历后面，让模型读完全文再回答。先跑 10 例阳性对照，大约 15–45 分钟。成功的可能性不大，而且就算过了，60 例也还要好几个小时。
目前代码的改动：

llm_guess.py 加了 think=False，否则 gemma4 这类会"思考"的模型会把输出额度用光，返回空答案。
输出文件名带上了模型名，两次的结果分别保存在 data/sample/llm_guess_*_{model} 里。
你选 A 还是 B？如果选 A，我接着把只含汇总数字的第二步报告整理出来，给你看过之后再 commit。

The Step 2 report is written: reports/step2_leakage_report.md. It has aggregate numbers only, no note text and nothing at the case level. All 19 tests pass, and ruff is clean on the new code.

It covers six things:

Data and outputs: the 300-case sample, the 2655-case pool, and how many sentences each packet keeps.
The removal rules: a table of what is removed in strict vs realistic, plus the removal counts split by the patient's actual destination.
TF-IDF check:
Held-out AUC drops from 0.79 on the original notes to 0.65 on strict.
Used alone, the dropped Disposition section reaches 0.95 and Discharge Medications 0.85.
The strongest remaining predictors are all clinical or functional (fracture, fall, dementia, wheelchair).
Leftover keywords and section presence.
LLM guessing check: no conclusion. Neither model passed the positive control (medgemma:4b 0.50, gemma4 0.60), so the plan is to redo it once a larger model is connected.
Conclusions and four open items:
mask where patients lived before admission, as a sensitivity analysis;
Social History is mostly blank, so C6 will often PEND;
your manual review of the 50 dev cases;
redo the LLM check later.