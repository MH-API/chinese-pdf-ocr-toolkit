#!/usr/bin/env python3
"""OCR后清洗脚本

通用框架。需要根据具体项目调整：
- HEADER_PATTERN: 页眉正则
- PAGE_MARKER_TEMPLATE: 页标记格式
- 项目特定的标签统一规则
"""
import re, os
from pathlib import Path

# === 配置区（按项目修改） ===

# 页眉页脚噪声正则（原文每页重复的书名行）
HEADER_PATTERNS = [
    # 例: 《易经例释》·乾为天卦案研究
    r'^《[^》]+》[·\s]*\S{2,5}卦案研究\s*$',
    # 例: 易经例释 · 乾为天
    r'^[《]?易经例释[》]?\s*[·•]\s*\S{2,5}\s*$',
]

# 页标记转换：## 第N页 → "> —— 第N页 ——"（Typora渲染为淡灰引用块）
PAGE_MARKER_TEMPLATE = "> —— 第{page}页 ——"

# 注释格式统一
ANNOTATION_UNIFY = [
    (r'\|([^|]+)\|', r'[\1]'),  # |注释| → [注释]
]

# 页码孤行（无其他内容的纯数字行）
PAGE_NUMBER_PATTERN = r'^\s*\d{1,4}\s*$'


def clean_page_text(text: str) -> str:
    """清洗单页文本"""
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        stripped = line.strip()
        # 跳过页眉
        if any(re.match(p.strip(), stripped) for p in HEADER_PATTERNS):
            continue
        # 跳过孤立页码
        if re.match(PAGE_NUMBER_PATTERN, stripped):
            continue
        cleaned.append(line)
    return '\n'.join(cleaned)


def clean_md_file(input_path: Path, output_dir: Path) -> int:
    """清洗单个MD文件"""
    text = input_path.read_text(encoding='utf-8')
    old_lines = text.count('\n')

    # 1. 统一注释格式
    for pattern, replacement in ANNOTATION_UNIFY:
        text = re.sub(pattern, replacement, text)

    # 2. 按页分割清洗
    pages = re.split(r'(^## 第\d+页$)', text, flags=re.MULTILINE)
    result = []
    first = True
    i = 0
    while i < len(pages):
        if i + 1 < len(pages) and re.match(r'^## 第\d+页$', pages[i + 1].strip()):
            page_header = re.match(r'## 第(\d+)页', pages[i + 1].strip())
            page_num = page_header.group(1)
            page_body = pages[i + 2] if i + 2 < len(pages) else ""
            cleaned_body = clean_page_text(page_body).strip()

            if not first:
                result.append(f"\n{PAGE_MARKER_TEMPLATE.format(page=page_num)}\n")
            first = False

            if cleaned_body:
                result.append(cleaned_body)
            i += 3
        else:
            result.append(pages[i])
            i += 1

    output = '\n'.join(result)

    # 3. 连续空行压缩
    output = re.sub(r'\n{3,}', '\n\n', output)

    # 4. 写入
    output_path = output_dir / input_path.name
    output_path.write_text(output)
    new_lines = output.count('\n')
    return old_lines - new_lines


def main():
    import sys
    input_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd() / "output"
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else input_dir / "cleaned"
    output_dir.mkdir(parents=True, exist_ok=True)

    mds = sorted(input_dir.glob("*.md"))
    if not mds:
        print("无MD文件")
        return

    total_removed = 0
    for md in mds:
        removed = clean_md_file(md, output_dir)
        total_removed += removed
        print(f"  {md.name}: 去{removed}行噪声")

    print(f"\n汇总: {len(mds)} 本, 去除 {total_removed} 行噪声")
    print(f"输出: {output_dir}")


if __name__ == "__main__":
    main()
