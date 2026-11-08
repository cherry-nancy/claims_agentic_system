# 第 ① 步报告：环境与仓库修复

- 日期：2026-11-08
- 分支：`zhijie-20261108`（基于 `7aa9d6e`），目录 `D:\Repo\claims_agentic_system`
- 计划：`reports/step1_plan.md`；hook 提议：`reports/proposal_hooks_settings.md`
- 用户决定（2026-11-08 对话）：test_sample 选 A；数据用本地路径、`.csv` / `.csv.gz` 都支持；Python 用 3.11 并补齐依赖；先不用 Ollama；claude / codex 路径留到第 ⑥ 步；先建 hook 再做 ①。

## 1. 完成标准对照

| 完成标准（设计 12 节附注 1） | 结果 | 证据 |
|---|---|---|
| `pytest` 通过 | **通过**：26 passed, 1 skipped；按审查意见修 hook 后 38 passed, 1 skipped | 4.6、4.8（干净 worktree）、第 6 节 |
| 检查脚本从 `MIMIC_RAW_DIR` 读到原始表 | **通过**：`check_batch1.py` 输出 `[(244576, 42312)]`，与附录 A 一致；`check_medgemma_real.py` 从 `MIMIC_RAW_DIR` 选出病例并读到出院小结 | 4.3 |

## 2. 做了什么

### 2.1 hook 与权限（提议已获同意）
| 文件 | 作用 |
|---|---|
| `.claude/hooks/guard.py` | PreToolUse：拦截对 `MIMIC_RAW_DIR` 的写；已存在的受保护文件不许改 / 删 / 改名（新建允许）；设计文档的修改转为"询问用户"；禁止读 `data/gold/test`、禁止 `--split test`；只许在 `zhijie-*` 分支 commit，push 只许推 `zhijie-*`，禁止 force / `--no-verify`；禁止 Claude 运行 `tools/freeze.py` |
| `.claude/hooks/stop_pytest.py` | Stop：工作区有改动且自上次通过后有变化时跑 `pytest -q -m "not slow"`，失败就拦住；第二次仍失败则放行并把失败输出显示给用户 |
| `.claude/hooks/session_start.py` | SessionStart：打印分支、`.env`、`MIMIC_RAW_DIR` 状态 |
| `.claude/settings.json` | 注册三个 hook；`allow` 常用只读 git / `uv run pytest`；`deny` 读 test-gold、force push；`ask` git push、受保护路径、设计文档、`tools/freeze.py`、`.claude/**` |
| `.claude/settings.local.json`（不进 git） | 本机专用：`deny Edit(//d/project data/mimiciv/**)` |
| `tools/freeze.py`、`data/PROTECTED.sha256`、`tests/test_protected_files.py` | L3：冻结文件的 sha256（CRLF→LF 归一化，跨机器一致），pytest 比对 |
| `tests/test_hooks.py` | 18 项（参数化展开后），对临时假仓库 + 假原始目录（路径带空格）测 guard 的放行 / 拒绝 |
| `pyproject.toml` | 注册 pytest 标记 `slow` |
| `.gitignore` | 加 `.claude/settings.local.json`、`.claude/.stop_pytest_pass` |

与提议的差别（实现时调整，需要你知道）：
- 设计文档用"询问"而不是"拒绝"：CLAUDE.md 的规则是"用户同意后再改"，询问正好对应；同时它在 hash 清单里，改了以后要你重新运行 `tools/freeze.py`，否则 pytest 失败。
- 初始的 `data/PROTECTED.sha256` 是我在 guard 生效前生成的，只含设计文档一项（含本次你同意的 11.5 / 3.1 改动）。以后冻结由你运行。
- test-gold 的 Read 拦截用权限规则做（不给每次读文件都起一个 Python 进程）。
- 2.4 的四项（test 隔离、git 护栏、SessionStart、allow 列表）全部按建议做了；检索评测集位置按建议定为 `knowledge/retrieval_eval/`，测试预期值约定放 `tests/expected/`；放行方式两种都支持（你手动改，或设 `SNF_PA_ALLOW_PROTECTED=1` 启动会话）。
- 已知误拦：`echo git push origin cfeng`、`echo rm -rf data` 这种只是字符串里出现的命令也会被拦（guard 只看文本）；commit message 里同一行同时出现删除类词和受保护路径也会被拦。
- 审查后又做了一轮加固（第 6 节），以第 6 节为准。

