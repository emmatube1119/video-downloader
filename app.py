"""
클라우드 배포용 영상 다운로드 웹앱
===================================
Flask 기반 웹 서버. Render.com 등에 배포 가능.
사용자가 URL을 입력하면 영상을 추출하여 브라우저로 직접 다운로드.
"""

import os
import io
import re
import json
import requests as req_lib
from flask import Flask, request, jsonify, send_file, Response
from playwright.sync_api import sync_playwright

app = Flask(__name__)


def normalize_url(url: str) -> str:
    return url.replace("www.rednote.com", "www.xiaohongshu.com").replace("rednote.com", "www.xiaohongshu.com")


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = name.strip()
    return name[:100] if name else "untitled"


def extract_video_url_from_page(url: str) -> dict:
    url = normalize_url(url)
    result = {"title": "", "type": "", "video_url": "", "image_urls": []}
    video_urls_found = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            locale="ko-KR",
        )
        page = context.new_page()

        def on_response(response):
            content_type = response.headers.get("content-type", "")
            req_url = response.url
            if "video" in content_type or ".mp4" in req_url or "sns-video" in req_url:
                video_urls_found.append(req_url)

        page.on("response", on_response)

        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
        except Exception:
            pass

        page.wait_for_timeout(3000)

        try:
            state_json = page.evaluate("""() => {
                if (window.__INITIAL_STATE__) return JSON.stringify(window.__INITIAL_STATE__);
                return null;
            }""")
            if state_json:
                data = json.loads(state_json)
                note_section = data.get("note", {})
                detail_map = note_section.get("noteDetailMap", {})
                for nid, ninfo in detail_map.items():
                    note = ninfo.get("note", {})
                    if not note:
                        continue
                    result["title"] = note.get("title", "") or note.get("desc", "untitled")
                    result["title"] = result["title"][:80].strip()

                    video = note.get("video", {})
                    if video:
                        result["type"] = "video"
                        media = video.get("media", {})
                        stream = media.get("stream", {})
                        best_url = ""
                        for quality, streams in stream.items():
                            if isinstance(streams, list):
                                for s in streams:
                                    master_url = s.get("masterUrl", "")
                                    if master_url:
                                        best_url = master_url
                                        break
                            if best_url:
                                break
                        if not best_url:
                            consumer = video.get("consumer", {})
                            origin_key = consumer.get("originVideoKey", "")
                            if origin_key:
                                best_url = f"https://sns-video-bd.xhscdn.com/{origin_key}"
                        result["video_url"] = best_url
                    else:
                        result["type"] = "image"
                        img_list = note.get("imageList", [])
                        for img in img_list:
                            url_default = img.get("urlDefault", "")
                            url_pre = img.get("urlPre", "")
                            info_list = img.get("infoList", [])
                            best_img = url_default or url_pre
                            if info_list:
                                best_img = info_list[-1].get("url", best_img)
                            if best_img:
                                if best_img.startswith("//"):
                                    best_img = "https:" + best_img
                                result["image_urls"].append(best_img)
        except Exception as e:
            print(f"파싱 실패: {e}")

        if result["type"] == "video" and not result["video_url"] and video_urls_found:
            result["video_url"] = video_urls_found[0]
        elif not result["type"] and video_urls_found:
            result["type"] = "video"
            result["video_url"] = video_urls_found[0]

        if result["type"] == "video" and not result["video_url"]:
            try:
                video_src = page.evaluate("""() => {
                    const v = document.querySelector('video');
                    if (v) return v.src || v.querySelector('source')?.src || '';
                    return '';
                }""")
                if video_src:
                    result["video_url"] = video_src
            except Exception:
                pass

        if not result["title"]:
            try:
                result["title"] = page.title() or "untitled"
            except Exception:
                result["title"] = "untitled"

        browser.close()
    return result


