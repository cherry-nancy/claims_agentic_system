# data/

项目内的数据：从 MIMIC 派生的样本和结果、数据集划分、合成病例、人工标注。原始 MIMIC 数据不放这里，它在仓库外的 `MIMIC_RAW_DIR`（见 `.env.example`），只读。

| 目录 | 内容 | 进 git |
|---|---|---|
| `sample/` | 抽样清单、处理后的病例（`CaseBundle`） | 是 |
| `splits/` | dev / test 划分（按 `subject_id`） | 是，冻结后不改 |
| `synthetic/` | 合成回归病例及预期结论 | 是，预期结论不改 |
| `gold/` | 人工标注 | 是，不改 |
| `derived/` | 大表 Parquet 子集、中间结果 | 否 |

- 本仓库是 private，协作者都持有 PhysioNet 授权，所以 MIMIC 派生数据可以提交。仓库必须保持 private。
- `splits/`、`synthetic/` 的预期结论、`gold/` 是受保护文件，规则见 `CLAUDE.md` 硬规则 3 和 7。
- 几十 MB 以上的单个文件，提交前先和大家确认。
- 能重新生成的中间结果放 `derived/`，不提交。