### 2.2 第 ① 步本身
| subtask | 改动 |
|---|---|
| Python 3.11 | `uv python install 3.11`（得到 3.11.15）；`.python-version` = `3.11`；`requires-python` `>=3.12` → `>=3.11`；`uv lock`。3.11 下所有依赖都能 import（4.1），没有缺包 |
| 1a `.env` | 由 `.env.example` 生成，`MIMIC_RAW_DIR=D:/project data/mimiciv`；被 `.gitignore` 忽略 |
| 1b 路径模块 | `src/snf_pa/paths.py`：`raw_dir()`（读 `MIMIC_RAW_DIR`，未设或不存在就报错，无默认值）、`raw_table(name)`（先 `.csv` 后 `.csv.gz`）、`sql_path()`；`tests/test_paths.py` 6 个用例 |
| 1b 附带 | `pyproject.toml` 加 `[build-system]`（hatchling，`packages = ["src/snf_pa"]`），让 `uv sync` 以可编辑方式安装 `snf_pa`。原因：之前只有 pytest 能 import `snf_pa`（靠 `pythonpath = src`），检查脚本 `uv run python tests/check_*.py` 会 `ModuleNotFoundError`；设计 11.2 的 `snf-pa` 命令行以后也需要 |
| 1c 检查脚本 | `check_batch1.py`、`check_medgemma_real.py` 的路径改为 `raw_table(...)`，逻辑不变 |
| 1d `test_sample.py` | 只把 `from snf_pa.data import config as C` 改成 `pytest.importorskip(...)`，**断言一个字没动**；样本未生成时整个文件跳过 |
| 1e chromadb | `uv remove chromadb`；`check_rag.py` 向量部分改为内存余弦，Ollama 不可用时只跑 BM25 |
| 设计文档 | 你同意的改动：3.1 附注 1 与 11.5 第一条改为"`.csv` 或 `.csv.gz` 都支持"（diff 见 4.9） |
| 1f | `test_sample.py` 本来就是 `N = 300`，"50"只在历史材料 `plan/step 0 plan.txt`；不改 |

## 3. 队友工作对照
本步与两位队友的 `src/snf_pa/data/config.py` 重叠（`reports/teammate_survey.md` 第 4 节）。对照结论：**两者都不采用**，自己写 `paths.py`。
- `snf-criterion-cards`（Hui Li，`b31285a`）：原始路径写死为仓库内 `data/mimiciv-3.1/...`，违反 CLAUDE.md「代码一律从 `MIMIC_RAW_DIR` 读路径，不写死」；文件还带着旧抽样常量（5 类、配额、test 规则），这些属于第 ② 步，且与设计 3.2 / 10.1 不一致。
- `cfeng`（`1c19996`）：读 `MIMIC_ROOT`、默认 `<repo>/physionet.org/files`、physionet 目录布局，不加载 `.env`。变量名、布局与 CLAUDE.md 规定的 `MIMIC_RAW_DIR` 不同，且有默认值（缺失时不报错）。
- 这是变量名 / 位置层面的差异，不涉及结果口径，所以不写分歧说明。第 ② 步对照队友的队列代码时再看是否要统一变量名。

## 4. 命令与原始输出

