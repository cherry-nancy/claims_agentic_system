# 分歧记录：原始数据的读取方式与环境

- 对应：设计第 12 节第 ① 步"环境与仓库修复"（设计 11.5）
- 我们的实现：`zhijie-20261108` @ `9e9a1ef`
- 队友：Hui Li `origin/snf-criterion-cards` @ `9ac1584`；cfeng `origin/cfeng` @ `b60f21e`
- 记录日期：2026-11-08
- 性质：这一组都是**不影响结果**的工程差异（路径、变量名、依赖），合并成一份。但两边代码要合到一起时必须统一，否则同一份代码在别人机器上读不到数据。

---

## 1. 原始数据目录从哪里读

**背景**：MIMIC 原始文件很大，不进 git，每台电脑放的位置不同（我的电脑在 `D:\project data\mimiciv`，主力电脑在 `E:\project data\AgentResearch\raw`）。代码需要一个统一的方式找到它。CLAUDE.md 规定："原始数据在仓库外，路径由 `.env` 的 `MIMIC_RAW_DIR` 指定……代码一律从这个变量读路径，不写死。"

**Hui Li 的做法**：写死在仓库内部的 `data/` 下。
```python
# origin/snf-criterion-cards:src/snf_pa/data/config.py L4-8  (b31285a)
ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data"
HOSP = DATA / "mimiciv-3.1" / "hosp"
ICU = DATA / "mimiciv-3.1" / "icu"
NOTE_FILE =DATA / "mimic-iv-note" / "note" / "discharge.csv.gz"
```

**cfeng 的做法**：读环境变量 `MIMIC_ROOT`；没设时默认是仓库里的 `physionet.org/files`；目录布局是 PhysioNet 下载器的原样结构；不读 `.env`。
```python
# origin/cfeng:src/snf_pa/data/config.py L7-11  (1c19996)
MIMIC_ROOT = Path(os.environ.get("MIMIC_ROOT", ROOT / "physionet.org" / "files"))
HOSP = MIMIC_ROOT / "mimiciv" / "3.1" / "hosp"
ICU = MIMIC_ROOT / "mimiciv" / "3.1" / "icu"
NOTE = MIMIC_ROOT / "mimic-iv-note" / "2.2" / "note"
```

**我们的做法**：`src/snf_pa/paths.py`。
- 读 `.env` 或环境变量里的 `MIMIC_RAW_DIR`。
- **没有默认值**：没设或目录不存在就直接报错。
- 目录布局是 `mimiciv-3.1/{hosp,icu}`、`mimic-iv-ed/ed`、`mimic-iv-note/note`。
- 谁定的：CLAUDE.md 规定。

**依据**：
- CLAUDE.md 的规定。
- 没有默认值，是为了避免数据放错位置时代码静默读到别的东西或空目录（CLAUDE.md 硬规则 4"缺失就是缺失"）。

**对结果的影响**：无。只影响"能不能在某台电脑上跑起来"。

**建议 / 待讨论**：
- 三人统一用一个变量名和一种目录布局。我们这边按 CLAUDE.md 用 `MIMIC_RAW_DIR` 加上面的布局。
- 如果队友更习惯 PhysioNet 原样布局（`mimiciv/3.1/...`），可以讨论让 `paths.py` 两种布局都认。

---

## 2. `.csv` 还是 `.csv.gz`

**背景**：PhysioNet 发布的是 `.csv.gz`。设计文档 v7 原来写"文件是未压缩的 `.csv`"（主力电脑上解压过），我这台电脑上是 `.csv.gz`。

**两位队友**：都只读 `.csv.gz`，文件名写死在 SQL 里。例如 Hui Li 的 `cohort.py` L44、L49、L51，cfeng 的 `cohort.py` L46、L57–58。

**我们的做法**：
- `raw_table("mimiciv-3.1/hosp/admissions")` 先找 `.csv`，没有再找 `.csv.gz`。
- 设计文档 3.1 和 11.5 已改成两种都支持。
- 谁定的：用户决定（2026-11-08）。

**对结果的影响**：无。DuckDB 读两种格式结果相同；只是 `.csv.gz` 不能并行读，大表更慢。

**建议**：队友的 SQL 改用 `raw_table()`，就能在解压过的主力电脑上直接跑。

---

## 3. Python 版本与依赖

**背景**：两台电脑、三个人的环境要一致，`uv.lock` 才有意义。

**队友**：两人都没有 `.python-version`，`pyproject.toml` 是 `requires-python = ">=3.12"`。
- Hui Li 加了 `pandas`、`scikit-learn`（`84832e0`）。
- cfeng 保留了 `chromadb`（`origin/cfeng:pyproject.toml` L7），另加 3 项依赖。

**我们的做法**：
- `.python-version` 固定为 3.11，`requires-python = ">=3.11"`。用户决定（2026-11-08）。
- 删掉 `chromadb`。设计 11.5：索引在内存里，用不上。
- 加了 hatchling build-system，让 `uv sync` 把 `snf_pa` 装成可编辑包。不加的话，检查脚本 import 不到 `snf_pa`。

**对结果的影响**：
- 无直接影响。
- 注意：`uv.lock` 在 3.11 和 3.12+ 上会解析出不同的 numpy 版本（2.4.6 / 2.5.4）。不固定 Python 版本，两台电脑跑的库就不一样。

**建议 / 待讨论**：
- 三人统一 Python 3.11。
- 队友代码要用的 `pandas`、`scikit-learn` 等，在我们采用对应代码时再加。

---

## 4. `tests/test_sample.py`

**背景**：这个测试来自最早的 `snf-prior-auth`（`8202079`），检查的是旧方案的 300 例样本。它 import `snf_pa.data.config`，而这个模块只在队友分支里有，所以我们分支上 pytest 一收集就报错。

**Hui Li**：在 `snf-criterion-cards` 上补了 `config.py`，让它能 import；样本也在那个分支上生成了。

**cfeng**：有自己的 `config.py`（字段不同）。

**我们的做法**：
- 只把 import 改成 `pytest.importorskip(...)`，**断言一个字没动**。
- 样本不存在时整个文件跳过。
- 谁定的：用户决定（选项 A）。

**依据**：
- 测试的预期值受保护（CLAUDE.md 硬规则 7）。
- 它断言的抽样方案（5 个诊断类别 × 60 例、排除观察期、午夜数 ≥3、test 占 38–46%）与设计 3.2 / 10.1 不一致，见 `reports/teammate_diff_cohort.md`。

**对结果的影响**：现在无影响。第 ② 步按设计重新抽样后，这个测试要么按新方案重写（需要用户同意），要么删除。

**待讨论**：这个测试最终的去留，和抽样方案一起定。
