# 第 ① 步计划：环境与仓库修复

- 日期：2026-11-08
- 分支：`zhijie-20261108`，目录 `D:\Repo\claims_agentic_system`
- 状态：**计划，未开工**。第 6 节的问题定了再动手。

## 1. 这是第 12 节的哪一步

第 ① 步"环境与仓库修复"（设计 12 节附注 1，内容见 11.5 节）。

**完成标准**（原文）：`pytest` 通过；检查脚本从 `MIMIC_RAW_DIR` 读到原始表。

## 2. 依据

- 设计 11.5（要修的三项）、11.1（目录结构）、12 节附注 1。
- CLAUDE.md：硬规则 1（原始数据只读）、7（不改测试预期值）、「随做随验证」「改动的范围」「数据与 git」「队友已经做过的工作」。
- 队友调查 `reports/teammate_survey.md` 第 4 节：两位队友都写过 `src/snf_pa/data/config.py`，与本步重叠。
- 第 15 节开放问题（3 天规则默认值、gold 标注人员）与本步无关。

## 3. 开工前的环境现状（2026-11-08 实测）

| 项 | 结果 |
|---|---|
| 分支 | 本地和远程都没有 `zhijie-20261108`，已从 `zhijie-plan-1025`（`7aa9d6e`）新建并切换，未 push |
| 本地仓库完整性 | 不是浅克隆；本地 `zhijie-plan-1025` = `origin/zhijie-plan-1025` = `7aa9d6e`（7 个 commit，`git diff` 为空）；`zhijie-plan-1108` 也指向 `7aa9d6e`。**不需要重新 clone** |
| `.env` | **不存在** |
| 原始数据 | 本机没有 E 盘。原始数据在 `D:\project data\mimiciv`，下有 `mimiciv-3.1`、`mimic-iv-ed`、`mimic-iv-note`（布局与 CLAUDE.md 一致）。**文件是 `.csv.gz`**，不是设计 11.5 写的未压缩 `.csv` |
| 原始数据是否只读 | **不是**：`Authenticated Users` 有 `Modify` 权限。我没有改 |
| 原始数据可读 | `admissions.csv.gz` 中 Medicare / 去 SNF = **244,576 / 42,312**，与附录 A 完全一致（DuckDB，0.9 秒） |
| `uv sync` | 成功；uv 0.11.28；没有 `.python-version`，uv 选了 **Python 3.14.6** |
| `pytest` | **失败**：`tests/test_sample.py` 收集阶段 `ModuleNotFoundError: No module named 'snf_pa.data'` |
| claude | 已登录（claude.ai 订阅，2.1.317），但**不在 PATH**，只有桌面应用自带的副本 |
| codex | 已登录（ChatGPT，codex-cli 0.166.0-alpha.6），**不在 PATH**，只有 Codex 应用自带的副本 |
| Ollama | **未安装**。GPU 是 RTX 3060 Laptop 6 GB |

## 4. subtask（每个都写了怎么验）

顺序执行，验过一个再做下一个。

### 1a. 建 `.env`
- 输入：`.env.example`。
- 输出：`.env`，`MIMIC_RAW_DIR=D:/project data/mimiciv`，其他项照抄模板。
- 验：`uv run python -c` 用 `python-dotenv` 读出 `MIMIC_RAW_DIR`，三个子目录都存在；`git status` 里看不到 `.env`（已被 `.gitignore`）。

### 1b. 原始数据路径模块
- 先按 CLAUDE.md 流程对照两位队友的 `config.py`（调查第 4 节）：Hui Li 的写死仓库内路径，cfeng 的用 `MIMIC_ROOT` + physionet 布局，都不符合 CLAUDE.md 的 `MIMIC_RAW_DIR`。届时在报告里写清对照结论。
- 输出：`src/snf_pa/paths.py`（位置是我的建议，设计 11.1 没列）：
  - `raw_dir()`：读 `MIMIC_RAW_DIR`（先加载 `.env`）；没设或目录不存在就报错，**不设默认值**（硬规则 4 的精神：缺就是缺）。
  - `raw_table("mimiciv-3.1/hosp/admissions")`：先找 `.csv`，没有再找 `.csv.gz`，都没有就报错。只返回路径，不打开写。
- 验：`tests/test_paths.py` 用 `tmp_path` 造假目录，测 5 种情况：只有 `.csv`、只有 `.csv.gz`、两者都有（取 `.csv`）、都没有（报错）、环境变量没设（报错）。再在本机实际解析 `admissions`，路径指向 `D:\project data\mimiciv\mimiciv-3.1\hosp\admissions.csv.gz`。

### 1c. 检查脚本改为从 `MIMIC_RAW_DIR` 读
- 改 `tests/check_batch1.py`、`tests/check_medgemma_real.py`：把 `data/mimiciv-3.1/...`、`data/mimic-iv-note/...` 换成 `raw_table(...)`。只改路径，不动逻辑。
- 验：
  - `uv run python tests/check_batch1.py` 输出 `[(244576, 42312)]`，与附录 A 一致。
  - `check_medgemma_real.py`：本机没有 Ollama，只能验到"选出病例、读到出院小结"这一段（打印的 `hadm picked`、`note loaded … chars`），模型调用那段**验不了**，报告里如实写。
  - `grep` 确认 `tests/`、`src/` 里不再有 `data/mimiciv`、`data/mimic-iv` 这类旧路径。

### 1d. 让 `pytest` 能收集（`tests/test_sample.py`）
- 现状：它 import 的 `snf_pa.data.config` 在我们分支上不存在；它校验的是旧的 300 例抽样（`data/sample/` 下的文件），我们分支上没有这个样本，按设计这个样本要在第 ② 步重新生成。
- 做法见第 6 节问题 1（需要你定）。
- 验：`uv run pytest -q` 收集无错误；`test_sample.py` 显示为 skipped，理由是"样本未生成"。

