\### Step 3: Policy RAG

下面是第三步（Policy RAG）的计划。我还没有动手。



对应关系

总计划的 Step 3「政策知识库」就是共识计划的 Step 7「政策 RAG 语料与检索评测」，下面以共识计划为准。

共识计划的 Step 2「criterion cards」你已经做完了（criterion\_cards.yaml）。所以这一步不再整理标准本身，只做"语料、切块、检索、评测"。

共识计划的核心原则：判定主要靠 criterion card 直接绑定的条文，检索只起补充作用。

检索主要用在三处：Reviewer 遇到卡片之外的情况时去查（policy\_search）；Critic 核对引用；决定信引用条款。

共识计划还规定，Policy RAG 是一个工具，不是 agent（D10，Step 9 注释）。

这一步完全不碰 MIMIC 数据。 语料都是公开的法规和 CMS 文件，切块结果和评测集都可以直接入库，没有泄漏或 DUA 的问题。

现状

已有	说明

Tier 1 法规	42cfr409\_subpartD.xml，以及 §422 的 15 个 XML（eCFR 2026-10-01 版本）

Tier 2 指导	BPM Ch.8 PDF（Rev. 12283）、CMS 2024-02 FAQ（PDF 和 txt）

原型	tests/check\_rag.py：已经做过 CFR/BPM 切块、bge-m3 向量、BM25、RRF 融合，还有少量测试问题

依赖	chromadb、rank-bm25、pypdf、bs4 已经装好；Ollama 里有 bge-m3

和共识计划清单相比，还缺这些文件：



Tier 1：

§424.20：SNF 的医师证明（physician certification），对应 C7；

§409.60–61：benefit period，以及 100 天上限和共付。

Tier 2： CMS 关于 Jimmo 和解的说明；NDMC（不予覆盖）通知的要求；Parts C\&D 的 coverage determination 和申诉指南。

Tier 3（只用来做负向测试，防止误引）：

TEAM 的 3-day 豁免（MLN MM14098）；

WISeR 说明；

CMS-0057-F 摘要。

BPM Ch.8 的版本：还没核对 Rev. 12283 是不是当前最新版。





\### After discussing with cc, we don't have physician certificate and benefit period information, so 

there is no need to download them. CC also confirmed that local BPM ch.8 file is up-to-date. So nothing 

to download.



1\. 医师证明和 benefit period：不纳入语料

医师证明（C7，§424.20）：共识计划 D2 的 profile 里已经有 physician\_cert: assume\_submitted，和你说的"假设都有证明"是一回事。不下载 §424.20。

benefit period（§409.60–61：每个 benefit period 最多 100 天，第 21 天起要共付）：MIMIC 里没有这类数据，假设每个病人都还有可用天数。我会在 profile 里加一行 benefit\_days\_available: assume\_true，写明这个假设。不下载这两条。

2\. Tier 2 重不重要：BPM Ch.8 很重要，其余可以不要

做医学必要性判断时，BPM Ch.8 是核心，它的重要性不低于 Tier 1。



42 CFR 409.31–409.35 只规定了原则，比如"需要 skilled services""每天""只能在 SNF 实际提供"，写得很简短。

怎么判断"算不算 skilled"，审核员实际依据的是 BPM Ch.8 §30 的解释和例子：

BPM Ch.8	内容	对应标准

§30.2–30.3	skilled nursing 和 skilled rehab 的定义与举例；病人本身病情复杂，需要专业人员管理	C3、C4

§30.2.3.1–30.2.3.3	三类容易被漏判的 skilled services：照护计划的管理与评估、病情观察与评估、病人和家属教育	C4

§30.4	skilled therapy 的条件；§30.4.1.2 是维持性治疗（Jimmo）	C4、C5

§30.6	"每天"的含义：skilled rehab 每周 5 天、restorative nursing 每周 6 天，不能人为隔开安排	C5

§30.7	"practical matter"：能不能在家由照护者提供，提供这些照护的其他方式能否报销不影响判断	C6

你的 criterion cards 里，A16/A17 和 evidence\_hints 已经引用了这几节。

Jimmo 不需要另外下载。 2014 年 CMS 按 Jimmo 和解修订了 BPM，§30.4.1.2 就是修订后的文字。



其他 Tier 2 文件：



CMS 2024-02 FAQ：大部分讲 MA 的流程。和医学必要性直接相关的只有两条：

Q2：用算法或 AI 时，判定必须基于病人的具体情况；

Q7：MA 计划不能用比 TM 更严格的标准拒绝 post-acute 入住。 这两条可以作为"系统设计原则"留在语料里，Reviewer 判定时用不到。

NDMC 通知、Parts C\&D 申诉指南：只关于流程，不下载。

§422 的那 15 个 XML 也是同样的情况。 内容大多是时限、申诉、通知、委员会这类流程规定，和"病人是否需要 skilled care"无关。我建议这次不把它们放进 Reviewer 的检索索引，文件留在 policy\_docs/，等以后做决定信模板或时限检查时再用。可能的例外是 §422.101(b)(c)：它规定 MA 必须沿用 TM 的标准，可以用来说明"为什么用 409 判 MA"，作为背景条文保留。



