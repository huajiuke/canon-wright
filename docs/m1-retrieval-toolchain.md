# M1 检索工具链（v0.1）

> 上游依据：`docs/product-constitution.md` 第 6 节、`docs/mvp-plan.md` 第 6 节 M1。
> 状态：**已实测可用**。范围限定为**古籍与论文**——这两类能全自动定位到卷/叶/页码；现代书的页码级定位留待后续迭代。

## 0. 一句话

单入口 `scripts/retrieve.py`，只用标准库。每个候选必须同时具备 `id`（可验证标识）、`locator`（定位）、`obtained`（获取方式），缺任何一项即被丢弃并在 stderr 报告原因——这是宪法第 6 节的机械落实，不是提示词里的建议。

## 1. 实测可达性

以下全部是 2026-09-27 在本机实测的结果，不是推断。

| 源 | 用途 | 状态 |
| --- | --- | --- |
| `api.openalex.org` | 论文发现，**页码级** | 可用，需 `mailto` 进 polite pool，突发会 429 |
| `api.crossref.org` | DOI 核验 | 可用，中文相关度差，定位为核验器 |
| `zh.wikisource.org/w/api.php` | 古籍全文、卷目录、**扫描叶次** | 可用，无需鉴权 |
| `api.zotero.org` | 书目库 | 可用，需 API key |
| `export.arxiv.org` | 预印本 | 可用 |
| `guoxuedashi.net` | 古籍全文 | 可达，抓取备用 |

不可达：

| 源 | 后果 |
| --- | --- |
| `archive.org`、`hathitrust.org` | **页码级全文检索最好的两个工具都不可用** |
| `googleapis.com/books`、`openlibrary.org` | 书目核验少一条退路 |
| `api.ctext.org` | 返回 `ERR_REQUIRES_AUTHENTICATION`，需 API key，本轮不启用 |
| `opac.nlc.cn`、`read.nlc.cn`、`find.nlc.cn` | 国图线上下线 |
| `ucdrs.superlib.net` | 参考咨询联盟不可用 |

可达但付费或需登录：`duxiu.com`、`wanfangdata.com.cn`、`cqvip.com`、`kns.cnki.net`。这几家**没有公开 API**，只能人工在站内检索。

**根因**：页码级全文检索最好用的 Internet Archive 与 HathiTrust 都不可达，而中文图书全文检索最强的读秀需要登录。这就是「现代书页码级定位必须人工回填」的由来——不是偷懒，是没有可自动化的通路。

## 2. 三类定位粒度

| 类型 | 定位粒度 | 来源 | 自动化 |
| --- | --- | --- | --- |
| 论文 | 页码 | OpenAlex `biblio.first_page/last_page`、Crossref `page` | 全自动 |
| 古籍 | 卷/门类 + 叶次 | Wikisource 子页面 + `Page:` 命名空间扫描页 | 全自动 |
| 现代书 | 页码 | 读秀/图书馆，需登录 | **需人工回填** |

古籍实测例：《大明會典》在 Wikisource 有卷级子页面（`大明會典/卷之三十九 廩祿二 俸給 廩給 行糧馬草`），哈佛藏本扫描页提供叶次（`Page:Harvard drs 428230936 大明會典 v.61.pdf/2`）。卷、门类、叶次三级都能拿到。

## 3. locator 必须绑定版本

宪法第 4 节写的 `source.locator: 第 3 章第 2 节 / p.112-114` 对古籍是错的，必须修正为带 scheme 的结构：

```
locator:
  scheme: 卷叶 | 页码 | doi_page
  edition: 万历重修本 | 哈佛藏本 | 中华书局 2007 年第 3 版
  value: 卷之三十九 / 第 12 叶
```

理由：

- 古籍不同刊本卷次不同，且只有叶次（一叶两面），没有页码。
- 现代书页码只在特定版次印次内有效。
- **`edition` 缺失即意味着这条「原文」日后无法复核**，直接违反宪法第 2 节第 5 条「原文是资产」。所以 `edition` 与 `locator` 同级必填。

## 4. 命令清单

```bash
python scripts/retrieve.py selftest                     # 离线自检，不联网
python scripts/retrieve.py search-paper  --query "..." [--lang zh] [--year-from 2000] [--limit 8] [--allow-article]
python scripts/retrieve.py verify-doi    --doi 10.xxxx/yyyy [--allow-article]
python scripts/retrieve.py search-classic --query "錢法" [--limit 8]
python scripts/retrieve.py locate-classic --query "古今圖書集成 錢法" [--limit 5]
python scripts/retrieve.py toc-classic   --title "大明會典" [--limit 200]
python scripts/retrieve.py zotero-check
python scripts/retrieve.py zotero-find-doi --doi 10.xxxx/yyyy
```

每个子命令都接受 `--out FILE`，把结果以 UTF-8 写入文件。**模型应当始终用 `--out`**：PowerShell 管道会把中文输出破坏成 `?`，写文件可绕开。

`toc-classic` 是唯一的例外：它输出**导航目录**而非候选，因此不走门禁（否则整卷体积超限会被全部丢弃，命令就没用了）。从目录里挑中的卷，仍需回到 `search-classic` 或 `locate-classic` 过一遍可读完检查，才能作为阅读任务交付。