### 4.1 Python 3.11 与依赖
```
$ uv python pin 3.11 && uv lock && uv sync && uv run python --version
Pinned `.python-version` to `3.11`
Using CPython 3.11.15 interpreter at: C:\Users\czj02\AppData\Roaming\uv\python\cpython-3.11.15-windows-x86_64-none\python.exe
Resolved 123 packages in 444ms
Updated numpy v2.5.4 -> v2.4.6, v2.5.4
Updated soupsieve v3.0.4 -> v2.10, v3.0.4
Python 3.11.15

$ uv run python -c "import ...; print versions"
bs4 4.15.0 / chromadb 1.5.9 / duckdb 2.0.0 / httpx 0.28.1 / langchain_aws 1.9.0 / langchain_core 1.7.0
langchain_ollama 1.1.0 / langgraph ok / polars 2.0.0 / pydantic 2.14.1 / pypdf 6.21.2 / dotenv ok
yaml 6.0.3 / rank_bm25 ok / tenacity ok / pytest 9.1.1 / numpy 2.4.6 / ruff 0.17.2
```
（chromadb 之后在 1e 删除。）注意：lock 对 3.11 和 3.12+ 分了两套 numpy / soupsieve 版本（3.11 上 numpy 2.4.6，3.12+ 上 2.5.4）。两台机器都用 `.python-version` 的 3.11 就一致。

### 4.2 `.env`
```
$ git status --short --ignored .env
!! .env
$ uv run python -c "load_dotenv(); ..."
'D:\\project data\\mimiciv'
mimiciv-3.1 True
mimic-iv-ed True
mimic-iv-note True
```

### 4.3 路径模块与检查脚本
```
$ uv run pytest tests/test_paths.py -q
6 passed in 0.20s

$ uv run python -c "from snf_pa.paths import raw_table; ..."
D:\project data\mimiciv\mimiciv-3.1\hosp\admissions.csv.gz
D:\project data\mimiciv\mimic-iv-note\note\discharge.csv.gz
D:\project data\mimiciv\mimic-iv-ed\ed\edstays.csv.gz

$ uv run python tests/check_batch1.py
[(244576, 42312)]

$ uv run python tests/check_medgemma_real.py
hadm picked: admission_type=SURGICAL SAME DAY ADMISSION, from=PHYSICIAN REFERRAL, midnights=4; note loaded 6107 chars in 16s
redacted: 6107 -> 5889 chars; leak-pattern hits remaining: 0
model: medgemma:4b
FAILED after 2s: ConnectError (output not shown, may contain note text)

$ grep -rnE "data/mimic|mimiciv-3\.1/|\.csv\.gz" src tests --include=*.py   (除 test_hooks / test_paths)
只剩 paths.py 的说明文字和 raw_table(...) 调用，没有旧路径
```

### 4.4 chromadb
```
$ uv remove chromadb
$ grep -c 'name = "chromadb"' uv.lock
0
$ grep -rn chromadb src tests pyproject.toml
（无输出）
$ uv run python tests/check_rag.py
embeddings unavailable (ConnectError); running BM25 only
...
recall@5 (pattern appears in a top-5 chunk): {'bm25': '6/6'}
```

### 4.5 hook 测试
```
$ uv run pytest tests/test_hooks.py tests/test_protected_files.py -q
（第一次）2 failed, 18 passed
  - gzip -dc 被误拦（组合参数没识别）→ 修 guard 的参数匹配
  - "/c/..." Git Bash 路径在命令中间没被归一化 → 修 norm()
（修后）20 passed in 11.23s   （test_hooks 18 项 + test_protected_files 2 项）
```
按 settings.json 里的原样命令管道测试（真实路径，只喂输入、不执行）：
```
[Write D:\project data\mimiciv\probe.txt] exit=2  [guard] BLOCKED: ... inside MIMIC_RAW_DIR ...
[Edit  D:\project data\mimiciv\mimiciv-3.1\hosp\admissions.csv.gz] exit=2  BLOCKED
[Edit  ...\plan\snf_pa_consensus_work_plan_1025.md] exit=0  {"permissionDecision": "ask", ...}
[Write ...\src\snf_pa\paths.py] exit=0
[PowerShell Remove-Item "D:\project data\mimiciv\mimic-iv-ed" -Recurse] exit=2  BLOCKED
[PowerShell Get-ChildItem "D:\project data\mimiciv"] exit=0
```
会话内实测（hook 已生效）：
```
$ echo git push origin cfeng
PreToolUse:Bash hook error: [guard] BLOCKED: push target 'cfeng' is not a zhijie-* branch
```
SessionStart 输出（当时 `.env` 还没建）：
```
[session] repo=D:\Repo\claims_agentic_system branch=zhijie-20261108
[session] WARNING: .env is missing (copy .env.example and set MIMIC_RAW_DIR).
```

