# 中文扫描书 OCR 工具箱 · Chinese Scanned-Book OCR Toolkit

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org)
[![Agent Skill](https://img.shields.io/badge/Agent-Skill-blueviolet.svg)](SKILL.md)
[![OCR](https://img.shields.io/badge/OCR-GLM--4.5V%20%7C%20tesseract-orange.svg)](docs/pipeline.md)

**把没有文字层的扫描书变成可信的 Markdown——从现代排版书到密集竖排木刻古籍。**

**Turn scanned books with no text layer into Markdown you can trust — modern typeset pages to dense vertical woodblock prints.**

这里的每一条规则都是用返工换来的：数千页真实生产运行里踩过的坑，全部固化进了脚本，和下面那张表。

---

## 给谁用 / Who this is for

- **做古籍数字化的人**：手上是扫描件或木刻影印本，OCR 软件要么读不出，要么读出通篇自信的胡说
- **研究者与编辑**：要把竖排文言变成可检索、可引用、可校对的文本
- **翻译与整理团队**：需要一个能重复跑的流程，而不是每次手工救火
- **跑 agent 的人**：这是个能交给 AI 执行的 skill（见 [`SKILL.md`](SKILL.md)），不是一堆要你背下来的命令

不适合：单张发票、截图、现代商务文档的快速 OCR——那种活有更轻的工具。

*For anyone digitizing classical Chinese books; researchers and editors turning vertical classical text into searchable, checkable text; translation teams needing a repeatable pipeline. Not for one-off screenshots or modern business documents — lighter tools exist.*

---

## 60 秒上手 / Quick start

**第一步：不花一分钱、不需要任何 key，先试拆分器。**
木刻影印本常是左右双页合排，这一步决定后面所有页的编号对不对：

```bash
python3 tools/split_double_pages.py <源PDF目录> <输出目录>    # 输出 p0000_left.jpg / p0000_right.jpg
python3 tools/split_double_pages.py <源> <出> --dry-run       # 只预览不落盘
python3 tools/split_double_pages.py --vol VOL-01              # 单选一卷
```

**第二步：视觉模型 OCR**（需要 SiliconFlow API key，模型 GLM-4.5V）：

```bash
export SILICONFLOW_API_KEY=sk-xxx
export OCR_PAGES_DIR=~/my_book/pages     # 一卷一个子目录，目录里放单页 jpg
export OCR_OUTPUT_DIR=~/my_book/out
python3 tools/ocr_vlm_batch.py --vol VOL-01 --limit 5   # 先试 5 页
python3 tools/ocr_vlm_batch.py --vol VOL-01             # 整卷，断点续传
```

产出：`$OCR_OUTPUT_DIR/VOL-01.md`（逐页带页码标记），另有 `_ocr.log` 与 `_progress.json`。
中断了直接重跑同一条命令，已完成的页会跳过。

**第三步：清洗与补漏。**

```bash
python3 tools/clean_md.py                     # 先改脚本顶部配置区，再运行
python3 tools/fix_hallucinations.py 243,251   # 对质检不合格的页重跑，只有过闸才落盘
```

**完全离线的路**（不调任何 API，tesseract + PyMuPDF）：`tools/ocr_single.py` 单册 worker + `tools/ocr_batch_v5.sh` 调度器（`./ocr_batch_v5.sh [起始序号] [数量] [超时秒数]`）。

---

## 装成 Agent Skill / Use it as an agent skill

仓库根目录有 [`SKILL.md`](SKILL.md)——把这个目录放进你的 agent skills 目录（Claude Code、Hermes，或任何会读 `SKILL.md` 的 agent），然后直接给它一本书：

> 按这个 skill 把这套扫描件转成 Markdown

它会自己走「拆分 → 按页型选模型 → 过幻觉闸 → 清洗 → 对着原图核对」这套流程。

说句实在话：这就是这份文档的正确用法——**交给 AI 去执行，而不是你自己背下来。**

*Drop the folder into your agent's skills directory and hand it a book. The honest use is exactly that: let the agent run the workflow, instead of memorizing it yourself.*

---

## 它撞的是什么墙 / Why plain converters fail

大多数 OCR 教程止步于"对图片跑 tesseract"。真实的扫描书会撞上它们从不提及的墙：

- **MuPDF 在损坏 PDF 上永久卡死**——卡在 C 层 syscall，signal 打不进去，`multiprocessing.terminate()` 也救不了
- **视觉模型 OCR 会幻觉**——单字复读、n-gram 循环、输出乱码但自信满满
- **密集竖排文言直接击穿现代 VL 模型**——抓约 400 字就停
- **NAS 存储 I/O 静默摧毁并行效率**——exFAT 上 16 路并行比单线程还慢

*Tutorials stop at "run tesseract on your image". Real scanned books hit walls they never mention: MuPDF hangs forever on corrupted PDFs (C-level syscall — signals can't interrupt it); VLM OCR hallucinates with perfect confidence; dense vertical classical text defeats modern VL models (~400 chars and they stop); NAS storage I/O silently destroys parallelism.*

---

## 工具清单 / Tools

| 工具 | 做什么 |
|---|---|
| `tools/ocr_vlm_batch.py` | 视觉模型批量 OCR（GLM-4.5V / SiliconFlow），**四层幻觉检测** + 断点续传 + 逐页重试 |
| `tools/ocr_single.py` + `tools/ocr_batch_v5.sh` | 离线 tesseract + PyMuPDF 管线；每册独立子进程，超时 `kill -9`（MuPDF 卡死的唯一可靠解） |
| `tools/split_double_pages.py` | 双页展开拆分；横版页切左右半，竖版页直接缩放；输出 ≤1500px JPEG q80，优先复用已有图片 |
| `tools/fix_hallucinations.py` | 对质检不合格的页重跑 OCR，**只有通过质量闸的产出才保存** |
| `tools/clean_md.py` | 产出清洗：页眉噪声、页标记、全半角混乱、断裂标点（顶部配置区按你的书改） |

**四层幻觉闸 / The 4-layer gate**——单页文本依次过（`ocr_vlm_batch.py`）：

```
L1  单字复读 > 60%                  → 拒
L2  唯一字符占比 < 5%               → 拒
L3  香农熵 < 2.5（文本长度 > 50）    → 拒
L4  3-gram 循环（≤10 种且占比 >50%） → 拒
全过                                → 落盘
```

闸门是筛子，不是保险：过闸不等于对，它只把明显是幻觉的先挡在门外。**最终判断仍要对原图逐字核对。**

---

## 血泪教训 / Hard-won lessons

| 教训 | 详情 |
|---|---|
| 用 `kill -9` 杀 | MuPDF 卡死在 C 层。bash 调度 + 独立子进程 + `kill -9` 是**唯一**可靠姿势；SIGALRM 和 `multiprocessing` 都不行 |
| 大 PDF 用 72dpi | 超过 20MB 的 PDF，72dpi 渲染快 4-5 倍；tesseract 内部会放大，质量损失可忽略 |
| stderr 要在 Python 内重定向 | MuPDF 会用 ExtGState 错误刷屏。用 `os.dup2`——**绝不**在 shell 层写 `2>/dev/null`（它会连 stdout 一起吞掉） |
| 用 `/private/tmp/` 而非 `/tmp/` | ARM macOS 上 homebrew tesseract 必须拿到真实路径（符号链接差异） |
| 先拷到本地 SSD 再跑 | exFAT NAS 卷上 16 路并行**比单线程还慢**；拷到本地 APFS 上 4 路并行 = 4 倍加速 |
| AI 视觉判不准 OCR 质量 | 拿 VLM 问"这段 OCR 对不对"，与真值偏差可达 30%。**一律逐字对原图。** |

---

## 什么页用什么模型 / Which model for which page

| 页面类型 | 推荐 |
|---|---|
| 现代排版书 | 视觉模型（GLM-4.5V 等）或 MinerU |
| 木刻 · 稀疏文字 | 视觉模型 ✅ |
| **密集竖排古籍** | tesseract / MinerU（VL 模型只抓约 400 字 ❌） |

---

## 效果示例 / Demo

![OCR before/after](examples/before_after.jpg)

*合成样张：印刷宋体 + 扫描噪点，**非真实扫描件**——如实标注，仅演示印刷体中文的识别效果。真实木刻影印件的对照样张列入待办。*

---

## 管线架构 / Pipeline

完整架构图见 [docs/pipeline.md](docs/pipeline.md)：
拆分 → 按页型路由 → OCR → 幻觉闸 → Markdown + 质量报告 → 清洗。

---

## 版权 / Copyright

本仓库**只含流程与工具**，不含任何书籍原文、扫描件或 OCR 产出——那些属于被处理的书，请自行排除在版本控制之外。**只对你拥有处理权、且法律允许的素材使用本工具。**

*This repository contains only the workflow and tools — no book text, scans, or OCR output. Use it only on material you have the right to process.*

## License

MIT — use it, fork it, ship it.
