# 提议：hooks 与 `.claude/settings.json` 权限设置

- 日期：2026-11-08
- 分支：`zhijie-20261108`，目录 `D:\Repo\claims_agentic_system`
- 状态：**只是提议，未建任何文件**。用户同意后再实现。
- 依据：CLAUDE.md「可以提议建工具」、硬规则 1 / 3 / 7、「随做随验证」。

## 0. 为什么需要

CLAUDE.md 的几条硬规则靠文字约束不可靠，而且本机已经出现一个具体风险：

- **原始数据目录不是只读的。** `D:\project data\mimiciv` 的 ACL 给 `NT AUTHORITY\Authenticated Users` 的是 `Modify, Synchronize`，当前用户可以写、删、改名。（2026-11-08 `Get-Acl "D:\project data\mimiciv"` 的输出；`mimiciv-3.1` 子目录相同。）
- 无人值守运行时没有人盯着每一条命令；受保护文件（splits、gold、合成集预期结论）被改一次，后面的评估全部不可信，而且事后很难发现。

## 1. 分四层，从强到弱

| 层 | 机制 | 能拦住什么 | 拦不住什么 |
|---|---|---|---|
| L0 | **操作系统 ACL（用户自己设）** | 任何进程写原始数据目录，包括 Python 脚本内部的写 | — 最可靠 |
| L1 | `.claude/settings.json` 的 `permissions` | Claude 用 Read / Edit / Write 工具碰特定路径 | Bash / PowerShell 里的命令 |
| L2 | `PreToolUse` hook（`guard.py`） | Bash / PowerShell 命令字符串里出现的写操作 + 路径；Edit / Write 的补充判断 | 脚本内部的写（命令里看不到路径） |
| L3 | 受保护文件 hash 清单 + pytest 校验 | **任何途径**造成的受保护文件变化（事后发现） | 不能事前阻止 |
| L4 | `Stop` hook 跑 pytest | 结束前测试没过就不让停 | — |

L2 只是防误操作，不是安全边界；原始数据真正靠 L0，受保护文件真正靠 L3。

## 2. 各项提议

### 2.1 禁止写 `MIMIC_RAW_DIR`

**L0（用户执行，我不改权限）**：给当前用户加一条拒绝写的 ACE，例如在管理员 PowerShell 里：

```powershell
icacls "D:\project data\mimiciv" /deny "$env:USERNAME:(OI)(CI)(W,D,DC,WDAC,WO)"
```

撤销：`icacls "D:\project data\mimiciv" /remove:d "$env:USERNAME"`。设完以后读不受影响，DuckDB 照常读 `.csv.gz`。

**L1**：`permissions.deny` 加 `Edit(//d/project data/mimiciv/**)`、`Write(//d/project data/mimiciv/**)`、`NotebookEdit(...)`。路径写法（Windows 盘符、带空格）实现时要实测一次。

**L2**：`guard.py` 从 `.env` 读 `MIMIC_RAW_DIR`，把命令里的路径统一成小写、正斜杠（`D:\…`、`D:/…`、`/d/…` 都认）。命令里出现原始目录 **且** 出现写类操作时拒绝：`>`、`>>`、`rm`、`mv`、`cp … <raw>`、`tee`、`sed -i`、`touch`、`mkdir`、`Remove-Item`、`Move-Item`、`Rename-Item`、`Copy-Item -Destination`、`New-Item`、`Set-Content`、`Add-Content`、`Out-File`、`icacls`、`attrib`、`takeown`、`git -C <raw>`。只读命令（`ls`、`Get-ChildItem`、`duckdb` 读）放行。

### 2.2 禁止修改受保护文件

**受保护路径（建议）**

| 路径 | 对应硬规则 7 的哪一项 | 说明 |
|---|---|---|
| `data/splits/**` | dev / test 划分 | 第 ② 步生成 |
| `data/synthetic/**` | 合成回归集预期结论 | 第 ⑥ 步；预期结论在病例 JSON 里，整目录保护 |
| `data/gold/**` | gold 标注 | 第 ⑧ 步 |
| 检索评测集（**位置待定**，建议 `knowledge/retrieval_eval/**`） | 检索评测集 | 第 ⑤ 步；设计文档没定位置 |
| `tests/expected/**` | 测试预期值 | 建议约定：测试的预期值放这里，不写死在测试函数里 |
| `plan/snf_pa_consensus_work_plan_1025.md` | 附录 A 计数；正文不得自改 | 整份保护 |

**规则**：文件**不存在时允许创建**（第 ② 步要生成 splits）；**已存在的不允许改、删、改名**。要改：Claude 停下说明原因，用户自己改，或用户临时设环境变量 `SNF_PA_ALLOW_PROTECTED=1` 启动会话。

- **L1**：受保护路径的 `Edit` 放进 `permissions.ask`（交互时弹窗，用户逐次确认）。
- **L2**：`guard.py` 对 Edit / Write 判断目标是否已存在；对 Bash / PowerShell 判断命令里的写操作是否指向受保护路径。Write 覆盖已存在文件 → 拒绝。
- **L3**：`data/PROTECTED.sha256`（本身受保护）记录冻结文件的 sha256；`tests/test_protected_files.py` 逐个比对，不一致就失败。冻结一个文件 = 用户确认后，由用户运行 `uv run python tools/freeze.py <路径>` 把它加进清单。这一层能发现脚本内部、`git checkout` 等任何途径造成的改动。
- 按病例 ID 写特殊处理（硬规则 7 后半句）hook 拦不住，靠审查。

