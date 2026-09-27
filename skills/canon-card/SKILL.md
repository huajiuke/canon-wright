---
name: canon-card
description: 把一条已选定方向的缺口，经检索定位后变成 canon 知识卡：交付可读完的阅读范围、验回原文片段、写卡并闭合缺口。当作者要落实某条缺口、或读到材料要入库时使用。不检索正文以外的内容、不改正文、不用摘要替代原文。
metadata:
  short-description: 缺口经检索定位后成卡
---

# Canon Card

把「缺口」推到「卡片」。这条流程横跨写作侧与阅读侧，所以每一步的归属必须清楚：机器负责定位，作者负责读与取舍。

## 前置

缺口必须已在 `gaps/inbox.md` 里，且带 `chosen_direction`。没有就先走 `$canon-gap`——方向未定就检索，等于替作者做取舍。

脚本在产品仓库里，不在小说库里。用环境变量 `CANON_WRIGHT_HOME` 定位它，不要写死路径：

```powershell
python "$env:CANON_WRIGHT_HOME\scripts\retrieve.py" ...
python "$env:CANON_WRIGHT_HOME\scripts\cards.py" ... --vault <库根>
```

没设这个变量就先问作者产品仓库在哪。

## 流程

### 1. 定位

按 `chosen_direction` 用 `retrieve.py` 检索（命令与已知坑见产品仓库的 `docs/m1-retrieval-toolchain.md`）。先粗后细：`search-classic` / `search-paper` 找候选，再用 `toc-classic`、`locate-classic`、`verify-doi` 收窄。

拿不到 `locator` 或 `obtained` 的候选**直接丢弃**，不要降级交付。宁可少给。

### 2. 交付阅读任务

一次交付**一条**（最多两三条）可读完的范围，而不是一口气抛十条。给作者四样：

- 读什么：`locator.value`，含版本
- 在哪读：`obtained`
- 读多久：`approx_chars` 或页码跨度换算
- 闭合哪个缺口：`G-NNN`

### 3. 等作者带原文回来

作者读完给你片段，才成卡。

**必须是逐字原文。** 作者给的是转述、概括或他自己的话时，明确要原文；原文确实拿不到时，宁可这张卡不做，也不要拿转述冒充原文——宪法第 2 节第 5 条。

### 4. 写卡

复制 `canon/cards/_template.md`，id 用 `python scripts/cards.py new-id` 生成，落到 `canon/cards/`。

字段定义与示例见 `references/card-schema.md`。

`locator.edition` 必填。古籍记刊本，现代书记版次，论文记期刊卷期。**缺 edition 的卡等于日后无法复核的原文**。

### 5. 校验

```bash
python "$env:CANON_WRIGHT_HOME\scripts\cards.py" check --vault <库根>
```

有问题必须修到通过，不要放过。

### 6. 闭合缺口

把台账里对应条目的 `status` 改为 `closed`，并加 `closed_by: C-YYYYMMDD-NNN` 指回卡片。台账只增不改：不删条目。

## 硬规则

- **无归属不入库。** `belongs_to` 挂不上书/章/人物/主题时，卡先落 `canon/staging/`，30 天后由 `cards.py sweep` 归档。这是设计，不是处罚。
- **不用摘要替代原文。** `segment` 是逐字片段，不是内容概括。
- **不臆造 locator。** 拿不到就丢弃；现代书的页码需人工在图书馆或数据库站内查得后回填，回填时把 `obtained` 标为 `人工回填`。
- **不抓现代版权书全文。** 现代书只做题录核验与定位，正文片段由作者从合法渠道摘录。
- **不改正文。** 正文引用标记属于作者动作。
- 一次不要堆积大量阅读任务——宪法第 7 条要的是「读完就能用上」，不是待办清单。