### 1e. 去掉 `chromadb`
- `uv remove chromadb`；`tests/check_rag.py` 是唯一用到它的地方，把向量部分改成内存里算余弦（仍用 Ollama 的 bge-m3），BM25 部分不动。
- 验：`uv.lock` 里没有 `chromadb`；`grep -r chromadb src tests` 为空；`check_rag.py` 的 BM25 部分能跑出 recall@5 那一行。向量部分要 Ollama，本机**验不了**。

### 1f. 设计 11.5 第二项（"test_sample.py 期望 300 例，旧文档写 50 → 统一为 300"）
- 实际情况：`test_sample.py` 已经是 `N = 300`；"50"只出现在历史材料 `plan/step 0 plan.txt`（L125、L129、L142）。历史材料不改。
- 所以这项**不需要改代码**，报告里说明。

### 1g. 干净环境验证
- `git worktree add` 到 scratchpad 下一个新目录 → `uv sync` → 用命令行传 `MIMIC_RAW_DIR` 跑 `uv run pytest -q` 和 `check_batch1.py`。确认不依赖本机残留文件。验完删掉 worktree 和临时分支。

### 1h. 报告与提交
- `reports/step1_env_repo_fix.md`：做了什么、命令、原始输出、对照完成标准、没验的部分（Ollama 相关）。
- `git status` 确认没有 `.env`、`traces/`、`data/derived/` 混入，然后在 `zhijie-20261108` commit 一次（你已授权）；不 push。

## 5. 碰哪些数据

- **读**原始数据：`mimiciv-3.1/hosp/admissions.csv.gz`（check_batch1）；`check_medgemma_real.py` 还会读 `admissions`、`diagnoses_icd`、`mimic-iv-note/note/discharge.csv.gz`（1.1 GB 压缩），只读、只打印计数。
- **写**：`.env`（不进 git）、`src/snf_pa/paths.py`、`tests/test_paths.py`、`tests/check_*.py`、`tests/test_sample.py`（视问题 1）、`pyproject.toml` / `uv.lock`、`traces/`（不进 git）、`reports/step1_env_repo_fix.md`。
- **不写** `data/` 的任何位置；不涉及受保护文件（splits、gold、合成集都还不存在）。

## 6. 需要你定的问题

1. **`tests/test_sample.py` 怎么处理？** 它的断言是旧抽样方案（5 类 × 60、只有 SNF/HHC/HOME、排除观察期、午夜数 ≥3、test 占 38–46%），与设计 3.2 / 10.1 不一致；按硬规则 7，测试预期值不能为了通过而改。
   - A（建议）：本步只把 import 挪进 `pytest.importorskip` / 文件存在判断后面，让它在样本未生成时干净地跳过，**断言一个字不动**。到第 ② 步再提出按设计重写，你同意后再改。
   - B：从 `snf-criterion-cards` 拿 Hui Li 的 `config.py`，让 import 成立（同样会因为样本不存在而跳过）。但那个文件写死仓库内路径，带着旧抽样常量。
   - C：本步直接删掉，第 ② 步按设计新写。
2. **`.csv` 还是 `.csv.gz`？** 设计 11.5 写"文件是未压缩的 `.csv`"，本机是 `.csv.gz`。建议路径模块两种都认（见 1b），并在设计 11.5 改一句"`.csv` 或 `.csv.gz` 都支持"（你同意才改设计文档）。注意：DuckDB 读 gzip 不能并行，`chartevents.csv.gz`（3.5 GB）、`labevents.csv.gz`（2.6 GB）在第 ② 步建 Parquet 子集时会慢，但只需扫一次。要不要另外解压一份到原始目录以外的地方，第 ② 步再说。
3. **Python 版本要不要固定？** 本机 uv 选了 3.14.6。主力电脑用的是哪个版本？建议加 `.python-version` 固定成和主力电脑一样，两台机器结果才可比。
4. **Ollama**：本机没装。第 ① 步完成标准不需要它，但四个 `check_*.py` 的模型部分验不了。要不要在这台机器装？（装软件由你来；6 GB 显存放得下 medgemma:4b、bge-m3，qwen3:14b 放不下，会退到 CPU）
5. **claude / codex 不在 PATH**：只能用桌面应用自带的副本，路径带版本号，应用一更新就变。这属于第 ⑥ 步（模型网关），本步先不处理；届时建议在 `.env` 加 `CLAUDE_CLI`、`CODEX_CLI` 两个可选路径，或你装独立 CLI（需要 Node.js，本机没有）。
6. **hook 先建还是后建**：建议第 ① 步开工前先建（见 `reports/proposal_hooks_settings.md`），这样 ① 本身就在护栏下做。

## 7. 可能撞上的硬规则

| 硬规则 | 在哪一步可能撞上 | 怎么避免 |
|---|---|---|
| 1 原始数据只读 | 1c、1g 读原始表 | 只用 DuckDB `read_csv` 读；不解压到原始目录；原始目录本身目前可写，建议你先按 hook 提议 L0 设成拒绝写 |
| 7 不改测试预期值 | 1d | 问题 1 选 A 时断言不动；任何断言改动都先问 |
| 3 test 隔离 | 无 | 本步不生成、不读任何划分 |
| 「验证要拿得出证据」 | 1c、1e 的 Ollama 部分 | 验不了的如实写"未验证"，不写"应该没问题" |

## 8. 需要新工具吗

- hook 与权限设置：见 `reports/proposal_hooks_settings.md`（待你同意）。
- 本步不需要 skill。
- 不派 subagent：每个 subtask 都很小，而且相互依赖（1b → 1c → 1d → 1g）。
