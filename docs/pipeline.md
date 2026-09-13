# Pipeline Architecture / 管线架构

```
                          Chinese Scanned Book (PDF/JPG)
                                      │
                    ┌─────────────────┴─────────────────┐
                    ▼                                   ▼
          ┌──────────────────┐              ┌──────────────────────┐
          │  Double-page     │              │  Page rasterization  │
          │  splitter        │              │  72-200 dpi (PyMuPDF)│
          │  (woodblock scans)│              └──────────┬───────────┘
          └────────┬─────────┘                           │
                   │                                     ▼
                   │                          ┌─────────────────────┐
                   │                          │  Route by page type │
                   │                          └───────┬─────┬───────┘
                   │                     modern/clean │     │ dense vertical
                   │                                  ▼     ▼ classical
                   │                    ┌──────────────┐  ┌──────────────────┐
                   │                    │ VLM OCR      │  │ tesseract        │
                   │                    │ (GLM-4.5V    │  │ chi_sim+eng      │
                   │                    │ SiliconFlow) │  │ --psm 6          │
                   │                    └──────┬───────┘  └────────┬─────────┘
                   │                           ▼                   │
                   │                ┌──────────────────┐           │
                   │                │ 4-layer          │           │
                   │                │ hallucination    │───────────┤
                   │                │ detection        │           │
                   │                └────────┬─────────┘           │
                   │                         ▼                     │
                   │              ┌─────────────────────┐          │
                   └─────────────►│  Markdown output    │◄─────────┘
                                  │  + quality report   │
                                  └──────────┬──────────┘
                                             ▼
                                  ┌─────────────────────┐
                                  │  post-cleanup       │
                                  │  (clean_md.py)      │
                                  └─────────────────────┘
```

## Hallucination detection / 幻觉检测四层

```
text ──► L1 single-char repetition > 60%        ──► REJECT
     ──► L2 unique-char ratio < 5%              ──► REJECT
     ──► L3 Shannon entropy < 2.5 (len > 50)    ──► REJECT
     ──► L4 3-gram loop (≤10 distinct, >50% dom)──► REJECT
     ──► PASS ──► save to output
```
