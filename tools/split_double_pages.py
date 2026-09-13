#!/usr/bin/env python3
"""
双页展开PDF拆分脚本
遍历卷目录，自动检测横版双页并拆分为左右单页JPEG

用法：
  python3 split_double_pages.py <源PDF目录> <输出目录>
  python3 split_double_pages.py --vol TB-01-42  # 单卷
  python3 split_double_pages.py --dry-run         # 预览

特性：
  - 优先复用已有PNG/JPG图片（避免重复提取）
  - 横版页面（w > h）→ crop左右半
  - 竖版页面（h > w）→ 直接resize
  - 输出 max 1500px, JPEG q80
"""

import fitz, os, sys, argparse
from PIL import Image

MAX_PX = 1500
JPEG_QUALITY = 80

def is_double_page(w, h):
    return w > h * 1.1

def process_page(img_path, out_dir, page_idx):
    img = Image.open(img_path)
    w, h = img.size
    if is_double_page(w, h):
        mid = w // 2
        halves = [
            ("right", img.crop((0, 0, mid, h))),
            ("left", img.crop((mid, 0, w, h))),
        ]
        results = []
        for side, half in halves:
            iw, ih = half.size
            ratio = MAX_PX / max(iw, ih)
            if ratio < 1:
                half = half.resize((int(iw*ratio), int(ih*ratio)), Image.LANCZOS)
            out_path = os.path.join(out_dir, f"p{page_idx:04d}_{side}.jpg")
            half.save(out_path, "JPEG", quality=JPEG_QUALITY)
            results.append(out_path)
        return results
    else:
        ratio = MAX_PX / max(w, h)
        if ratio < 1:
            img = img.resize((int(w*ratio), int(h*ratio)), Image.LANCZOS)
        out_path = os.path.join(out_dir, f"p{page_idx:04d}.jpg")
        img.save(out_path, "JPEG", quality=JPEG_QUALITY)
        return [out_path]

def find_images(vol_dir):
    """收集已有图片文件"""
    imgs = []
    for root, dirs, files in os.walk(vol_dir):
        for f in sorted(files):
            if f.lower().endswith(('.png', '.jpg', '.jpeg')):
                imgs.append(os.path.join(root, f))
    return imgs

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", nargs="?", help="源PDF目录")
    parser.add_argument("output", nargs="?", help="输出目录")
    parser.add_argument("--vol", help="单卷名称")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.vol:
        # 从BASE/vol_name中找PDF和图片
        base = args.source or os.getcwd()
        vol_dir = os.path.join(base, args.vol)
        out_dir = os.path.join(args.output or os.path.join(base, "_ocr_pages"), args.vol)
    elif args.source and args.output:
        vol_dir = args.source
        out_dir = args.output
    else:
        print("用法: split_double_pages.py <源目录> <输出目录> 或 --vol TB-01-42")
        sys.exit(1)

    if not args.dry_run:
        os.makedirs(out_dir, exist_ok=True)

    # 找PDF
    pdf_path = None
    for f in os.listdir(vol_dir):
        if f.endswith('.pdf'):
            pdf_path = os.path.join(vol_dir, f)
            break

    if not pdf_path:
        print(f"未找到PDF: {vol_dir}")
        return

    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    images = find_images(vol_dir)

    count = 0
    if len(images) >= total_pages * 0.9:
        print(f"复用 {len(images)} 已有图片 (≈{total_pages} PDF页)")
        for i, img_path in enumerate(images[:total_pages]):
            if args.dry_run:
                w, h = Image.open(img_path).size
                count += 2 if is_double_page(w, h) else 1
            else:
                results = process_page(img_path, out_dir, i)
                count += len(results)
    else:
        print(f"从PDF提取 ({len(images)} 图片 < {total_pages} 页)")
        for i in range(total_pages):
            if args.dry_run:
                p = doc[i]
                count += 2 if is_double_page(p.rect.width, p.rect.height) else 1
            else:
                pix = doc[i].get_pixmap(dpi=200)
                tmp = os.path.join(out_dir, f"_tmp_{i:04d}.png")
                pix.save(tmp)
                results = process_page(tmp, out_dir, i)
                os.remove(tmp)
                count += len(results)

    doc.close()
    print(f"→ {count} 单页")

if __name__ == "__main__":
    main()