### 2.3 结束前必须跑 pytest

**L4：`Stop` hook**

- 触发：每次 Claude 准备结束一轮时。
- 只在工作区有改动时跑（`git status --porcelain` 非空，排除 `traces/`、`data/derived/`），纯对话的轮次不跑。
- 命令：`uv run pytest -q -m "not slow"`，超时 300 秒。读大表、调 LLM 的测试标 `slow`，不在这里跑（避免每轮几分钟）。
- 失败：返回 `{"decision": "block", "reason": <pytest 输出最后 40 行>}`，Claude 必须继续修。
- 防死循环：输入里 `stop_hook_active` 为真（已经因为失败被拦过一次）时不再拦，但把失败输出原样留给用户看。这对应 CLAUDE.md「验失败了如实说」。

### 2.4 另外建议加的（同样只提议）

| 项 | 解决什么 | 机制 |
|---|---|---|
| test 隔离 | 硬规则 3：不读 test-gold，不在 test 上看中间结果，正式评估只由用户触发 | `permissions.deny`：`Read(data/gold/test/**)`；guard 拒绝命令里出现 `data/gold/test`、`--split test` 的命令（用户在自己的终端里跑正式评估）。前提：gold 按 `data/gold/dev/`、`data/gold/test/` 分目录 |
| git 护栏 | 只在 `zhijie-*` 上提交；push 要用户确认；不碰队友分支 | guard：当前分支不是 `zhijie-` 开头时拒绝 `git commit`；拒绝 `git push` 到非 `zhijie-` 引用；拒绝 `--force`；`git push` 放 `permissions.ask` |
| 会话开始提示 | 防止在错误分支或缺 `.env` 时开工 | `SessionStart` hook：打印当前分支、`.env` 是否存在、`MIMIC_RAW_DIR` 是否存在；不阻止，只提示 |
| 减少弹窗 | 无人值守时少卡在只读命令上 | `permissions.allow`：`Bash(uv run pytest:*)`、`Bash(uv sync)`、`Bash(git status)`、`Bash(git diff:*)`、`Bash(git log:*)`、`Bash(git show:*)`、`Bash(git fetch:*)` |

## 3. 文件清单与投入

| 文件 | 内容 | 估计 |
|---|---|---|
| `.claude/settings.json` | permissions + hooks 注册 | 小 |
| `.claude/hooks/guard.py` | PreToolUse：原始目录、受保护文件、test 隔离、git 护栏 | ~150 行 |
| `.claude/hooks/stop_pytest.py` | Stop hook | ~40 行 |
| `.claude/hooks/session_start.py` | SessionStart 提示 | ~30 行 |
| `tools/freeze.py`、`data/PROTECTED.sha256`、`tests/test_protected_files.py` | L3 | ~60 行 |
| `tests/test_hooks.py` | 用构造的 hook 输入 JSON 测 guard 的放行 / 拒绝 | ~100 行 |

hook 用 `.venv` 里的 Python 直接跑（不经 `uv run`，每次调用省约 0.3 秒）。

`claude -p` 子进程在干净的空目录调用（CLAUDE.md「模型调用」），不会加载这些 hook，不影响系统里的 LLM 调用。

## 4. 怎么验

- `tests/test_hooks.py`：每条规则至少一个应拒、一个应放的用例（例：`cat "D:/project data/mimiciv/hosp/admissions.csv.gz"` 放行；`rm` 同一路径拒绝；`/d/project data/...` 写法同样拒绝；新建 `data/splits/x.csv` 放行；覆盖已存在的拒绝）。
- 实测：在会话里真的发一次被拒的 Edit / Bash，看到 hook 的拒绝信息。**原始目录的实测不对真目录做**：把 `MIMIC_RAW_DIR` 临时指向 scratch 下的假目录再试，避免 hook 出错时真的写进原始数据（硬规则 1）。
- Stop hook：故意留一个失败的测试，确认被拦一次、第二次放行并显示失败输出；再删掉。
- L0 由用户设完后，我用 `Get-Acl` 读出来确认有 Deny 条目，不做写入尝试。

## 5. 不建的代价

- 不设 L0：原始数据只靠自觉；一次误操作（例如解压到原目录、脚本写错输出路径）就违反硬规则 1，而且可能破坏 PhysioNet 原始文件的 SHA256 校验。
- 不建 L3：受保护文件被改后不会有任何信号，评估结果失去可信度，事后也查不出从哪一步开始错的。
- 不建 Stop hook：「没跑过就说已验证」只能靠自觉。

## 6. 需要用户定的

1. 同不同意整体方案；2.4 里哪些要。
2. L0 的 ACL 由你执行（我不改权限）。
3. 检索评测集放哪（建议 `knowledge/retrieval_eval/`），测试预期值是否约定放 `tests/expected/`。
4. 改受保护文件的放行方式：你手动改 / 临时环境变量，二选一或都要。
