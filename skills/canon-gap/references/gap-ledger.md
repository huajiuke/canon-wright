# 缺口台账规范

台账位于库内 `gaps/inbox.md`（实际路径以 `.canon/config.yml` 的 `paths.gaps` 为准）。它是写作侧与阅读侧唯一的交接面：写作中只追加，章末结算时集中处理。

## 字段

| 字段 | 必填 | 取值 | 说明 |
| --- | --- | --- | --- |
| `need` | 是 | 一句可检索的话 | 不要写成「了解一下明代钱法」这种无从下手的话 |
| `type` | 是 | `fact` / `craft` / `motif` | 决定它会不会过期、要不要进母题台账 |
| `why` | 是 | 章 + 段落的定位 | **写不出来就不入台账**，这是挡住弥散焦虑的闸门 |
| `granularity` | 是 | 范围目标，到章节级 | 读多少能闭合，且必须满足 30 分钟内可读完。此处只写范围意图；精确到页的定位由 M1 检索确认后再补 |
| `deadline_chapter` | 是 | 形如 `ch-009` | 最晚哪一章要用，决定优先级 |
| `status` | 是 | 见下 | |
| `created` | 是 | `YYYY-MM-DD` | |
| `chosen_direction` | `open` 时必填 | 方向代号 + 一句话 | 作者从互斥方向中选定的那个。M1 按它检索；这一栏丢了，作者的创作选择就丢了 |
| `closed_by` | `closed` 时必填 | `C-YYYYMMDD-NNN` | 闭合它的卡片 |
| `reason` | `abandoned` 时必填 | 一句话 | 为什么放弃 |

## 状态流转

```
open ──→ dispatched ──→ closed
  │
  └────→ abandoned
```

- `open`：待处理。台账里唯一的待办来源。
- `dispatched`：已派给阅读任务（M1 起）。
- `closed`：找到原文并成卡。闭合时补一行 `closed_by: C-YYYYMMDD-NNN` 指向卡片。
- `abandoned`：放弃，改用推测写法。**这是合法终态**，必须写 `reason`。放弃不是失败，是设计的一部分——留着一条永远闭合不了的缺口才是。

## 编号

`G-NNN`，三位补零，取台账中现有最大值 +1。编号只增不复用，`abandoned` 也占号。

## 示例

待处理：

```markdown
## G-003

- need: 明代私铸钱的法禁与实际流通差异
- type: fact
- why: ch-007，沈砚在市集用假钱试探那一段，「钱缘的毛刺已经磨圆了」之后需要知道当时钱法如何执行
- granularity: 第 4 章第 2 节，共约 6 页
- deadline_chapter: ch-009
- status: open
- created: 2026-09-26
- chosen_direction: A 法制史：要法条原文，确认法禁与实际执行的落差
```

放弃：

```markdown
## G-004

- need: 明代铸剑坊的工时与师承制度
- type: fact
- why: ch-008，沈砚入坊拜师那一段
- granularity: 整本书（超限，未切碎）
- deadline_chapter: ch-010
- status: abandoned
- reason: 该段改为虚写，只留一个「三年」的时间跨度，不必落实制度细节
- created: 2026-09-26
```