HTML_PAGE = """<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>영상 다운로드 도구</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            min-height: 100vh;
            background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%);
            color: #e0e0e0;
            display: flex; flex-direction: column; align-items: center; justify-content: center;
            padding: 20px;
        }
        .container { width: 100%; max-width: 640px; }
        .card {
            background: rgba(255,255,255,0.06);
            backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 20px; padding: 40px 36px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.4);
        }
        h1 {
            font-size: 28px; font-weight: 700; text-align: center; margin-bottom: 8px;
            background: linear-gradient(135deg, #a78bfa, #6dd5fa, #ff6fd8);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
        }
        .subtitle { text-align: center; font-size: 14px; color: rgba(255,255,255,0.5); margin-bottom: 32px; }
        .input-group { display: flex; gap: 10px; margin-bottom: 12px; }
        input[type="text"] {
            flex: 1; padding: 14px 18px; border-radius: 12px;
            border: 1px solid rgba(255,255,255,0.15);
            background: rgba(255,255,255,0.08); color: #fff;
            font-size: 14px; font-family: inherit; outline: none;
            transition: border-color 0.3s, box-shadow 0.3s;
        }
        input[type="text"]:focus { border-color: #a78bfa; box-shadow: 0 0 0 3px rgba(167,139,250,0.2); }
        input[type="text"]::placeholder { color: rgba(255,255,255,0.3); }
        button {
            padding: 14px 28px; border-radius: 12px; border: none;
            background: linear-gradient(135deg, #7c3aed, #a78bfa);
            color: #fff; font-size: 15px; font-weight: 600; font-family: inherit;
            cursor: pointer; transition: all 0.3s ease; white-space: nowrap;
        }
        button:hover { transform: translateY(-1px); box-shadow: 0 6px 20px rgba(124,58,237,0.4); }
        button:active { transform: translateY(0); }
        button:disabled { opacity: 0.5; cursor: not-allowed; transform: none; box-shadow: none; }
        #status {
            min-height: 60px; padding: 16px 18px; border-radius: 12px;
            background: rgba(0,0,0,0.3); font-size: 13px; line-height: 1.6;
            white-space: pre-wrap; word-break: break-all; overflow-y: auto; max-height: 200px;
        }
        #status.success { border-left: 3px solid #34d399; }
        #status.error { border-left: 3px solid #f87171; }
        #status.loading { border-left: 3px solid #a78bfa; }
        .history { margin-top: 24px; }
        .history h3 { font-size: 14px; font-weight: 600; margin-bottom: 12px; color: rgba(255,255,255,0.6); }
        .history-item {
            display: flex; align-items: center; gap: 10px;
            padding: 10px 14px; border-radius: 10px;
            background: rgba(255,255,255,0.04); margin-bottom: 6px;
            font-size: 13px; transition: background 0.2s;
        }
        .history-item:hover { background: rgba(255,255,255,0.08); }
        .history-item .icon { font-size: 18px; }
        .history-item .name { flex: 1; color: rgba(255,255,255,0.8); }
        .spinner {
            display: inline-block; width: 14px; height: 14px;
            border: 2px solid rgba(255,255,255,0.2); border-top-color: #a78bfa;
            border-radius: 50%; animation: spin 0.8s linear infinite;
            margin-right: 8px; vertical-align: middle;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        .footer { text-align: center; margin-top: 20px; font-size: 12px; color: rgba(255,255,255,0.25); }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <h1>🎬 영상 다운로드</h1>
            <p class="subtitle">샤오홍슈(레드노트) 영상 URL을 붙여넣고 다운로드</p>
            <div class="input-group">
                <input type="text" id="urlInput" placeholder="영상 URL을 여기에 붙여넣으세요..." autofocus>
                <button id="downloadBtn" onclick="startDownload()">다운로드</button>
            </div>
            <div class="input-group">
                <input type="text" id="filenameInput" placeholder="저장할 파일명 (선택사항, 비워두면 자동 지정)">
            </div>
            <div id="status">대기 중... URL을 입력하고 다운로드를 클릭하세요.</div>
            <div class="history" id="historySection" style="display:none;">
                <h3>📁 다운로드 완료</h3>
                <div id="historyList"></div>
            </div>
        </div>
        <div class="footer">클라우드 배포 · 어디서나 접속 가능</div>
    </div>
    <script>
        const urlInput = document.getElementById('urlInput');
        const filenameInput = document.getElementById('filenameInput');
        const downloadBtn = document.getElementById('downloadBtn');
        const statusDiv = document.getElementById('status');
        const historySection = document.getElementById('historySection');
        const historyList = document.getElementById('historyList');

        urlInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') startDownload(); });

        async function startDownload() {
            const url = urlInput.value.trim();
            if (!url) { statusDiv.textContent = '⚠️ URL을 입력해주세요.'; statusDiv.className = 'error'; return; }

            const filename = filenameInput.value.trim();
            downloadBtn.disabled = true;
            statusDiv.innerHTML = '<span class="spinner"></span> 다운로드 중... 페이지를 분석하고 있습니다. (30초~1분 소요)';
            statusDiv.className = 'loading';

            try {
                // 1단계: 영상 URL 추출
                let body = 'url=' + encodeURIComponent(url);
                if (filename) body += '&filename=' + encodeURIComponent(filename);
                const resp = await fetch('/extract', { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body });
                const data = await resp.json();

                if (!data.success) {
                    statusDiv.textContent = '❌ ' + data.message;
                    statusDiv.className = 'error';
                    downloadBtn.disabled = false;
                    return;
                }

                // 2단계: 파일 다운로드 (브라우저에서 직접)
                statusDiv.innerHTML = '<span class="spinner"></span> 파일 다운로드 중...';
                const dlResp = await fetch('/proxy-download?video_url=' + encodeURIComponent(data.video_url) + '&filename=' + encodeURIComponent(data.filename));
                if (!dlResp.ok) throw new Error('다운로드 실패');

                const blob = await dlResp.blob();
                const a = document.createElement('a');
                a.href = URL.createObjectURL(blob);
                a.download = data.filename;
                a.click();
                URL.revokeObjectURL(a.href);

                statusDiv.textContent = '✅ 다운로드 완료: ' + data.filename;
                statusDiv.className = 'success';
                addHistory(data.filename);
                urlInput.value = '';
            } catch (e) {
                statusDiv.textContent = '❌ 오류: ' + e.message;
                statusDiv.className = 'error';
            }
            downloadBtn.disabled = false;
            urlInput.focus();
        }

        function addHistory(filename) {
            historySection.style.display = 'block';
            const item = document.createElement('div');
            item.className = 'history-item';
            item.innerHTML = '<span class="icon">🎬</span><span class="name">' + filename + '</span>';
            historyList.prepend(item);
        }
    </script>
</body>
</html>"""


