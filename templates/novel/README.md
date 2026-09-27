# 小说库骨架

把本目录整个复制成你的小说库（例如 `D:\13155\my-novel`），再按需改名。

## 用途

这份骨架就是 `docs/product-constitution.md` 与 `docs/mvp-plan.md` 定义的文件约定。M2 之前，产品本体是**目录约定 + Codex 技能**，编辑器随便挑——Obsidian 可以直接打开这个目录。

## 目录

| 路径 | 用途 | 谁写 |
| --- | --- | --- |
| `manuscript/book-01/` | 章节正文，**唯一真相**，不含任何元数据 | 作者 |
| `canon/cards/` | 知识卡：原文片段 + 出处。`_template.md` 是模板，脚本按 `_` 前缀跳过 | 技能 `canon-card` |
| `canon/entities/` | 设定实体：人物 / 地点 / 器物 / 组织 | 作者 + 技能（M2 起） |
| `canon/motifs/` | 母题台账 | 作者 |
| `canon/staging/` | 暂存区：无归属卡，30 天后归档 | `cards.py sweep` |
| `gaps/inbox.md` | 缺口台账，唯一的 open 列表 | 技能 `canon-gap` |
| `gaps/archive/` | 已结算缺口 | 技能 |
| `inbox.md` | 灵感收件箱，只记不整理 | 作者 |
| `reports/` | 回检报告，每章一份 | 技能（M3 起） |
| `.canon/config.yml` | 路径与阈值 | 作者 |

## 三条硬约束

- 正文目录不放元数据，保证可读、可导出、可脱离本产品使用。
- 一次写入只落一个地方，禁止靠多份副本同步维持。
- `.canon/` 下的生成物随时可以删除重建。

## 起步

1. 复制本目录成你的小说库，`git init` 并提交。
2. 把已有章节放进 `manuscript/<book>/ch-001.md`。
3. 写完一章后召唤 `$canon-gap` 整理这一章暴露的知识缺口。
4. 落实缺口时召唤 `$canon-card`；定期运行 `python scripts/cards.py sweep` 结算暂存区（默认 dry-run，加 `--apply` 才动手）。
