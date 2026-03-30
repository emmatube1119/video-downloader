"""
영상 다운로드 도구 v25.0 (쿠팡 파트너스 키워드 연동 및 ETA 엔진 탑재)
"""
import sys, os, re, json, requests, threading, time
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
from coupang_api import extract_keywords

progress_info = {}

def init_prog(tid="default"): 
    progress_info[tid] = {
        "status":"idle", "percent":0, "downloaded_mb":0.0, "total_mb":0.0, 
        "title":"", "message":"준비 중", "start_time": time.time(), "elapsed": 0, "eta": "계측 중...",
        "keywords": ""
    }

def set_prog(tid, k, v):
    if tid not in progress_info: init_prog(tid)
    progress_info[tid][k] = v
    # 실시간 정보 갱신
    t = progress_info[tid]
    if t["status"] not in ["done", "error"]:
        elapsed = time.time() - t["start_time"]
        t["elapsed"] = round(elapsed, 1)
        # ETA 계산 (다운로드 중일 때만 유효)
        if t["status"] == "downloading" and t["downloaded_mb"] > 0 and t["total_mb"] > 0:
            speed = t["downloaded_mb"] / elapsed # MB/s
            rem_mb = t["total_mb"] - t["downloaded_mb"]
            if speed > 0:
                rem_sec = int(rem_mb / speed)
                t["eta"] = f"약 {rem_sec}초 남음" if rem_sec < 60 else f"약 {rem_sec//60}분 {rem_sec%60}초 남음"
            else: t["eta"] = "계측 중..."
        elif t["status"] == "merging": t["eta"] = "병합 중 (약 1분 내외)"
        elif t["status"] == "done": t["eta"] = "완료됨"
        else: t["eta"] = "분석 중..."

def get_prog(tid): return progress_info.get(tid, {"status":"idle", "percent":0})

def normalize_url(url):
    if not url.startswith("http"): return url
    if any(d in url for d in ["xhslink.com", "vt.tiktok.com", "tiktok.com/t/"]):
        try:
            r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, allow_redirects=True, timeout=10)
            return r.url
        except: return url
    return url

def download_video_and_info(url, task_id="default", out_dir="outcome", custom_name=""):
    set_prog(task_id, "status", "extracting"); set_prog(task_id, "message", "엔진 가동..."); url = normalize_url(url)
    is_tk = "tiktok" in url; is_xhs = "xiaohongshu" in url
    
    if any(d in url for d in ["youtube.com", "youtu.be", "instagram.com"]):
        try:
            import yt_dlp
            set_prog(task_id, "message", "유튜브 고화질 분석..."); fmt = "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best"
            with yt_dlp.YoutubeDL({"quiet":True,"noplaylist":True,"format":fmt}) as ydl:
                info = ydl.extract_info(url, download=False); bn = sanitize_filename(custom_name or info.get("title","video"))
                fp = unique_filepath(os.path.join(out_dir, f"{bn}.mp4")); set_prog(task_id, "title", os.path.basename(fp))
                set_prog(task_id, "keywords", extract_keywords(info.get("title","")))
                def hook(d):
                    if d['status'] == 'downloading':
                        try:
                            v = d.get('downloaded_bytes', 0); t = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                            p = d.get('_percent_str', '0%').replace('%','').strip()
                            set_prog(task_id,"percent",int(float(p))); set_prog(task_id,"downloaded_mb",round(v/1048576,2)); set_prog(task_id,"total_mb",round(t/1048576,2))
                            set_prog(task_id,"status","downloading"); set_prog(task_id,"message","고화질 다운로드 중...")
                        except: pass
                    elif d['status'] == 'finished': set_prog(task_id,"status","merging"); set_prog(task_id,"message", "병합 작업 중...")
                opts = {"quiet":True,"noplaylist":True,"format":fmt,"outtmpl":fp,"progress_hooks":[hook],"merge_output_format":"mp4","postprocessor_args":["-y","-c:v","copy","-c:a","aac","-b:a","192k"]}
                with yt_dlp.YoutubeDL(opts) as ydl: ydl.download([url])
                sz = os.path.getsize(fp) if os.path.exists(fp) else 0
                set_prog(task_id,"total_mb",round(sz/1048576,2)); set_prog(task_id,"downloaded_mb",round(sz/1048576,2))
                set_prog(task_id,"status","done"); set_prog(task_id,"percent",100); set_prog(task_id,"message", "완료!"); return True
        except Exception as e: set_prog(task_id, "status", "error"); set_prog(task_id, "message", f"오류: {str(e)[:40]}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-blink-features=AutomationControlled"])
        context = browser.new_context(user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15" if is_tk else "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        page = context.new_page(); v_url = ""; v_found = []
        page.on("response", lambda r: v_found.append(r.url) if (("video" in (r.headers.get("content-type") or "") or ".mp4" in r.url.lower()) and "logo" not in r.url.lower()) else None)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=25000); page.wait_for_timeout(5000)
            e_js = """() => { const s = window.__INITIAL_STATE__ || window.SIGI_STATE || (document.getElementById('initialState')||{}).textContent; return (typeof s === 'string') ? s : (window.__INITIAL_STATE__?.note?.note ? JSON.stringify({note: window.__INITIAL_STATE__.note.note}) : (window.SIGI_STATE ? JSON.stringify(window.SIGI_STATE) : null)); }"""
            st = page.evaluate(e_js); title = page.title() or "video"
            if st:
                try:
                    d = json.loads(st); n = d.get("note") or d.get("props",{}).get("pageProps") or d.get("ItemModule") or d
                    if "ItemModule" in d: it = d["ItemModule"].get(next(iter(d["ItemModule"],""),""),{}); v_url = it.get("video",{}).get("downloadAddr",""); title = it.get("desc", title)
                    if not v_url: v_o = n.get("video") or (n if "play_addr" in n else None); v_url = (v_o or {}).get("downloadAddr") or (v_o or {}).get("url"); title = (n or {}).get("title") or (n or {}).get("desc") or title
                except: pass
            if not v_url and v_found: v_url = v_found[-1]
            if v_url:
                os.makedirs(out_dir, exist_ok=True); bn = sanitize_filename(custom_name or title)
                fp = unique_filepath(os.path.join(out_dir, f"{bn}.mp4")); set_prog(task_id, "title", os.path.basename(fp))
                set_prog(task_id, "keywords", extract_keywords(title))
                set_prog(task_id, "status", "downloading"); set_prog(task_id, "message", "보안 전송 중...")
                resp = context.request.get(v_url, headers={"Referer": url})
                if resp.status == 200:
                    body = resp.body(); total = len(body); set_prog(task_id, "total_mb", round(total/1048576, 2)); set_prog(task_id, "downloaded_mb", round(total/1048576, 2))
                    with open(fp, "wb") as f: f.write(body)
                    set_prog(task_id, "status", "done"); set_prog(task_id, "percent", 100); set_prog(task_id, "message", "완료!"); return True
            else: raise Exception("주소 탐지 실패")
        except Exception as e: set_prog(task_id, "status", "error"); set_prog(task_id, "message", str(e))
        finally: browser.close()
    return False

def sanitize_filename(f): return re.sub(r'[\\/*?:"<>|]', "", f or "video").strip()[:100]
def unique_filepath(p):
    b, e = os.path.splitext(p); c = 1; n = p
    while os.path.exists(n): n = f"{b} ({c}){e}"; c += 1
    return n
