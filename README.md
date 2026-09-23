<div align="center">

# PDF Translation

**把英文文献翻译成排版精美的中文 PDF**

公式重排、图片归位、表格重建、脚注可跳转 —— 不是把 PDF 转成文本再翻译，而是**重建一份中文版面**

[![Claude Code](https://img.shields.io/badge/Claude%20Code-Skill-d97757)](https://claude.com/claude-code)
[![Codex](https://img.shields.io/badge/Codex-Skill-000000)](https://openai.com/codex)
[![DSH](https://img.shields.io/badge/DSH-Skill-1f4e79)](https://github.com/deepseek-ai)
[![Pi](https://img.shields.io/badge/Pi-Skill-6b4fbb)](https://github.com/badlogic/pi)
[![License](https://img.shields.io/badge/License-MIT-2ea44f)](LICENSE)

[English](README.en.md) · 中文

</div>

---

## 能做什么

这是一个 **Agent Skill**。它不绑定任何特定的 agent 平台 —— 只要你的 agent 能读到 `SKILL.md`、能跑 Python 和 Chrome，就能用它。安装好后输入一句「翻译这篇 PDF」，它就会自动生成一份经过重新排版的**中文文献稿**。

已验证可用：**Claude Code**、**Codex**、**DSH**、**Pi**（安装路径见[安装](#安装)）。Cursor、Cline、Gemini CLI 等任何读 `SKILL.md` 的 agent 同样适用。

我调研了社区中现有的 PDF 翻译方案，目前，大多数 PDF 翻译方案主要采用两类思路：一种是先解析并提取 PDF 中的文本内容，完成翻译后再根据原始信息重新生成文档；另一种则是在尽可能保留原始 PDF 结构的基础上进行翻译，例如 BabelDOC 所采用的方案。无论采用哪种方式，核心挑战都并不在于翻译本身——借助大语言模型已经能够实现较高质量的文本翻译，真正困难的是**如何准确理解 PDF 中复杂的文档结构，并在翻译后实现高质量的排版重构**。

在实际应用中，PDF 中的公式、图片、表格、超链接、脚注以及复杂的版面布局都给解析与重排带来了挑战。因此，现有方案仍可能出现公式渲染异常、图表位置偏移、排版效果不佳、链接跳转失效以及脚注显示异常等问题。这些问题也是我在翻译和阅读学术文献过程中长期遇到的痛点，我相信也困扰着许多科研人员和技术学习者。

本 Agent Skill 致力于解决这些 PDF 翻译中的排版问题，其中一个核心设计是使用 **KaTeX 对数学公式进行重新排版**。生成的公式采用真正的矢量字体渲染（如 `KaTeX_Math-Italic`、`KaTeX_Size2-Regular` 等字体子集），因此具备良好的缩放能力、对齐效果和打印质量。目前，社区中尚未发现采用类似方案的开源 PDF 翻译工具。

---

## 效果

### 1. 修复原文的文字重叠

有些 PDF（尤其是排版引擎生成的）文字层会互相叠在一起，直接提取出来是一团乱码。工具会按字形位置重新归位。

<img src="docs/images/01-text-overlap.png" width="100%" alt="文字重叠">

### 2. 图片：按原文的跨栏方式归位

原文里跨两栏的图（(a) 在左栏、(b) 在右栏、题注横跨），译文里**照样跨两栏**，两个子图各占一栏 —— 而不是缩成半宽塞进一栏。题注也逐句翻译。

<img src="docs/images/02-figure.png" width="100%" alt="图片翻译与排版">

### 3. 表格：重建单元格，不是截图

原文是**矢量轮廓**的表格（文字层是空的）也能重建。表头、对齐、跨栏与否都按原文来。

<table>
<tr><th>原文</th><th>译文</th></tr>
<tr>
<td><img src="docs/images/03-table-source.png" alt="表格原文"></td>
<td><img src="docs/images/04-table-zh.png" alt="表格译文"></td>
</tr>
</table>

### 4. 标题：中英对照，层级照旧

标题保留英文原题，中文为主、英文为辅，字号与层级关系按原文还原。

<table>
<tr><th>原文</th><th>译文</th></tr>
<tr>
<td><img src="docs/images/06-heading-source.png" alt="标题原文"></td>
<td><img src="docs/images/05-heading-zh.png" alt="标题译文"></td>
</tr>
</table>

### 5. 公式：重新排版，不是裁图

绝大多数公式能**逐符号还原**，包括多层上下标、大型运算符、分式与定界符。

<table>
<tr><th>原文</th><th>译文</th></tr>
<tr>
<td><img src="docs/images/07-formula-source.png" alt="公式原文"></td>
<td><img src="docs/images/08-formula-zh.png" alt="公式译文"></td>
</tr>
</table>

复杂的嵌套公式会有**字符与断行上的差异** —— 比如根号内的括号层级、换行位置 —— 但数学含义不变，不影响阅读。

<table>
<tr><th>原文</th><th>译文</th></tr>
<tr>
<td><img src="docs/images/10-formula-complex-source.png" alt="复杂公式原文"></td>
<td><img src="docs/images/09-formula-complex-zh.png" alt="复杂公式译文"></td>
</tr>
</table>

### 6. 脚注：翻译 + 双向跳转

原文把脚注排在引用页页脚，译文集中放在文末（Chrome 的 CSS 至今没有实现 `float: footnote`，无法做到真正的页脚脚注）。但**点击正文的上标可以跳到脚注，点击脚注末尾的 ↩ 可以跳回正文**。

<img src="docs/images/11-footnotes.png" width="100%" alt="脚注">

### 7. 保留原文的引用跳转

正文里的 `[n]` 全部变成可点击链接，指向文末对应的参考文献条目。鼠标悬停即可预览。

<img src="docs/images/12-citation-link.png" width="100%" alt="引用跳转">

### 8. 参考文献不翻译

作者名、刊名、卷期、DOI 是**书目数据**，翻译会破坏可检索性与 CrossRef 匹配。所以原样提取、重新排版、单独成页。

<img src="docs/images/13-references.png" width="100%" alt="参考文献">

### 9. 标题与摘要

<img src="docs/images/14-title-abstract.png" width="100%" alt="标题与摘要">

---

## 工作原理

六个阶段，前三个和第六个是脚本，中间是模型自己的活。

```
0. ask        → 先问你：只要 Markdown，还是要排版好的 PDF？报出预估 token 与耗时
1. probe      → 这个 PDF 有文字层吗？哪些页需要 OCR？
2. extract    → 逐页取出文本块 + 坐标 + 字体字号，图片按 300 dpi 裁出
3. classify   → 哪些片段是公式，哪些块是标题 / 代码 / 题注
4. translate  → 模型写中文，产出结构化的正文文件
5. verify     → fidelity.py：有没有漏句、有没有把题注写成摘要
6. typeset    → HTML + KaTeX → headless Chrome → PDF，再盖章页眉页脚
```

选「只要 Markdown」的话，跑完第 5 步就结束，跳过整个排版环节 —— **成本大约只有四分之一**。

### 为什么是 HTML + CSS，不是 LaTeX

设计迭代就是改一行 CSS，几秒钟出结果；LaTeX 要先装 MiKTeX。中日韩断行和字体回退交给浏览器处理，比 xeCJK 省事。LaTeX 适合你自己从零写一篇数学密集的文档；这里做的是**重建别人已经排好的版面**，CSS 是更便宜的工具。

---

## 安装

### 前置条件

| 依赖 | 说明 |
|---|---|
| **宿主 agent** | 任何支持 Agent Skill 的平台 —— Claude Code、Codex、DSH、Pi 等。**翻译由 agent 自己的模型完成，skill 不需要 API key** |
| **Python 3.9+** | 需要 `pymupdf`：`pip install pymupdf` |
| **Node.js + npm** | 首次运行时在临时目录装一份 KaTeX（之后离线可用） |
| **Chrome 或 Edge** | 用来打印 PDF。装在标准路径即可，否则设 `CHROME_PATH` 环境变量 |
| **中文字体** | 正文 `STSong` / `SimSun`，标题 `Microsoft YaHei`（Windows 自带；macOS/Linux 见下方 FAQ） |

### 装 skill

把仓库放进 agent 的 skill 目录。各平台的路径不同，选你用的那个：

```bash
git clone https://github.com/DFBlowing/pdf-translation.git

# Claude Code
cp -r pdf-translation ~/.claude/skills/

# Codex
cp -r pdf-translation ~/.codex/skills/

# DSH
cp -r pdf-translation ~/.dsh/skills/

# Pi
cp -r pdf-translation ~/.pi/agent/skills/
```

用别的 agent 就把 `pdf-translation` 整个目录放到它的 skill 目录下 —— skill 本身没有任何平台相关的代码。
（也可以用软链接代替复制，方便以后 `git pull` 更新。）

然后在会话里说「翻译这篇 PDF」即可触发；也可以直接 `/pdf-translation`。

---

## 使用

### 它会先问你三个问题

1. **在动手之前**，它会先量一遍你的文档，询问你是选择只翻译出 Markdown 还是翻译为排版好的 PDF：

`estimate.py` 会根据页数、英文词数、编号公式数估算 token 与耗时。**它的系数来自两个案例的实测**，不是拍脑袋：

| 参考案例 | 规模 | 实测产出 token | 实测耗时 |
|---|---|---|---|
| IEEE TWC 2026（公式密集） | 14 页 / 9,652 词 / 72 式 | 42k – 62k | 11 – 18 分钟 |
| **Stanford CS231n 讲义**（纯文字 + 代码） | **191 页 / 50,529 词 / 80 图** | **222k**（实测值） | **约 29 分钟**（实测值） |

**这里有一条容易被忽略的事实：成本的主导项不是译文长度，而是「轮次 × 上下文大小」。**

CS231n 那次翻译的总消耗里，**绝大部分是缓存读** —— 13 个并行子 agent 各自反复读自己的上下文。所以页数翻倍远不止 token 翻倍；而把文档拆成并行批次，能在总 token 基本不变的前提下把墙钟时间压掉一大截。上面那个 29 分钟走的就是并行路线，串行单 agent 会明显更慢（`estimate.py` 会同时给出两个口径）。

> 顺带一提：`estimate.py` 的第一版把系数标错了 —— 每页耗时是从参考案例的**全程**反推的，而那次全程包含 9 轮用户反馈。拿"含返工的时长"外推新文档，会得出「191 页 = 6–11 小时」这种结论。现在把**干净首轮**和**每轮返工**分开算了。

2. 如果你选择翻译 PDF，它会询问你是**正文**是选择单栏排版还是双栏排版？

3. 如果你选择翻译 PDF，它会询问你是**图表**是使用单栏排版还是双栏排版。

问题 2 和问题 3 决定了 CSS 架构、图片标记方式和公式越界判据，事后返工要重跑整个流程。

如果原文是双栏期刊（IEEE / ACM / Elsevier），skill 会去读 `references/two-column-paper.md` —— 里面有实测的栏几何、逐段分栏架构、越界判据及其两个已经踩过的坑、图片与表格的跨栏规则。

### 使用条件

**适合：**

- 有**文字层**的学术 PDF（期刊论文、会议论文、讲义、教材）
- 单栏或双栏排版
- 公式、图片、表格、参考文献、脚注

**不适合：**

- **扫描件 / 影印本** —— 没有文字层，需要先做 OCR（工具会明确告诉你）
- 公式本身是**图片**的文档（老论文扫描版常见）
- 图文混排的杂志、手写体、竖排文字

---

## 常见问题

### 需要配置 API key 吗？

**这个 skill 本身不需要任何 key。**

翻译是**宿主 agent 用它自己的模型**做的 —— key 配在 agent 里，不在 skill 里。你只要保证你的 agent 能正常对话，就能用它。skill 里没有任何 API key 配置项，也没有需要你填的密钥字段。

需要配置的只有几个**可选项**：

```bash
# 可选：Chrome 不在标准路径时
export CHROME_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# 可选：macOS / Linux 上的中文字体（见下一条）
export PDF_TRANSLATION_SERIF="Songti SC"          # 正文
export PDF_TRANSLATION_SANS="PingFang SC"         # 标题
```

### macOS / Linux 上的中文字体
（未经测试，我使用的是 Windows 系统。）
默认字体名是 Windows 的 `STSong` / `SimSun`（正文）和 `Microsoft YaHei`（标题）。其他平台用上面两个环境变量覆盖即可，**不需要改代码**：

| 平台 | `PDF_TRANSLATION_SERIF` | `PDF_TRANSLATION_SANS` |
|---|---|---|
| Windows | `STSong`（默认） | `Microsoft YaHei`（默认） |
| macOS | `Songti SC` | `PingFang SC` |
| Linux | `Noto Serif CJK SC` | `Noto Sans CJK SC` |

页眉页脚是脚本用 PyMuPDF 盖的章（不走 Chrome），所以它需要一个**字体文件**而不是字体名。脚本会自动探测常见路径，也可以用 `PDF_TRANSLATION_FONT_DIR` 指定目录。

### 为什么脚注不放在页面底部？

Chrome 至今**没有实现** CSS GCPM 的 `float: footnote`（`position: running()` 只管页边元素）。用单向 HTML 流模拟会遇到「引用点位置随分页变化」的循环依赖，只能多轮渲染逼近，非常脆弱。所以脚注集中在文末，用**双向跳转**补上体验。真要贴页得换 LaTeX 重排，那是另一条技术栈。

### 公式会不会排错？

绝大多数不会。复杂嵌套公式可能有字符或断行上的差异（见上文第 5 条）。**但比「拍平成 Unicode」和「裁成图片」好得多** —— 那两种做法是必然出错，不是可能出错。

---

## 目录结构

```
pdf-translation/
├── SKILL.md                        主流程与设计决策
├── references/
│   └── two-column-paper.md         双栏期刊版式：栏几何、分栏架构、越界判据
├── scripts/
│   ├── estimate.py                 阶段 0 — token 与耗时预估
│   ├── probe.py                    阶段 1 — 页数/块数/字号直方图
│   ├── extract.py                  阶段 2 — structure.json + 300dpi 图片
│   ├── classify.py                 阶段 3 — 公式片段 + 标题层级
│   ├── fidelity.py                 阶段 5 — 漏译/未译/题注闸门
│   ├── typeset.py                  阶段 6 — HTML + KaTeX + Chrome → PDF
│   └── compare.py                  对比任意两份 PDF
└── docs/images/                    README 用的效果图
```

---

## 已知限制

- **公式密集的文档要多轮迭代。** 修好一批公式后分页会变，可能暴露新的越界，所以要循环到收敛。这是工具会如实汇报成本的原因。
- **分栏的末页可能参差。** Chrome 对含高不可分割块的多页分栏段不做末页均衡，CSS 层面无解。彻底解决要换 LaTeX 重排。
- **脚注无法贴页**（见 FAQ）。
- **页眉页脚是脚本盖的章**，不是原文版面。

---

## 翻译案例

两个**排版效果演示**（原文 + 中文译文对照），用来直观说明这个 skill 能做出什么样的版面：

| 案例 | 规模 | 重点 |
|---|---|---|
| **Disco 论文**（IEEE 双栏） | 14 页 → 译文 18 页 · 73 个公式 | 公式全部 KaTeX 重排、越栏判据、`[n]` 双向跳转 |
| **Stanford CS231n 讲义** | 191 页 → 译文 158 页 · 80 图 | 13 个并行批次（实测约 29 分钟）、代码原样保留 |

文件较大（合计约 36 MB），所以**不放进仓库**，挂在 Release 上：

**[⬇ 下载两个案例](https://github.com/DFBlowing/pdf-translation/releases/tag/cases-v1)** · 细节见 [`docs/cases/`](docs/cases/README.md)

> CS231n 那份源文件本身有缺陷：代码框用了 `overflow: hidden`，**146 行代码在原文里就被截断了**，缺失字符在 PDF 里不存在。译文照原样保留并逐处标注（58 条，覆盖 146 行）。

---

## 版权声明

本仓库**只包含工具代码，不包含任何论文原文或译文**。

案例目录（Release 附件）中的 **原文**著作权归原作者及出版方所有（Disco 论文 © IEEE；CS231n 讲义 © Stanford Vision Lab）；**译文**由本工具自动生成，仅供学习、研究与技术演示，不得商用。本仓库不主张对它们的任何权利，也不从中获利。

**如果这些文件侵犯了您的权利，请提交 [Issue](https://github.com/DFBlowing/pdf-translation/issues) 或邮件至 zzdf176@gmail.com，我会在第一时间删除，非常抱歉。**

---

## License

[MIT](LICENSE)

效果图来自 IEEE TWC 2026 的一篇公开论文，仅用于演示排版能力。