@app.route("/")
def index():
    return HTML_PAGE


@app.route("/extract", methods=["POST"])
def extract():
    url = request.form.get("url", "").strip()
    custom_name = request.form.get("filename", "").strip()

    if not url:
        return jsonify({"success": False, "message": "URL이 비어있습니다."})

    try:
        print(f"\n🔽 추출 요청: {url}")
        info = extract_video_url_from_page(url)

        if not info["type"]:
            return jsonify({"success": False, "message": "영상/이미지를 찾을 수 없습니다."})

        base_name = sanitize_filename(custom_name) if custom_name else sanitize_filename(info["title"])

        if info["type"] == "video" and info["video_url"]:
            filename = f"{base_name}.mp4"
            return jsonify({
                "success": True,
                "message": f"영상 발견: {info['title']}",
                "video_url": info["video_url"],
                "filename": filename,
            })
        else:
            return jsonify({"success": False, "message": "영상을 추출할 수 없습니다."})

    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.route("/proxy-download")
def proxy_download():
    """영상 URL을 프록시하여 사용자 브라우저로 다운로드합니다."""
    video_url = request.args.get("video_url", "")
    filename = request.args.get("filename", "video.mp4")

    if not video_url:
        return "URL 없음", 400

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.xiaohongshu.com/",
    }

    def generate():
        with req_lib.get(video_url, headers=headers, stream=True, timeout=120) as r:
            r.raise_for_status()
            for chunk in r.iter_content(chunk_size=8192):
                yield chunk

    return Response(
        generate(),
        content_type="video/mp4",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