### 4.6 全量 pytest
```
$ uv run pytest -q -rs
SKIPPED [1] tests\test_sample.py:8: sample not built yet (design step 2)
26 passed, 1 skipped in 10.96s
```
`pytest --collect-only`：test_hooks 18 + test_paths 6 + test_protected_files 2 = 26；test_sample 整个文件跳过。

### 4.7 test_sample.py diff
```
-from snf_pa.data import config as C
+# The old-plan sample module is not on this branch; skip until step 2 builds the sample (assertions unchanged).
+C = pytest.importorskip("snf_pa.data.config", reason="sample not built yet (design step 2)")
```

### 4.8 干净环境验证
新建 detached worktree（scratchpad 下），把本次未提交的改动以 patch + 未跟踪文件拷入（不含 `.env`、`settings.local.json`），新建 venv：
```
$ uv sync            → Python 3.11.15，全部依赖重新安装
$ env -u MIMIC_RAW_DIR uv run pytest -q -rs
SKIPPED [1] tests\test_sample.py:8: sample not built yet (design step 2)
26 passed, 1 skipped in 11.67s
$ env -u MIMIC_RAW_DIR uv run python tests/check_batch1.py
RuntimeError: MIMIC_RAW_DIR is not set; copy .env.example to .env and set it
$ MIMIC_RAW_DIR="D:/project data/mimiciv" uv run python tests/check_batch1.py
[(244576, 42312)]
$ git worktree remove --force <worktree>   → 已删除，无临时分支
```

### 4.9 设计文档 diff（你同意的改动）
```
-1. **原始 CSV**：MIMIC-IV 3.1 hosp / icu、ED、Note，未压缩；目录只读。labevents 18GB、chartevents 42GB，不能整表读进内存。
+1. **原始 CSV**：MIMIC-IV 3.1 hosp / icu、ED、Note；未压缩的 `.csv` 或 PhysioNet 原样的 `.csv.gz` 都支持（各台电脑不同）；目录只读。labevents 18GB、chartevents 42GB（未压缩），不能整表读进内存。
-- 现有检查脚本从 `data/mimiciv-3.1/...` 读原始表（旧的仓库内位置），而且按 `.csv.gz` 读 → 改为从 `MIMIC_RAW_DIR` 读，文件是未压缩的 `.csv`。
+- 现有检查脚本从 `data/mimiciv-3.1/...` 读原始表（旧的仓库内位置）→ 改为从 `MIMIC_RAW_DIR` 读；文件是未压缩的 `.csv` 或 `.csv.gz`，两种都支持（优先 `.csv`）。
```

## 5. 没做或没验的

- **Ollama 相关全部未验证**（你决定先不用）：`check_ollama.py`、`check_langgraph.py` 没跑；`check_medgemma_real.py` 只验到读数据，模型调用 `ConnectError`；`check_rag.py` 只验了 BM25。
- **原始数据目录仍然可写**：L0 的 ACL 要你执行（命令见 `reports/proposal_hooks_settings.md` 2.1），我没改权限。guard 只能拦命令文本里看得到的写，脚本内部的写拦不住。
- `settings.local.json` 的 `Edit(//d/project data/mimiciv/**)` 规则没有实测（实测要真的往原始目录写，违反硬规则 1）；同一目录由 guard 拦，guard 已用真实路径管道测试过。
- `check_*.py` 仍然叫 check、不被 pytest 收集，属于手动检查脚本，没有改成测试。
- claude / codex 不在 PATH（第 ⑥ 步处理）。
- 独立审查：见第 6 节。

## 6. 独立审查

按 CLAUDE.md，用一个全新的 subagent（只给设计文档、CLAUDE.md 和本次 diff，不给我的结论）做只读审查。它复跑了 pytest（26 passed, 1 skipped）、`check_batch1.py`（`[(244576, 42312)]`）和 `check_rag.py`，结论是第 ① 步本身（paths.py、检查脚本、测试、设计文档改动、pyproject）没有严重问题；问题都在 hook 上。逐条处理：

