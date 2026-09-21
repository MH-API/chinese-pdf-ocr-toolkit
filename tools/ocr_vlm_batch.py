#!/usr/bin/env python3
"""
Chinese classic woodblock OCR - batch script (VLM)
GLM-4.5V (SiliconFlow) 逐页转录，含幻觉检测+断点续传

用法：
  python3 ocr_batch.py                          # 全部
  python3 ocr_batch.py --vol TB-01-42           # 单卷
  python3 ocr_batch.py --vol TB-01-42 --limit 5  # 测试前5页
"""

import os, sys, json, time, base64, argparse, re
from pathlib import Path
from collections import Counter
import math
import httpx

BASE = os.environ.get("OCR_BOOK_BASE", "./pages")  # one subdir per volume, single-page jpgs inside
PAGES_DIR = os.environ.get("OCR_PAGES_DIR", os.path.expanduser("~/ocr_pages"))
OUT_DIR = os.environ.get("OCR_OUTPUT_DIR", os.path.expanduser("~/ocr_output"))
PROGRESS_FILE = os.path.join(OUT_DIR, "_progress.json")
LOG_FILE = os.path.join(OUT_DIR, "_ocr.log")

# API配置
API_URL = "https://api.siliconflow.cn/v1/chat/completions"
MODEL = "zai-org/GLM-4.5V"
MAX_TOKENS = 4096
TEMPERATURE = 0.1
MAX_RETRIES = 0
# 单页请求超时（秒）。密集竖排/大页面在 20s 下必超时——那是默认值太紧，不是模型不行。
HTTP_TIMEOUT = float(os.environ.get("OCR_TIMEOUT", "180"))

PROMPT = """请将这张古籍页面的文字完整转录为繁体中文。
这是单页竖排木刻版古籍，从右到左从上到下阅读。
完整转录所有可见文字，不要遗漏。保持繁体中文。
不要添加任何解释。不要描述版面。按阅读顺序输出。"""

def get_api_key():
    return os.environ.get("SILICONFLOW_API_KEY", "")

def log(msg):
    timestamp = time.strftime("%H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")
        f.flush()

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {}

def save_progress(data):
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(PROGRESS_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def detect_hallucination(text):
    """四层幻觉检测：单字重复 / n-gram循环 / 唯一字符占比 / 香农熵
    返回 (is_hallucination, reason)"""
    clean = text.strip()
    if len(clean) < 20:
        return False, ""
    
    chars_only = re.sub(r'\s+', '', clean)
    if not chars_only:
        return False, ""
    
    # 1. 单字重复 > 60%
    counter = Counter(chars_only)
    top_char, top_count = counter.most_common(1)[0]
    if top_count / len(chars_only) > 0.6:
        return True, f"单字'{top_char}'重复{top_count}/{len(chars_only)}={top_count/len(chars_only):.0%}"
    
    # 2. 唯一字符占比 < 5%
    unique_ratio = len(set(chars_only)) / len(chars_only)
    if unique_ratio < 0.05:
        return True, f"唯一字符占比{unique_ratio:.1%}"
    
    # 3. Shannon熵 < 2.5 (大文本)
    if len(chars_only) > 50:
        ent = 0
        total = len(chars_only)
        for c, n in counter.items():
            p = n / total
            ent -= p * math.log2(p)
        if ent < 2.5:
            return True, f"Shannon熵={ent:.1f}"
    
    # 4. 3-gram循环检测
    if len(chars_only) > 30:
        ngrams = [chars_only[i:i+3] for i in range(len(chars_only)-2)]
        ng_counter = Counter(ngrams)
        distinct = len(ng_counter)
        if distinct <= 10 and ng_counter.most_common(1)[0][1] / len(ngrams) > 0.5:
            return True, f"3-gram循环(distinct={distinct}, top={ng_counter.most_common(1)[0][1]/len(ngrams):.0%})"
    
    return False, ""

def ocr_page(img_path, api_key):
    """OCR单页，返回 (text, error)"""
    with open(img_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()
    
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = httpx.post(
                API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": MODEL,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                            {"type": "text", "text": PROMPT}
                        ]
                    }],
                    "max_tokens": MAX_TOKENS,
                    "temperature": TEMPERATURE
                },
                timeout=httpx.Timeout(HTTP_TIMEOUT, connect=8.0)
            )
            data = resp.json()
            
            if "choices" in data:
                content = data["choices"][0]["message"]["content"]
                # 清理box标签
                content = content.replace("<|begin_of_box|>", "").replace("<|end_of_box|>", "")
                content = content.strip()
                
                # 幻觉检测
                is_hall, reason = detect_hallucination(content)
                if is_hall:
                    if attempt < MAX_RETRIES:
                        log(f"  幻觉({reason})，重试 {attempt+2}/{MAX_RETRIES+1}")
                        time.sleep(2)
                        continue
                    else:
                        return content, f"HALLUCINATION: {reason}"
                
                return content, None
            else:
                err = data.get("error", {}).get("message", str(data))
                if attempt < MAX_RETRIES:
                    log(f"  API错误: {err}，重试 {attempt+2}/{MAX_RETRIES+1}")
                    time.sleep(3)
                    continue
                return "", f"API_ERROR: {err}"
                
        except Exception as e:
            if attempt < MAX_RETRIES:
                log(f"  网络错误: {e}，重试 {attempt+2}/{MAX_RETRIES+1}")
                time.sleep(5)
                continue
            return "", f"NETWORK_ERROR: {e}"
    
    return "", "MAX_RETRIES_EXCEEDED"