3\. Tier 3 是什么

共识计划里的 Tier 3 指听起来和 Medicare PA 或 SNF 相关、但不能作为判定依据的文件。放进语料，是为了测试系统会不会误引它们。原计划列了这几类：



文件	内容	为什么不能用来判定

TEAM（CMS Innovation Center 的强制模式，2026-01-01 起）	参与医院的 TM 病人，在髋部骨折、关节置换、脊柱融合等手术的 episode 里，可以豁免 SNF 的 3-day 住院要求	只适用于参与医院的 TM 病人，不适用于 MA 的 PA；而且讲的是 3-day 规则（C1），不是医学必要性

WISeR（2026-01-01 起，在 6 个州的 TM 里试点，用 AI 厂商做 prior auth）	对少数服务（如皮肤替代物、神经刺激器、膝关节镜）要求 PA	只适用于 TM，不包括 SNF。风险在于模型看到"Medicare + PA + AI"就会联想到它

CMS-0057-F（互操作性与 PA 规则）	PA 的时限（72 小时 / 7 天）、API、拒绝理由要具体	内容已经写进你手上的 §422.122 和 §422.568；而且是流程，不是医学标准

州法规（如加州 SB 1120：拒绝决定必须由医师复核）	对 AI 参与 PA 的限制	MA 受联邦法优先（§422.402），州法不直接适用

OIG 报告（如 2022 年的报告：MA 拒绝的 PA 中约 13% 其实符合 Medicare 覆盖标准）	说明 MA 存在误拒问题	是背景和动机，可以给投资人讲，不是规则

我的建议：这次不做 Tier 3。



你的重点是医学必要性。TEAM 只影响 C1，而 C1 已经由 profile 的开关和代码处理了；其他几类都和 C3–C6 无关。

不放进语料，系统也就检索不到它们。Reviewer 的 policy\_refs 只能填语料里的 chunk ID，所以在结构上也引用不了。

剩下的风险是模型凭记忆在理由里写出"TEAM""WISeR"。这个用一条简单的文本检查就能拦住，不需要下载文件。

以后做投资人 demo，或者扩展到"Medicare PA 问答"时，再按需加入 Tier 3。

这会修改共识计划 D2 里"TEAM 进 Tier 3 语料、加负向检索测试"的做法。我会在 Step 3 的报告里注明这个变更。



修改后的第三步范围

语料：

42 CFR 409 Subpart D（Tier 1）；

BPM Ch.8 §30，以及作为背景的 §20（Tier 2，核心）；

可选：FAQ 的 Q2/Q7 和 §422.101(b)(c)，作为背景，不进判定检索。

下载：基本不需要新文件，只核对 BPM Ch.8 是不是当前版本。

评测集：仍然约 40 条，但去掉 MA 流程题和 TEAM/WISeR 负向题，改成以 C3–C6 的临床情景为主。重点覆盖容易判错的点：

维持性治疗（Jimmo）；

观察与评估、照护计划管理这类"看不出是 skilled"的服务；

一周 5 天和 6 天的计算；

照护者在家能否提供、替代照护能否报销都不影响判断。

切块、卡片绑定、hybrid 检索、引用校验：和上一版计划一样。语料变小，大约 120–200 个 chunk，工作量也能降到 2 天左右。



Only policy text goes into the vector store. No patient notes go in.



What gets stored

Each chunk produced in 3.2 becomes one row, with three parts:



Part	Example	Purpose

chunk\_id + metadata	BPM8:30.4.1.2, tier 2, citation "BPM Ch.8 §30.4.1.2", title, URL	Identifies which clause this is; the Reviewer cites it by this ID

Original text	The full paragraph on maintenance therapy (Jimmo)	Returned as-is when the chunk is retrieved

Vector (embedding)	1024 floats produced by bge-m3	Used to measure how close a query is to this chunk in meaning

With the narrowed scope that's roughly 120–200 rows: 42 CFR 409 Subpart D plus BPM Ch.8 §20/§30.



How it's used at search time

A query comes in, for example "a stroke patient whose condition won't improve: can they still get skilled PT?"

bge-m3 turns the query into a 1024-dimensional vector as well.

The query vector is compared with all \~150 chunk vectors (cosine similarity), and the closest ones are taken, e.g. BPM8:30.4.1.2 (maintenance therapy).

In parallel, BM25 ranks the chunks by keyword overlap. BM25 doesn't need a vector store; it works directly on the text.

RRF merges the two rankings, and the top k chunks (ID plus original text) go back to the Reviewer.

Vector search catches matches with different wording (the query says "won't improve" while the regulation says "maintenance"). BM25 catches exact terms ("5 days per week", "409.33").



\### Confirmed with CC what would go into RAG at this step?



vector store 里放的是政策原文，来自两份文件：



文件	是否放进 vector store	原因

42cfr409\_subpartD.xml	放	SNF 覆盖条件的法规原文（§409.30–409.36）

bp102c08.pdf（BPM Ch.8）	放（只放 §20 和 §30）	skilled services 的解释和举例，判断医学必要性主要靠它

