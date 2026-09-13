#!/usr/bin/env python3
"""Batch re-OCR hallucinated/empty pages with quality gating.
Reads page list, OCRs each with VL-30B-A3B, runs 4-layer quality check,
only saves if passes. Usage:

    python3 fix_hallucinations.py           # fix default list
    python3 fix_hallucinations.py 2430,2510 # fix specific pages
"""
import os, sys, json, base64, httpx, re, time, cv2, numpy as np
from pathlib import Path
from collections import Counter

for v in ['HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY','all_proxy']:
    os.environ.pop(v, None)

API_KEY = os.environ.get("SILICONFLOW_API_KEY", "")
if not API_KEY:
    sys.exit("ERROR: set SILICONFLOW_API_KEY env var")

STAGING = os.environ.get("OCR_OUTPUT_DIR", os.path.expanduser("~/ocr_output"))
SRC = Path(os.environ.get("OCR_PAGES_DIR", os.path.expanduser("~/ocr_pages")))
pngs = sorted(SRC.glob("*.png"), key=lambda f: int(re.search(r"_page_(-?\d+)", f.stem).group(1)), reverse=True)
fix = [int(x) for x in (sys.argv[1] if len(sys.argv)>1 else "").split(",") if x.strip()]

def qc(text):
    if not text or len(text.strip())<10: return False,"empty"
    c = text.replace("\n","").replace(" ","")
    if len(c)<50: return True,"short"
    m = Counter(c).most_common(1)[0]
    if m[1]/len(c) > 0.6: return False,f"repeat '{m[0]}'x{m[1]}"
    if len(set(c))/len(c) < 0.05: return False,f"low-unique"
    for n in [3,4]:
        ng = [c[i:i+n] for i in range(len(c)-n)]
        if ng and Counter(ng).most_common(1)[0][1] > 50: return False,f"{n}gram-loop"
    return True,"ok"

cli=httpx.Client(timeout=300)
ok=0
for pg in fix:
    print(f"p{pg}...",flush=True)
    img=cv2.imread(str(pngs[pg-1]))
    h,w=img.shape[:2]
    if w>1024:
        s=1024/w; img=cv2.resize(img,(1024,int(h*s)))
    _,e=cv2.imencode(".jpg",img,[cv2.IMWRITE_JPEG_QUALITY,85])
    b64=base64.b64encode(e.tobytes()).decode()
    txt=""
    for a in range(5):
        try:
            r=cli.post("https://api.siliconflow.cn/v1/chat/completions",
                headers={"Authorization":f"Bearer {API_KEY}","Content-Type":"application/json"},
                json={"model":"Qwen/Qwen3-VL-30B-A3B-Instruct","messages":[
                    {"role":"system","content":"古籍OCR助手。完整转录图片文字。"},
                    {"role":"user","content":[{"type":"text","text":f"转录第{pg}页："},{"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{b64}"}}]}
                ],"max_tokens":4096,"temperature":0.1})
            if r.status_code==200:
                t=r.json()["choices"][0]["message"]["content"]
                t=re.sub(r'<\|.*?\|>',"",t).strip()
                p,why=qc(t)
                if p: txt=t; break
                print(f"  {a+1}: {why}",flush=True); time.sleep(3)
            else: print(f"  {a+1}: HTTP{r.status_code}",flush=True); time.sleep(5)
        except Exception as ex: print(f"  {a+1}: {str(ex)[:60]}",flush=True); time.sleep(5)
    if txt:
        open(f"{STAGING}/p{pg:04d}.txt","w").write(txt)
        print(f"  OK {len(txt)}c",flush=True); ok+=1
    else: print(f"  FAIL",flush=True)
cli.close()
print(f"Done: {ok}/{len(fix)}")
