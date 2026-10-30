---
name: skimreading
description: 文献速读助手（快速版）。读取 PDF/论文文本/DOI，生成中文结构化文献简报（Markdown + JSON、页码溯源、关键图表截图、Obsidian 可用嵌入、更新 skimreading_notes 索引）。适用于 10–15 分钟出稿的快速文献汇报。
---

# skimreading

## 目标与时间预算

为一篇论文产出一份自包含的文献简报文件夹，**目标 10–15 分钟完成**（25 页内的论文）。

```text
<notes-root>/{YYYYMMDDHHMM}_{NameSlug}/
├── {YYYYMMDDHHMM}.md
├── note.json
├── asset_manifest.json
└── figures/
```

`YYYYMMDDHHMM` 用实际开始解析的时间；`NameSlug` 取自论文标题，缺省用 PDF 文件名。
Markdown 文件名只保留时间戳，如 `202607212349.md`。写作语言为中文，保留原文标题、
术语和关键英文句子。

**`notes_root` 必须是用户自己的绝对路径**（如 `~/literature-reading-notes/skimreading_notes`），
不要写进技能目录或共享工作区。

### 时间预算（硬约束）

| 阶段 | 预算 |
|---|---|
| 环境检查 + prep（脚本） | ≤1 分钟 |
| 读全文（只读文本） | 3–5 分钟 |
| 核对并确认嵌入图（2–4 张） | 2–3 分钟 |
| 写 Markdown + note.json | 5–6 分钟 |
| finalize + 修错误 | ≤1 分钟 |

**决定速度的三条铁律：**

1. **文本优先**。先读 `tmp_pages/fulltext_pages.json` 全文掌握全文，**不要逐页打开 `page_XXX.png`**。
   整页渲染图只在需要核对某张嵌入图的裁切时才看。
2. **只核对要嵌入的图**。默认 2–4 张关键图。质检联系表（contact sheet）看一遍即可，
   不用为 30 张候选图逐个写 9 字段决策。
3. **一张图只分析一次**。不要在「关键图表」和「实验图」两处重复描述同一张图。

### 第四铁律：读图次数预算（实测最耗时的一步）

每次 `read_image` 都是几秒到几十秒，而 write/finalize 几乎不占时间。**单次笔记的总读图次数不得超过 8 次**，
否则必然超时。分配如下：

| 用途 | 次数 |
|---|---|
| 联系表（一次看完所有候选） | 1 |
| 逐张核对待嵌入图 | 3–5（**每张只看一次**） |
| 兜底重裁复查 | ≤2 |

反面教训（2026-10-30 实测 35 分钟仍未达标）：prep 脚本只有 6.7 秒，真正的开销是
**15 次 read_image**——公式被反复裁了 8 次、每裁一次都要重读验证。避免方式：

- **公式一律用 `scripts/crop_display_equations.py` 一次批量裁完**，它锚定公式编号行并向上扩展求和/分式的上下限，
  不再靠手工试坐标。绝不要为一条公式写一个脚本、裁一次、读一次、再调一次。
- 图片类裁剪先用脚本产出，**只在联系表里视觉筛一遍**，只对最终要嵌入的那几张逐张打开确认。
- 若某张图裁坏了，最多修一次；第二次仍不对就换一张候选图或改用整页截图，不要进入无限微调。

### 第五铁律：先跑校验器，再写正文

`check_text_quality.py` 与 `check_formula_quality.py` 的错误**全部是可以在写作时避免的**。
写完 note.json 后先跑一次 `finalize`，如果出现"raw formula-like text"或"complete formula appears in a
Markdown table"，说明写作阶段就违反了规则，当场改一次；**不要等到 finalize 之后再来回改**。

已知的书写约束（照此写，可一次通过）：

- 反引号 `` `field_name` `` 内部的下划线会被判为下标 → 字段名/文件名尽量不放反引号内，或用连字符写法。
- 表格单元格**不得**写完整公式（含 `=` 的式子）→ 单元格只写自然语言或"见公式卡片 F3"。
- 正文里的每个 `$...$` 必须成对闭合；不要出现裸 `_{i}`、`^{m}`、`X_global` 这类未包裹写法。

## 触发流程

### 1. 确定输入

- 有 PDF → 走完整流程。
- 只有粘贴文本 → 只做文本部分，明确标注缺少图表。
- 只有 DOI/链接 → 有网络则取 PDF，取不到就请用户提供 PDF。
- 扫描版无文本层 → 请用户提供 OCR 版。

只有一种模式：`standard`（文献速读汇报，比略读笔记实用，比精读笔记短）。

### 2. 跑脚本预处理

```bash
python scripts/run_lit_skim.py prep "<paper.pdf>" "<notes-root>" --name "<标题或pdf名>"
```

默认**不再渲染整页 PNG**（省 20MB+ 和大量图像读取时间）。产出：