| # | 审查发现 | 是否成立 | 处理 |
|---|---|---|---|
| 1 | guard 直接调 `.venv` 的 Python；新克隆没 `.venv` 时 exit 127，Claude Code 当作非阻断错误，**全部放行**；guard 内部异常同样放行 | 成立 | settings.json：没有 `.venv` 时退到 `uv run --no-project python`（guard 只用标准库），并设 `onFailure: "block"`；guard 内部异常改为拒绝（fail closed）；给你留了逃生开关 `SNF_PA_GUARD_OFF=1`（只能在启动会话时设，命令里内联设无效）。实测：临时目录无 `.venv` 时仍然拦住写原始目录（exit 2） |
| 2 | 设计文档被冻结后，你同意的修改会让 `test_protected_files` 失败，Stop hook 要求"修根因"，而 Claude 又不能重新冻结，最可能的结果是**把你同意的修改改回去** | 成立 | 保留冻结（硬规则 7 明确保护附录 A 计数）；Stop hook 识别到是 `test_protected_files` 失败时，改为提示"不得回退用户同意的修改，停下请用户运行 `tools/freeze.py`" |
| 3 | `tools/freeze.py` 的子串规则连 `cat`、`git add`、`git diff` 都拦 | 成立（审查时它自己的 `cat` 被拦） | 只拦"运行"（`python` / `uv run` / `./tools/freeze.py` 后跟该路径）；读、暂存、diff 放行。已加测试 |
| 4 | 只认显式写出的受保护路径：`git checkout origin/<分支> -- data/`、`git restore .`、`rm -rf data`、`cd <raw> && rm x`、`git -C <raw> init` 都能绕过 | 成立。第一条正是 CLAUDE.md 规定的采用队友代码的写法 | 新增：父目录（`.`、`*`、`data` 等）传给删除类命令或 git 写操作，且受保护目录里已有文件时拒绝；`git reset --hard <其他提交>` 在有受保护文件时拒绝；跟踪 `cd` / `Set-Location` 进入原始目录后的写；原始目录上的任何 git 命令拒绝。受保护目录为空时不拦（没东西可保护，第 ② 步要能建）。已加 7 + 5 个测试 |
| 5 | guard 里对 Read / Grep / Glob 的 test-gold 判断永远不会执行（matcher 没包含这些工具），测试直接调 guard 所以测不出 | 成立 | matcher 加上 `Grep|Glob`，Glob 的 pattern、Grep 的 glob 也检查；Read 仍靠权限规则 `Read(data/gold/test/**)`（不给每次读文件起进程）。**剩余缺口**：对仓库根目录的整体 Grep 会搜到 test-gold 文件，等第 ⑧ 步 test-gold 真的存在时再定（例如放到工作区外） |
| 低 | 受保护文件存在性用小写路径判断，在区分大小写的 Linux 上会误判为不存在 | 成立 | 改用原始大小写路径判断 |

修完后的验证：
```
$ SNF_PA_GUARD_UNDER_TEST=<scratchpad>/guard_new.py uv run pytest tests/test_hooks.py -q
（先在 scratchpad 副本上测，避免装上有错的 guard 把自己锁死）
第一次 1 failed（Glob 无 path 时提前 return）→ 修 → 30 passed
$ uv run pytest -q -rs
SKIPPED [1] tests\test_sample.py:8: sample not built yet (design step 2)
38 passed, 1 skipped in 16.82s
$ 无 .venv 的临时目录 + settings.json 原样命令，喂"写原始目录"
[guard] BLOCKED: D:\project data\mimiciv\x.txt is inside MIMIC_RAW_DIR ...   exit=2
$ 会话内实测
head -3 tools/freeze.py        → 放行
echo rm -rf data               → [guard] BLOCKED: 'data' contains the protected path data/protected.sha256 ...
```
guard 和 settings.json 的修改是通过 Edit / Write 工具做的，按 `.claude/**` 的 ask 规则逐次经过你的确认。