## 5. 环境变量

| 变量 | 用途 | 必需性 |
| --- | --- | --- |
| `CANON_WRIGHT_HOME` | 产品仓库根目录，脚本按它定位 | 技能运行脚本时必需 |
| `CANON_MAILTO` | 进 Crossref / OpenAlex 的 polite pool，显著降低 429 | 强烈建议 |
| `ZOTERO_API_KEY` | Zotero API 访问权限（当前只需只读） | 用 Zotero 时必需 |
| `ZOTERO_LIBRARY_ID` | Zotero 数字用户 ID | 用 Zotero 时必需 |

密钥只走环境变量，不写进 `config.yml`（该文件在库里，会被提交）。

获取 Zotero 两项凭据（同一页）：

1. 打开 https://www.zotero.org/settings/keys —— 页面顶部 `Your userID for use in API calls is ...` 的数字即 `ZOTERO_LIBRARY_ID`。
2. `Create new private key` → 勾 `Personal Library` 下的 `Allow library access`。写入权限等卡片写入落地后再开（编辑同一个 key 即可，不必新建）。
3. 保存时显示的 key 即 `ZOTERO_API_KEY`，**只显示这一次**。

**注意**：userID 不是用户名，同名会 404；当前只支持个人库（`/users/{id}`），群组库未支持。

写入用户级环境变量（PowerShell）：

```powershell
[Environment]::SetEnvironmentVariable('ZOTERO_LIBRARY_ID', '21849729', 'User')
[Environment]::SetEnvironmentVariable('ZOTERO_API_KEY', '<key>', 'User')
[Environment]::SetEnvironmentVariable('CANON_MAILTO', '<邮箱>', 'User')
```

**设完必须重启 Codex**：已经在跑的进程读不到新变量，`zotero-check` 会继续报缺变量。已实测确认这一点。

自检：`python scripts/retrieve.py zotero-check` 应返回 `status: ok`；`sample: false` 只表示该库当前没有任何条目。

## 6. 门禁与可读完原则

`locator_grade` 五级，等级不够即丢弃：

| 等级 | 含义 | 例 |
| --- | --- | --- |
| `leaf` | 叶次 | 第 12 叶 |
| `page` | 页码 | 页码 189-192 |
| `article` | 整篇：期刊只给文章号或未收录页码，整篇即阅读单元 | 文章号 e202318026 |
| `volume` | 卷/门类/篇 | 卷之三十九 |
| `coarse` | 定位不足以直接去读 | 体积未知的古籍页 |

最低门槛：论文 `page`，古籍 `volume`。

`article` 默认**不通过**：整篇可能是 30 页，无从判断是否可读完。要让流程接受整篇，需显式加 `--allow-article`——把「这篇我想整篇读」的判断权交回作者，而不是工具默认放宽（宪法第 2 节第 4 条：AI 不做取舍）。

宪法第 2 节第 7 条的「30 分钟可读完」也在这里机械落实：`READABLE_BYTES = 12000`（文言文按 30 分钟约 4000 字估算）。古籍命中页体积超限即降为 `coarse` 被丢弃，逼着流程用 `toc-classic` 继续收窄到门类。实测《錢法論》（856 字）通过，《錢氏私志》（过长）被丢弃。

## 7. 已知精度问题

**检索式质量决定结果质量。** 实测用 `明代 钱法` 查 OpenAlex，返回的是铀矿床论文与虚拟货币洗钱论文——古代钱法与当代货币被混在一起，相关性很差。这不是 bug，是这些索引对文言与专门史的语义不敏感。

**期刊页码正在消失。** 不少期刊不给页码、只给文章号（实测 `e202318026`、`9140057`），Heritage Science 这类连 Crossref 都没有 `page` 字段。所以「页码级」对相当一部分论文根本不存在，`article` 等级就是为它们设的。文章号必须与真页码区分：把 `e202318026` 当页码会让 `pages` 谎报成 1 页，而文章号只说明「整篇」、不说明长度。`classify_page()` 负责这个判定。

因此 M1 的模型步骤（把缺口转成检索式）很关键，要点：

- 用**专名**而非主题词：`私鑄`、`銅錢`、`寶鈔`、`大明會典` 优于「钱法研究」。
- 加**年代与文献类型**过滤（`--year-from`、`--lang`）。
- 先 `toc-classic` 定卷，再 `locate-classic` 定叶，不要一步到位。
- 结果相关度低时**宁可少给**，不要凑数交付（宪法第 6 节）。

## 8. 运维

单入口是刻意的：白名单只需一条前缀规则即可覆盖全部检索能力，不必每跑一个缺口点一次同意。

```
prefix_rule: ["python", "scripts\\retrieve.py"]
```

脚本内置每主机限速与 429 指数退避，所以把 `--limit` 开大不会把自己打死。

## 9. 明确不做

- **不抓现代版权书全文**。现代书只做题录核验与定位；正文片段必须由作者从合法获取的渠道自行摘录。工具代抓即越界。
- 不启用需鉴权或付费的源（ctext、读秀、CNKI、万方、维普）。
- **不臆造 locator**。拿不到就丢弃，宁可少给。