- `tmp_pages/fulltext.txt`、`tmp_pages/fulltext_pages.json` —— 带页码的全文，主要阅读材料。
- `figures/*.png` —— 图表/公式裁切候选（DPI 220，可直接嵌入）。
- `figures/_qa_contact_sheet*.png` —— 缩略图联系表，一次看完所有候选。
- `asset_manifest.json` —— 每个资产的 `ref`/`caption`/`page`/`confidence`/`crop_quality_status`。

**公式必须单独批量裁**（自动候选常截断上下限，手工试坐标会烧掉十几次读图）：

```bash
python scripts/crop_display_equations.py "<paper.pdf>" "<note_dir>/figures" --dpi 320
```

它锚定每个公式编号行，向上合并同行与被除式/求和限所在的行，一次产出全部 `eq_<num>_p<page>.png`，
带 4pt 内边距且不牵连相邻正文。跑完后**只对要嵌入的那 2–4 条公式各看一眼**即可。

确实需要逐页看图时再加：

```bash
python scripts/extract_pdf_assets.py "<paper.pdf>" "<note_dir>" --dpi 200 --keep-pages
```

（`--keep-pages` 会渲染整页 PNG，明显变慢，非必要不要开。）

### 3. 读全文并综合

以 `fulltext_pages.json` 为主。每个关键论断必须带页码标记，如 `[p.6]` 或 `[p.6-8]`。

需要提取：

- 元数据：标题、第一作者、通讯作者、单位、期刊、DOI、年份、关键词、总页数。
- 章节地图与核心论证：背景、目标、创新、主要结论。
- **关键证据 2–4 张图/表**，每张一张卡片（截图 + 解读）。
- 关键公式——仅在概念上重要时收录；**截图优先**，能高置信转写才写 MathJax，否则只留截图和文字解释。
- 优点与不足（包括作者没提但你判断存在的问题）。
- 英文论文：写术语/翻译 QA 块。

### 4. 图片核对（只做必要的）

1. 打开 `figures/_qa_contact_sheet*.png` 一次，挑出要用的 2–4 张；
2. 对每张要嵌入的图，打开它自己的 `figures/*.png` 确认：
   - 图号、caption、页码和可见内容一致；
   - 主体完整（不截断）、caption 完整；
   - 没混进相邻图表、标题或大段正文。
3. 在 `visual_qa.asset_decisions` 里**只登记要嵌入的图**（每张 8 个字段：
   `path`/`ref`/`page`/`status`/`classification`/`caption_match`/`body_complete`/`content_clean`/`reason`）。
   其余候选资产不必登记。
4. 裁切不合格时：用 `figures/` 里的候选换一张，或从整页图重裁后再登记。

**不得**把只有文字块的裁切当图，或把图片截图当公式。生成联系表本身不等于通过视觉 QA。

### 5. 生成两份输出

Markdown 报告必须包含这 9 节：

1. `📋 文章信息`
2. `📖 基本框架`
3. `🧠 方法与创新深解`
4. `🔬 关键图表、公式与实验结果`
5. `⭐ 文章优点、不足与可信度判断`
6. `💡 可借鉴之处（1-2-5 原则）`
7. `🏷️ 个人备注`
8. `🧾 附录 A：翻译与术语 QA`
9. `🧪 附录 B：视觉 QA 与资源检查`

**1-2-5 原则（严格）**：1 个可迁移思路（100–200 字）、2 张高质量图表（各带已核验截图）、
5 个有用原句（各带页码、使用场景、好在哪）。两张图直接复用第 4 节已分析的，
在那里只写「好在哪 / 如何借鉴」，**不要重写描述**。

`🧠 方法与创新深解` 包含：问题-方法对应表、结构拆解、方法模块卡片、创新链条、
创新-证据对齐、公式直觉（如相关）、消融解读、可迁移性判断。
表格里**不写完整公式**，完整公式放独立公式卡片。

图片用标准 Markdown 嵌入（Obsidian 也认）：

```markdown
![Fig. 1: 描述](figures/figure_1_p3.png)
```

关键图表**不用总览表**，一张图一张卡片：标题 → 图片 → 内容描述 → 我的理解 →
为什么重要 → 可借鉴点 → QA 状态。

`note.json` 必须符合 `templates/note-schema.json`。不要手写伪造的 validation 字段，
`finalize` 会写入。

### 6. 校验、索引、导出 PDF、清理

```bash
python scripts/run_lit_skim.py finalize "<note_dir>" --notes-root "<notes-root>" --skill-version 3.1
```

它依次刷新联系表、跑公式质检、校验 note.json、跑文本质检、更新 `index.json`、
`glossary.json`、`pipeline_state.json`。**校验错误必须修完再汇报。**

**校验通过后必须导出 PDF**（交付物是 Markdown + PDF 两份，缺一不可）：

```bash
python scripts/export_note_pdf.py "<note_dir>"
```