def process_volume(vol_name, limit=None):
    """处理单卷所有单页"""
    pages_dir = os.path.join(PAGES_DIR, vol_name)
    if not os.path.isdir(pages_dir):
        log(f"⚠ {vol_name}: 页面目录不存在 {pages_dir}")
        return
    
    # 获取所有单页图片，按页码排序
    images = sorted([
        f for f in os.listdir(pages_dir) 
        if f.endswith('.jpg') and not f.startswith('_tmp')
    ])
    
    if limit:
        images = images[:limit]
    
    api_key = get_api_key()
    if not api_key:
        log("❌ 未找到 SILICONFLOW_API_KEY")
        return
    
    progress = load_progress()
    vol_key = vol_name
    completed = set(progress.get(vol_key, []))
    
    vol_md_path = os.path.join(OUT_DIR, f"{vol_name}.md")
    vol_lines = []
    
    # 如果之前有部分产出，加载
    if os.path.exists(vol_md_path):
        with open(vol_md_path) as f:
            vol_lines = f.read().split('\n')
    
    total = len(images)
    success = 0
    failed = 0
    skipped = 0
    
    log(f"\n{'='*50}")
    log(f"{vol_name}: {total} 单页 (已完成 {len(completed)})")
    
    for i, img_name in enumerate(images):
        if img_name in completed:
            skipped += 1
            continue
        
        img_path = os.path.join(pages_dir, img_name)
        start = time.time()
        text, error = ocr_page(img_path, api_key)
        elapsed = time.time() - start
        
        if error:
            log(f"  [{i+1}/{total}] {img_name} ❌ {error} ({elapsed:.0f}s)")
            failed += 1
            if "HALLUCINATION" in str(error):
                # 幻觉页仍保存但标记（已带标记写盘，视为处理过，不再重跑）
                vol_lines.append(f"\n> —— {img_name} [⚠幻觉] ——\n")
                vol_lines.append(text)
                vol_lines.append("")
                completed.add(img_name)
            # 其余错误（网络/API）：**不记入进度**，下次重跑自动补这一页
        else:
            log(f"  [{i+1}/{total}] {img_name} ✓ {len(text)}字 ({elapsed:.0f}s)")
            success += 1
            vol_lines.append(f"\n> —— {img_name} ——\n")
            vol_lines.append(text)
            vol_lines.append("")
            completed.add(img_name)
        
        # 每10页写盘
        if (success + failed) % 10 == 0:
            with open(vol_md_path, "w") as f:
                f.write('\n'.join(vol_lines))
            progress[vol_key] = list(completed)
            save_progress(progress)
        
        # 连续5次失败则暂停
        if failed >= 5 and failed > success:
            log(f"⚠ 连续失败过多 ({failed}f/{success}s)，暂停")
            break
    
    # 最终写盘
    with open(vol_md_path, "w") as f:
        f.write('\n'.join(vol_lines))
    progress[vol_key] = list(completed)
    save_progress(progress)
    
    log(f"{vol_name} 完成: {success}✓ {failed}✗ {skipped}跳")
    pending = [im for im in images if im not in completed]
    if pending:
        log(f"⚠ 还有 {len(pending)} 页未完成（失败页不记进度）——重跑同一条命令即可补齐")
    return success, failed, skipped

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vol", help="单卷名称")
    parser.add_argument("--limit", type=int, help="限制页数（测试用）")
    args = parser.parse_args()
    
    os.makedirs(OUT_DIR, exist_ok=True)
    
    # 初始化日志
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write(f"# OCR log {time.strftime('%Y-%m-%d %H:%M')}\n")
    
    api_key = get_api_key()
    if not api_key:
        log("❌ 未找到API Key，请设置 SILICONFLOW_API_KEY")
        sys.exit(1)
    
    # 测试API连通性
    log("测试API连通性...")
    try:
        resp = httpx.post(
            API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": "回复OK"}],
                "max_tokens": 10
            },
            timeout=httpx.Timeout(HTTP_TIMEOUT, connect=8.0)
        )
        if resp.status_code == 200:
            log("✓ API连通正常")
        else:
            log(f"⚠ API返回 {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        log(f"❌ API连接失败: {e}")
        sys.exit(1)
    
    if args.vol:
        process_volume(args.vol, args.limit)
    else:
        vols = sorted([d for d in os.listdir(PAGES_DIR) 
                       if os.path.isdir(os.path.join(PAGES_DIR, d))])
        log(f"共 {len(vols)} 卷待处理\n")
        for vol in vols:
            process_volume(vol)

if __name__ == "__main__":
    main()
