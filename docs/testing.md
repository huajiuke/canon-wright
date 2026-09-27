# 怎么验证与试用

面向作者本人的手工验收清单。当前已实现 M0（缺口台账）与 M1（检索定位、卡片、暂存区归档）。

## 0. 一次性准备

**装技能。** 两个技能目前不是自动安装的，要复制到 Codex 的技能目录：

```powershell
Copy-Item -Recurse -Force "D:\13155\canon-wright\skills\canon-gap"  "$env:USERPROFILE\.codex\skills"
Copy-Item -Recurse -Force "D:\13155\canon-wright\skills\canon-card" "$env:USERPROFILE\.codex\skills"
```

装完**重启 Codex**，`$canon-gap` 与 `$canon-card` 才叫得出来。产品仓库更新后重复这一步即可（暂时没有安装机制）。

**设产品仓库位置。** 脚本在产品仓库里、不在小说库里，靠这个变量定位：

```powershell
[Environment]::SetEnvironmentVariable('CANON_WRIGHT_HOME', 'D:\13155\canon-wright', 'User')
```

**重启**之后生效。变量还没生效前，把下面命令里的 `$env:CANON_WRIGHT_HOME` 直接换成 `D:\13155\canon-wright` 即可。

## 1. 冒烟：两个脚本自检（离线，不读写任何库）

```powershell
python "$env:CANON_WRIGHT_HOME\scripts\retrieve.py" selftest
python "$env:CANON_WRIGHT_HOME\scripts\cards.py" selftest
```

期望：`retrieve.py` 25/25，`cards.py` 21/21，退出码都是 0。这两个自检覆盖检索门禁、页码与文章号判定、YAML 解析、卡片校验——**全程不联网**，所以它通过只说明逻辑没坏，不说明网络通。

## 2. 建一个测试库

```powershell
Copy-Item -Recurse "D:\13155\canon-wright\templates\novel" "D:\13155\my-novel"
cd D:\13155\my-novel
git init
git add -A
git commit -m "init novel vault"
```

把一章草稿放进 `manuscript/book-01/ch-007.md`。

## 3. 走 M0：抽缺口

在 Codex 里说：

> 用 $canon-gap 整理这一章暴露的知识缺口

期望：给出 3–7 条候选缺口，每条带 `why`（挂在哪章哪段）与 3–5 个互斥方向。**它必须停下来等你选**；若不问就自己往台账里写，说明技能没装好。

选中后检查台账：

```powershell
rg '^## G-' gaps\inbox.md
rg '^- status: open' gaps\inbox.md
```

## 4. 走 M1：检索定位（联网）

```powershell
python "$env:CANON_WRIGHT_HOME\scripts\retrieve.py" search-classic --query "錢法" --limit 3
python "$env:CANON_WRIGHT_HOME\scripts\retrieve.py" toc-classic   --title "大明會典" --limit 20
python "$env:CANON_WRIGHT_HOME\scripts\retrieve.py" locate-classic --query "大明會典 錢法" --limit 5
python "$env:CANON_WRIGHT_HOME\scripts\retrieve.py" search-paper  --query "私鑄 銅錢" --limit 5 --allow-article
```

看三件事：

- 输出 JSON 里每条都有 `id`、`locator`、`obtained`、`locator_grade`。
- stderr 出现 `dropped: ...` 行——**这是门禁在工作**，不是报错。缺定位的候选被丢掉了。
- 古籍命中带 `approx_chars`；超过 30 分钟阅读量的会被降级丢弃。

想少踩限流，先确认 `CANON_MAILTO` 已设。

## 5. 走 M1：成卡与校验

在 Codex 里说：

> 用 $canon-card 把 G-001 落实成卡片

自己手验时直接用脚本：

```powershell
python "$env:CANON_WRIGHT_HOME\scripts\cards.py" new-id --vault D:\13155\my-novel
copy canon\cards\_template.md canon\cards\C-20260927-001.md
python "$env:CANON_WRIGHT_HOME\scripts\cards.py" check --vault D:\13155\my-novel
```

**故意把 `source.locator.edition` 留空再跑一次 `check`**，应报 `缺少 source.locator.edition`。这条是「原文是资产」的守门人：没有版本，卡片里的原文日后回不到原书。

同样，把 `belongs_to` 全部留空，应报「应进暂存区」。

## 6. 走 M1：暂存区与归档

```powershell
python "$env:CANON_WRIGHT_HOME\scripts\cards.py" staging --vault D:\13155\my-novel
python "$env:CANON_WRIGHT_HOME\scripts\cards.py" sweep   --vault D:\13155\my-novel
python "$env:CANON_WRIGHT_HOME\scripts\cards.py" sweep   --vault D:\13155\my-novel --apply
```

`sweep` 默认只报告不动作，加 `--apply` 才移动与归档。

**不必等 30 天**：把暂存区某张卡的 `created` 改成一个多月前的日期，再跑 `sweep --apply`，它的 `status` 会被改写为 `archived`，`staging` 里显示负数天数。

## 7. 已知限制

- **技能不会自动更新。** 改完产品仓库要重新复制技能目录，否则跑的还是旧版。
- **现代书拿不到页码。** 目前只覆盖古籍（卷/叶）与论文（页码/文章号）。现代书的页码需人工在图书馆或数据库站内查得后回填。
- **引用率还没实现**（M2）。现在无法回答「这些卡片有多少真被写进正文」——那是产品的唯一硬指标，也是 M2 的核心。
- **回检报告还没实现**（M3）。
- **Zotero 只支持个人库、只读。** 把卡片写入 Zotero 尚未实现。