# Demo provenance / 演示素材来源与复现

`before_after.jpg` 是本仓库工具的**真实运行结果**，不是示意图。

## 素材 / Source

| 项 | 内容 |
|---|---|
| 书刊 | 《国粹学报》第四十二期 |
| 版本 | 民國鉛印本（铅字排版，竖排） |
| 取样页 | 第 3 页（PDF 第 3 页，200 dpi 导出） |
| 来源 | Wikimedia Commons（天一阁藏本扫描件，共 84 页） |
| 许可 | **Public domain** |

`examples/demo-scan-output.md` 是同一次运行的**原始输出原文**（未人工修改），可逐字与图对照。

## 怎么复现 / Reproduce

```bash
# 1) 把该页导出为单页 jpg，放进「一卷一目录」的结构里
#    目录：$OCR_PAGES_DIR/<卷名>/page_0003.jpg

# 2) 跑管线（真实 API 调用）
export SILICONFLOW_API_KEY=sk-xxx
export OCR_PAGES_DIR=./pages OCR_OUTPUT_DIR=./out
python3 tools/ocr_vlm_batch.py --vol DEMO

# 3) 产出 → ./out/DEMO.md
```

## 实测参数 / Measured

| 项 | 值 |
|---|---|
| 模型 | GLM-4.5V（SiliconFlow API） |
| 页图 | 1500 × 1182 px（原页 1964 × 1548，长边缩到 1500） |
| 输出 | 697 字 |
| 耗时 | 51 秒（单页） |
| 人工修改 | 无（清洗步骤由 `tools/clean_md.py` 承担，本图展示的是清洗前） |

## 说明 / Notes

- 右栏刻意展示**原始输出**——包括空格与断行在内的原始形态。这不是排版失误，是我们想让读者看到的起点：未经清洗的 OCR 产出长什么样。
- 该页属于「密集竖排铅印」，按 README 的路由表本可由 tesseract 离线路处理；此图演示的是 VLM 路在竖排页上的实际表现。
- 早期版本曾用合成样张示意（印刷宋体 + 噪点），已被真实扫描页取代。
