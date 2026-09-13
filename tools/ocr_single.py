#!/usr/bin/env python3
"""Single-PDF OCR worker (called by ocr_batch_v5.sh).

tesseract + PyMuPDF offline pipeline for Chinese scanned books.
每个 PDF 作为独立进程运行：MuPDF 损坏页卡死时由调度脚本 kill -9。

Key pitfalls baked in / 已固化的坑：
- stderr redirect via os.dup2 INSIDE Python (shell-level redirect eats stdout too)
- /private/tmp not /tmp on ARM macOS (homebrew tesseract symlink issue)
- 72dpi for large PDFs (4-5x faster, negligible quality loss)
- max page cap to avoid runaway runs

Output: JSON result on stdout {"status": "ok"|"error", "path": ..., "pages": N}
"""
import fitz          # PyMuPDF
import subprocess
import re
import json
import os
import sys

TMP_DIR = "/private/tmp/ocr_batch"           # NOT /tmp — ARM macOS homebrew tesseract
MAX_PAGES = 50                                # cap per PDF
DPI = 72                                      # 72 fast / 150 balanced / 200 quality
PDF_DIR = os.environ.get("OCR_PDF_DIR", os.path.expanduser("~/ocr_pdfs"))
OUT_DIR = os.environ.get("OCR_OUTPUT_DIR", os.path.expanduser("~/ocr_output"))


def sanitize_name(name):
    name = re.sub(r"【[^】]*】", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = re.sub(r"\(\d+\)$", "", name)
    return name


def main():
    idx = int(sys.argv[1])
    pdfs = sorted(f for f in os.listdir(PDF_DIR) if f.lower().endswith(".pdf"))
    if idx >= len(pdfs):
        print(json.dumps({"status": "error", "error": "index out of range"}))
        return

    fp = os.path.join(PDF_DIR, pdfs[idx])
    os.makedirs(TMP_DIR, exist_ok=True)
    os.makedirs(OUT_DIR, exist_ok=True)

    # suppress MuPDF stderr noise INSIDE Python (never at shell level)
    devnull = os.open(os.devnull, os.O_WRONLY)
    stderr_fd = os.dup(2)
    os.dup2(devnull, 2)

    try:
        doc = fitz.open(fp)
        page_count = doc.page_count
        max_pages = min(page_count, MAX_PAGES)

        base = sanitize_name(os.path.splitext(pdfs[idx])[0])
        out_md = os.path.join(OUT_DIR, base + ".md")
        lines = []

        for pg_idx in range(max_pages):
            try:
                page = doc[pg_idx]
                pix = page.get_pixmap(dpi=DPI)
                img_path = os.path.join(TMP_DIR, f"_pg_{idx}_{pg_idx}.png")
                pix.save(img_path)
            except Exception:
                continue  # corrupted page: skip, don't die

            out_base = os.path.join(TMP_DIR, f"_ocr_{idx}_{pg_idx}")
            try:
                subprocess.run(
                    ["tesseract", img_path, out_base, "-l", "chi_sim+eng", "--psm", "6"],
                    capture_output=True, timeout=60,
                )
                with open(out_base + ".txt", encoding="utf-8") as f:
                    text = f.read().strip()
                if text:
                    lines.append(text)
            except subprocess.TimeoutExpired:
                pass
            finally:
                for p in (img_path, out_base + ".txt"):
                    if os.path.exists(p):
                        os.remove(p)

        doc.close()
        with open(out_md, "w", encoding="utf-8") as f:
            f.write("\n\n".join(lines))

        print(json.dumps({"status": "ok", "path": out_md,
                          "pages": max_pages, "total": page_count},
                         ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False))
    finally:
        os.dup2(stderr_fd, 2)
        os.close(devnull)
        os.close(stderr_fd)


if __name__ == "__main__":
    main()
