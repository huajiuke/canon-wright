# 卡片字段规范

卡片是 canon 的最小知识单元：**原文片段 + 出处 + 归属**。`scripts/cards.py check` 按本文校验。

## 字段

| 字段 | 必填 | 取值 | 说明 |
| --- | --- | --- | --- |
| `id` | 是 | `C-YYYYMMDD-NNN` | `cards.py new-id` 生成，编号只增不复用 |
| `type` | 是 | `fact` / `craft` / `motif` | 决定它会不会过期、要不要进母题台账 |
| `gap` | 否 | `G-NNN` | 由哪条缺口驱动。灵感驱动的卡可留空 |
| `segment` | 是 | 块标量 | **逐字原文**。不得改写、不得摘要 |
| `source.work` | 是 | 书名或篇名 | |
| `source.author` | 否 | 著者 | 古籍记撰人，佚名可留空 |
| `source.locator.scheme` | 是 | 见下表 | 定位制式 |
| `source.locator.edition` | 是 | 刊本 / 版次 / 卷期 | **缺此字段的卡日后无法复核** |
| `source.locator.value` | 是 | 卷/叶/页码 | 具体位置 |
| `source.obtained` | 是 | 见下 | 怎么拿到原文 |
| `belongs_to.book` | 否 | `book-01` | 四项归属至少填一个 |
| `belongs_to.chapter` | 否 | `ch-007` | |
| `belongs_to.entities` | 否 | 内联列表 | 人物 / 地点 / 器物 |
| `belongs_to.motif` | 否 | 母题名 | |
| `citations` | 否 | 列表 | 由正文引用标记统计写入，**不手填** |
| `status` | 是 | `active` / `stale` / `archived` | |
| `created` | 是 | `YYYY-MM-DD` | 暂存区超期归档据此计算 |

## locator 制式

| scheme | 用于 | value 例 |
| --- | --- | --- |
| `卷叶` | 古籍 | 卷八十一 / 第 12 叶 |
| `页码` | 现代书与期刊 | p.112-114 |
| `doi_page` | 有 DOI 的在线论文 | 10.xxxx/yyyy 第 3 节 |
| `文章号` | 不给页码的期刊 | 文章号 e202318026 |

为什么要绑定版本：古籍不同刊本卷次不同，且只有叶次（一叶两面）；现代书页码只在特定版次印次内有效。同一句原文在不同版本里位置不同，`edition` 一缺，这张卡就再也回不到原书。

## obtained 取值

`公开链接`（附 URL）、`机构订阅`、`图书馆借阅`、`人工回填`。若检索工具给不出获取方式，该候选本就不该成卡。

## status 与暂存区

```
active ──→ stale ──→ archived
   │
   └─ 无归属 ──→ canon/staging/ ──30 天──→ archived
```

- `active`：可用。暂存区的卡同样是 active——无归属本身就是负债，计入引用率分母。
- `stale`：事实层会过期，回检时发现依赖它的新章要复核。
- `archived`：已结算，不再计入引用率。

## 示例：古籍卡

```markdown
---
id: C-20260927-001
type: fact
gap: G-001
segment: |
  凡私鑄銅錢者，為首并工匠依律問罪，為從者減一等。
source:
  work: 大明會典
  author: 申時行等
  locator:
    scheme: 卷叶
    edition: 萬曆重修本（哈佛藏本）
    value: 卷之三十九
  obtained: https://zh.wikisource.org/wiki/大明會典
belongs_to:
  book: book-01
  chapter: ch-007
  entities: [沈砚]
  motif:
citations: []
status: active
created: 2026-09-27
---
```

## 示例：无归属卡（应进暂存区）

```markdown
---
id: C-20260927-002
type: craft
segment: |
  淬火之聲，水入火出，其音短促者火候足，沉悶者火已過。
source:
  work: 古今圖書集成
  locator:
    scheme: 卷叶
    edition: 清雍正銅活字本
    value: 第 22 叶
  obtained: https://zh.wikisource.org/wiki/Page:Gujin_Tushu_Jicheng
belongs_to:
  entities: []
status: active
created: 2026-09-27
---
```

这张卡 `belongs_to` 全空，`cards.py check` 会报「应进暂存区」，`sweep` 会把它移进 `canon/staging/`。写卡时就该直接落暂存区。
