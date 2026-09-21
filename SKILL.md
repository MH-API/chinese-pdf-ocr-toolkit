---
name: chinese-scanned-book-ocr
description: Use when turning a scanned Chinese book with no text layer (modern typeset or dense vertical woodblock) into reliable Markdown. Routes pages by type, runs a 4-layer hallucination gate, cleans output, then verifies against the scan. 中文扫描书 OCR 全流程。
license: MIT
---

# 中文扫描书 OCR / Chinese Scanned-Book OCR

把没有文字层的扫描书，变成一份可检索、可校对、可引用的 Markdown。

## 何时用 / When to use

**用**：
- 输入是扫描件（PDF 或单页图片），**没有文字层**
- 输出要 Markdown（后续要检索、要逐字校对、要引用）
- 素材是中文书：现代排版、老式铅印、木刻影印都算

**不用**：
- PDF 有文字层 → 直接 `pdftotext`，别上 OCR
- 单张截图 / 发票 / 商务文档 → 有更轻的工具
- 要求 100% 免校对 → 做不到，本流程的价值恰恰在于**把不可信的产出变成可核对的产出**

## 铁律 / Non-negotiables

1. **先量后动**：拿到书先看页型（横版双页合排？竖排？字密度？有无损坏册），再决定用哪条路。选错模型 = 整本白跑。
2. **逐页过闸**：任何一页 OCR 产出必须先过四层幻觉闸才允许落盘（闸门逻辑见 `tools/ocr_vlm_batch.py`）。
3. **过闸 ≠ 正确**：闸门只挡明显幻觉。**质量判定只能对着原图逐字核对**——绝不要问视觉模型"这段 OCR 对不对"（实测与真值偏差可达 30%）。
4. **一册一进程 + `kill -9`**：损坏页会让 MuPDF 卡在 C 层 syscall，signal 打不进去。bash 调度 + 独立子进程 + 超时强杀是唯一可靠姿势。
5. **I/O 先落地**：素材在 NAS / exFAT 上，先拷到本地 SSD 再跑——外置卷上多路并行会比单线程还慢。

## 流程 / Workflow

**0. 盘点**
列卷目录、页数、判断是否双页合排、找出损坏 PDF。此时就要决定路由（见第 2 步）。

**1. 拆分**
```bash
python3 tools/split_double_pages.py <源PDF目录> <输出目录>   # 先 --dry-run 预览
```
产出 `p0000_left.jpg` / `p0000_right.jpg` 等单页图。**记下编号规则**——后面重跑补页要对得上号。

**2. 按页型路由**

| 页型 | 走哪条路 |
|---|---|
| 现代排版书 | 视觉模型（GLM-4.5V 等），或 MinerU |
| 木刻 · 稀疏文字 | 视觉模型 ✅ |
| **密集竖排古籍** | tesseract 离线路（VL 模型抓约 400 字就停 ❌） |

```bash
# VLM 路
export SILICONFLOW_API_KEY=sk-xxx OCR_PAGES_DIR=.../pages OCR_OUTPUT_DIR=.../out
python3 tools/ocr_vlm_batch.py --vol VOL-01 --limit 5   # 必须先试跑，确认识别质量再整卷
python3 tools/ocr_vlm_batch.py --vol VOL-01

# 离线路（tesseract + PyMuPDF，无需 API）
python3 tools/ocr_single.py <序号>          # 单册 worker，stdout 输出 JSON 结果
./tools/ocr_batch_v5.sh [起始序号] [数量] [超时秒数]
```

**3. 过闸补漏**
```bash
python3 tools/fix_hallucinations.py 243,251   # 对质检不合格的页重跑，只有过闸才落盘
```

**4. 清洗**
先改 `tools/clean_md.py` 顶部的配置区（页眉噪声正则、页标记格式），再运行。**配置不改直接跑 = 白跑**，那些正则本来就是要按书改的。

**5. 验收（不可省）**
抽 5% 页面（必含首页、末页、图表页、竖排最密的一页）对原图逐字核对。
发现系统性错字（如固定把某字认成另一个字）→ 回到第 4 步加替换规则，重跑。

## 环境 / Setup

- Python 3.9+；依赖 `pymupdf`、`pillow`、`httpx`
- 离线路另需 tesseract（含 `chi_sim` 语言包）
- 环境变量：`SILICONFLOW_API_KEY`、`OCR_PAGES_DIR`、`OCR_OUTPUT_DIR`；单页超时 `OCR_TIMEOUT`（秒，默认 180）；离线路另用 `OCR_PDF_DIR`
- 首次跑视觉模型不需要下载模型（走 API）；MinerU 若使用则首次约 1 GB 模型

## 已知坑 / Known pitfalls

| 坑 | 解 |
|---|---|
| 套 PDF 卡死不退 | bash 调度 + 独立子进程 + 超时 `kill -9`（`ocr_batch_v5.sh` 已实现） |
| 大 PDF 渲染慢 | > 20MB 的 PDF 用 72dpi，快 4-5 倍，tesseract 内部会放大，质量损失可忽略 |
| stderr 被 MuPDF 刷屏 | 在 Python 内 `os.dup2` 重定向；shell 层 `2>/dev/null` 会连 stdout 一起吞 |
| ARM macOS 上 tesseract 找不到 | 用真实路径 `/private/tmp/`，不要用符号链接 `/tmp/` |
| 外置卷并行更慢 | 先拷到本地 SSD（APFS）再跑 |
| 页号对不上，重跑补页错位 | 拆分器的编号规则要贯穿全程，补页前先核对文件名 |
| `fix_hallucinations.py` 找不到页 | 它按 `*_page_NNNN.png` 匹配，页图命名要合规 |
| **断点续传反而漏页** | 「完成」的判据必须钉死：只有**真产出内容**的页才准记进进度文件。若在收尾处批量标记全部页（含失败页），失败页会被永久跳过、静默丢失。改这类代码时先写清「什么算完成」，并跑一次「全失败」用例证明进度文件是空的 |

## 交付 / Deliverable

除 Markdown 正文外，必须一并交：**质检日志**（哪些页过闸失败、重跑了几次）+ **未决问题清单**（识别不出、疑似缺页、符号丢失、无法判断对错的地方）。
只交文本不交问题清单 = 把核对成本全推给下一个人。