脚本自动：找 `note.json` 声明的 md → 保护所有 `$...$` / `$$...$$` 不被 Markdown 吃掉 →
用本地缓存的 MathJax（首次自动下载到临时目录，之后复用）同步渲染 → Chrome 无头打印 A4 →
**打印完自动回读 PDF 检查 LaTeX 残留**，残留非零就返回 `ok: false`。

产出 `<note_dir>/<时间戳>.pdf`，并在结果里报告 `pages`、`images`、`latex_remnants`。
三项都应合理（`latex_remnants` 必须为 0）。HTML 中间文件自动删除，加 `--keep-html` 可保留排查。

遇到 `ok: false` 时看 `error` 字段：
- `MathJax did not typeset` → 本机连不上 CDN 且无缓存，手工下载 `tex-svg.js` 后用 `--cache-dir` 指定目录。
- `no Chrome/Edge binary found` → 装 Chrome 或用 `--cache-dir` 无关，需有浏览器。

最后删临时文件：

```bash
rm -rf "<note_dir>/tmp_pages"
```

保留 `asset_manifest.json`（记录图表来源）和导出的 `.pdf`。


## 边界情况

| 情况 | 处理 |
|---|---|
| 综述 | 图表当概念图/框架图看，Methods 可缺 |
| 理论/建模 | Methods 视为假设、推导、算法、证明 |
| 短文 | 明确标注章节压缩 |
| 无结论 | 从 Discussion 末段综合，标页码 |
| 只有文本 | 生成 Markdown/JSON，标注图表缺口 |
| 无可用图 | 不要伪造截图，直接说明没有可核验资产 |

## 汇报格式

不超过 20 行：论文标题、**笔记路径与 PDF 路径**、一句话发现、1-2-5 要点、校验结果、
PDF 导出的 `pages` / `images` / `latex_remnants`、视觉 QA 状态
（`pass`/`warn`/`recrop`/`unavailable`）、未解决的限制。

## 版本

- v3.2 (2026-10-30): **补齐交付物**。此前技能只产出 Markdown + JSON，PDF 是每次现写脚本
  临时做的，知识未沉淀——同样的三个坑（Markdown 吞掉 LaTeX 下标、CDN 异步 MathJax 打印时
  未完成渲染、相对图片路径失效）每次都重踩。本版把 `scripts/export_note_pdf.py` 固化进流程：
  先保护 `$...$` 与代码块再做 Markdown 转换，用本地缓存的 MathJax 同步渲染，Chrome 无头打印后
  **自动回读 PDF 校验 LaTeX 残留**。实测 MGLL 论文一次通过：15 页 / 14 图 / 残留 0。
  SKILL.md 第 6 步改为「校验、索引、导出 PDF、清理」，PDF 成为必交产物。
- v3.1 (2026-10-30): **实测整改版**。上一版把预算写成文字但没解决真正的瓶颈。
  实测一篇 40 页论文耗时 35 分钟，而 prep 脚本仅 6.7 秒——开销全在 **15 次 read_image**
  （公式被反复手工裁了 8 轮、每轮重读验证）。本版措施：
  ①新增 `scripts/crop_display_equations.py`，锚定公式编号行并向上合并求和/分式上下限，
  一次批量裁完全部编号公式，取代手工试坐标；
  ②`check_text_quality.py` 修正两处误报来源——反引号内标识符（`caption_match`、文件名）的下划线
  不再被当作下标，Markdown 表格行不再重复报公式警报（完整公式由 check_formula_quality 负责阻断）；
  实测同一篇笔记的误报警告从 11 条降为 0，省掉一整轮返工；
  ③新增「第四铁律：读图次数预算 ≤8 次」与「第五铁律：先跑校验器再写正文」，把两条硬规则写进流程。
- v3.0 (2026-10-29): **提速版**。默认不渲染整页 PNG（省 20MB+ 与大量图像读取）；
  只对要嵌入的 2–4 张图做视觉核对与 QA 登记，不再为全部 30 个候选资产逐一决策；
  取消「关键图表」与「实验图」对同一张图的重复分析，合并为单一卡片；
  加入分阶段时间预算（目标 10–15 分钟）；校验器同步放宽为只校验实际使用的资产。
- v2.7 (2026-07-30): 公式形式与视觉资产完整性成为阻断项；完整公式独立成卡片；
  嵌入图表需 `content_clean=true`。
- v2.6 (2026-07-30): 嵌入图表必须包含完整主体与完整 caption。
- v2.5 (2026-07-30): 补全实验图覆盖；联系表不得当作 QA 通过。
- v2.4-public (2026-07-29): 输出根目录可由用户配置。
- v2.4 (2026-07-23): 增加安装与使用指南。
- v2.3 (2026-07-23): 技能可独立分发；增加依赖声明与只读环境检查。
- v2.2 (2026-07-22): 更名为 skimreading。
- v2.1 (2026-07-22): 增加公式质检与术语表累积。
- v2.0 (2026-07-22): 资产抽取 v2。
- v1.x: 早期迭代（略读模式、双链 QA、联系表、时间戳目录、校验脚本等）。