15 个 42cfr422\_\*.xml	不放	内容是 MA 的流程：时限、申诉、通知、委员会，和"病人是否需要 skilled care"无关。可选：§422.101 作为背景条文，但不进判定检索

criterion\_cards.yaml	不放	卡片不靠检索，而是直接给 Reviewer 用（见下）



criterion cards 和 vector store 的分工

两者用法不同：



criterion cards 是主力，不经过检索。

Reviewer 判 C3–C6 时，代码按标准直接把对应的卡片放进 prompt。比如判 C5 时放 A8、A18、A19。

卡片里有条文摘录、summary\_zh、guardrail 和 evidence\_hints，是整理过的判定规则。

vector store 是补充。 当病例遇到卡片没覆盖的情况，Reviewer 调用 policy\_search 去查原文。

例子 1：气管切开护理算不算 skilled？答案在 BPM §30.3 的举例里。

例子 2：病人只需要观察病情，算不算 skilled？答案在 §30.2.3.2。

这些细节大多在 BPM 里，卡片只摘了 42 CFR 的核心条文。

两者的连接点是 3.3 的"卡片绑定"。

每张卡的 cfr 字段会对应到 vector store 里的一个 chunk ID，例如 A9 → CFR:409.31(b)(2)。

代码会检查卡片里的 text\_verbatim 能不能在那个 chunk 的原文里逐字找到。

这样卡片引用的永远是语料里真实存在的条文。



为什么不把 cards 也放进去

内容重复。 卡片的 text\_verbatim 本来就是从 409 原文摘出来的。两份都放，检索时会返回两条几乎一样的结果，挤掉别的有用条文。

规则和解读会混在一起。 卡片的 note、guardrail 和 evidence\_hints 是我写的解读，不是法规原文。如果它们和原文一起被检索出来，Reviewer 引用时就分不清"法规怎么说"和"我们怎么理解"。按共识计划，引用必须指向原文条款。



1\. 什么是"卡片绑定"

就是给每张卡记下"它摘自语料里的哪一块原文"，再用代码核对摘得对不对。



拿 A9 举例：





criterion\_cards.yaml                       vector store 里的 chunk

─────────────────────                      ─────────────────────

id: A9                                     chunk\_id: CFR:409.31(b)(2)

cfr: 42 CFR 409.31(b)(2)        ──绑定──►  citation: 42 CFR 409.31(b)(2)

text\_verbatim: "The daily skilled          text: "(2) The daily skilled services

&#x20; services must be ones that..."                  must be ones that, as a practical

summary\_zh / guardrail / ...                     matter, can only be provided..."

绑定程序（bind\_cards.py）对每张卡做三件事：



找 chunk：把卡片的 cfr（"42 CFR 409.31(b)(2)"）换算成 chunk ID（CFR:409.31(b)(2)），确认语料里真的有这一块。

核对原文：统一引号和空白后，卡片里的 text\_verbatim 必须能在那块原文中逐字找到。找不到就报错。

核对 see\_also：卡片 see\_also 里列出的条款也要能找到对应的 chunk。



为什么要做绑定：



防止抄错。 卡片是人工整理的，可能漏字或改了措辞。之前 §409.35 的弯引号问题就属于这类。绑定会自动把这种问题找出来。

防止版本漂移。 以后 eCFR 或 BPM 更新了，原文一变，绑定就会失败，你立刻知道哪张卡需要更新。

引用统一。 Reviewer 用卡片判定时，引用填的是 chunk ID（如 CFR:409.31(b)(2)）。这和检索结果用的是同一套 ID，所以代码可以用同一种方法验证所有引用、回填原文，决定信里也能显示出处。



2\. criterion\_cards.yaml 会用在哪里

会用到，而且是系统的核心文件。用在下面这些地方：



阶段	谁用	怎么用

Step 3（这一步）	绑定程序	核对卡片和原文是否一致（如上）

Step 8 标注 gold	标注人（你和同事）	作为标注规则：每条标准按卡片的条文和 evidence\_hints 判 MET / NOT\_MET / INSUFFICIENT，标注口径和系统一致

Step 9 Criteria Reviewer（主要用途）	LLM	每个病例判 C3–C6 时，代码把对应卡片放进 prompt：条文原文、guardrail，以及 evidence\_hints 里的 question、supports、against、pend\_if 和 rfi。Reviewer 对照病历逐条判定

Step 9 Critic	LLM	复核 Reviewer 的结论时，用同一套卡片检查有没有违反 guardrail。比如有没有因为"病情不会好转"就判 NOT\_MET，这违反了 Jimmo 规则

Step 9 Aggregator 和决定信	代码、模板	PEND 时，用卡片的 rfi 生成"需补交资料"清单；决定信里引用卡片绑定的条款号和原文

Step 10 ablation	评估	共识计划的 A1 是"不给政策"，A2 是"A1 + 全部 criterion cards"。两者对比，衡量卡片本身带来多少提升

各部分的分工：



卡片：决定"判什么、怎么判"，每个病例都会用到。

vector store：只在卡片没覆盖到的情况下，让 Reviewer 去查 BPM 原文。

所以按共识计划的说法，卡片是主力，检索是补充。









&#x20;



