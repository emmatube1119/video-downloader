import os, sys, json, re, threading, webbrowser, requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs, quote

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = "outcome"
PORT = int(os.environ.get("PORT", 8085))

from download_video import init_prog, set_prog, get_prog, download_video_and_info, progress_info
from coupang_api import search_products

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Download Flow v25.0</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;500;700&display=swap');
        body { background: linear-gradient(135deg, #fdfcfb 0%, #e2d1c3 100%); color: #475569; font-family: 'Outfit', sans-serif; padding: 40px; min-height: 100vh; }
        .app-container { max-width: 650px; margin: 0 auto; background: rgba(255, 255, 255, 0.85); backdrop-filter: blur(15px); border-radius: 30px; padding: 40px; box-shadow: 0 25px 60px rgba(0,0,0,0.08); border: 1px solid rgba(255,255,255,0.5); }
        h1 { text-align: center; color: #64748b; font-weight: 700; font-size: 2rem; margin-bottom: 30px; letter-spacing: -1px; }
        .input-box { width: calc(100% - 30px); padding: 18px; border-radius: 20px; border: 2px solid #e2e8f0; background: #fff; color: #1e293b; font-size: 1.05rem; transition: 0.3s; margin-bottom: 15px; outline: none; }
        .input-box:focus { border-color: #cbd5e1; box-shadow: 0 0 15px rgba(0,0,0,0.03); }
        .btn-add { width: 100%; padding: 16px; border-radius: 20px; background: linear-gradient(to right, #6a11cb 0%, #2575fc 100%); color: white; border: none; font-weight: 700; cursor: pointer; font-size: 1.1rem; box-shadow: 0 10px 30px rgba(106, 17, 203, 0.2); transition: 0.4s; }
        .btn-add:hover { transform: translateY(-3px); box-shadow: 0 15px 40px rgba(106, 17, 203, 0.3); }
        .task-card { background: white; padding: 22px; border-radius: 25px; margin-top: 20px; box-shadow: 0 10px 30px rgba(0,0,0,0.03); border: 1px solid #f1f5f9; position: relative; animation: slideUp 0.5s ease-out; }
        @keyframes slideUp { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        .progress-track { height: 12px; background: #f8fafc; border-radius: 10px; overflow: hidden; margin: 15px 0; border: 1px solid #f1f5f9; }
        .progress-fill { height: 100%; background: linear-gradient(90deg, #84fab0 0%, #8fd3f4 100%); transition: width 0.5s; border-radius: 10px; }
        .task-title { font-weight: 700; font-size: 1.1rem; color: #334155; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; width: 75%; }
        .badge-timer { position: absolute; top: 22px; right: 22px; background: #f1f5f9; color: #64748b; padding: 6px 12px; border-radius: 15px; font-size: 0.75rem; font-weight: 700; }
        .status-msg { font-size: 0.85rem; color: #94a3b8; margin-top: 5px; }
        .filesize { font-size: 0.82rem; font-weight: 700; color: #cbd5e1; }
        /* 쿠팡 추천 상품 */
        .rec-area { margin-top: 12px; padding-top: 12px; border-top: 1px dashed #e2e8f0; }
        .rec-label { font-size: 0.7rem; color: #94a3b8; margin-bottom: 8px; }
        .rec-item { display: flex; align-items: center; gap: 12px; padding: 10px; background: #fefce8; border-radius: 14px; margin-bottom: 8px; text-decoration: none; color: #334155; transition: 0.2s; border: 1px solid #fef08a; }
        .rec-item:hover { transform: translateY(-2px); box-shadow: 0 5px 15px rgba(0,0,0,0.05); }
        .rec-img { width: 55px; height: 55px; border-radius: 10px; object-fit: cover; }
        .rec-name { font-size: 0.82rem; font-weight: 500; line-height: 1.3; flex: 1; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
        .rec-price { font-size: 0.85rem; font-weight: 700; color: #dc2626; white-space: nowrap; }
    </style>
</head>
<body>
    <div class="app-container">
        <h1>&#10024; Download Flow</h1>
        <input type="text" id="urlInput" class="input-box" placeholder="&#128279; &#50668;&#44592;&#50640; &#47553;&#53356;&#47484; &#45347;&#50612;&#51452;&#49464;&#50836;..." autofocus>
        <input type="text" id="nameInput" class="input-box" placeholder="&#128221; &#50896;&#54616;&#45716; &#54028;&#51068;&#47749; (&#50630;&#51004;&#47732; &#51088;&#46041;)">
        <button class="btn-add" onclick="start()">&#128640; &#52628;&#44032;&#54616;&#44592;</button>
        <div id="list"></div>
    </div>
    <script>
        let tasks = {};
        let recCache = {};
        let clientId = localStorage.getItem('df_client_id');
        if(!clientId) { clientId = 'c_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9); localStorage.setItem('df_client_id', clientId); }
        function start() {
            const url = document.getElementById('urlInput').value.trim();
            const name = document.getElementById('nameInput').value.trim();
            if(!url) return;
            const tid = 't_' + Date.now();
            tasks[tid] = { status:'prep', percent:0, title:'&#48516;&#49437; &#51473;...', message:'&#51104;&#49884;&#47564; &#44592;&#45796;&#47140;&#51452;&#49464;&#50836;', elapsed:0, eta:'...', downloaded_mb:0, total_mb:0, keywords:'' };
            render();
            fetch('/download', { method:'POST', headers:{'Content-Type':'application/x-www-form-urlencoded'}, body:`url=${encodeURIComponent(url)}&filename=${encodeURIComponent(name)}&task_id=${tid}&client_id=${clientId}` });
            document.getElementById('urlInput').value = '';
            document.getElementById('nameInput').value = '';
        }
        setInterval(async () => {
            try {
                const r = await fetch('/progress?client_id=' + clientId); const d = await r.json();
                for(const [id, info] of Object.entries(d)) {
                    tasks[id] = info;
                    if(info.keywords && !recCache[id]) {
                        try {
                            const rr = await fetch('/recommend?keyword=' + encodeURIComponent(info.keywords));
                            recCache[id] = await rr.json();
                        } catch(e) { recCache[id] = []; }
                    }
                }
                render();
            } catch(e) {}
        }, 1500);

        function render() {
            const list = document.getElementById('list');
            Object.entries(tasks).reverse().forEach(([id, info]) => {
                let el = document.getElementById(id);
                if(!el) { el = document.createElement('div'); el.id = id; el.className = 'task-card'; list.prepend(el); }
                const done = info.status==='done'; const err = info.status==='error';
                const color = done?'#10b981':(err?'#ef4444':'#3b82f6');
                let recHTML = '';
                const recs = recCache[id] || [];
                if(recs.length > 0 && !err) {
                    recHTML = '<div class="rec-area"><div class="rec-label">&#127873; &#51060;&#47088; &#44148; &#50612;&#46524;&#49464;&#50836;?</div>';
                    for(const item of recs) {
                        recHTML += `<a href="${item.url}" target="_blank" class="rec-item">
                            <img src="${item.image}" class="rec-img" onerror="this.style.display='none'">
                            <span class="rec-name">${item.name}</span>
                            <span class="rec-price">${Number(item.price).toLocaleString()}&#50896;</span>
                        </a>`;
                    }
                    recHTML += '</div>';
                }
                let dlBtnHtml = '';
                if(done && info.title) {
                    dlBtnHtml = `<a href="/download_file?task_id=${id}" style="display:block; margin-top:12px; padding:12px; background:linear-gradient(90deg, #10b981, #34d399); color:white; border-radius:12px; text-decoration:none; font-weight:700; font-size:0.95rem; text-align:center; box-shadow:0 4px 10px rgba(16,185,129,0.3); transition:0.2s;">&#128229; 내 기기로 영상 파일 받기</a>`;
                }
                el.innerHTML = `
                    <div class="badge-timer">&#9201; ${info.elapsed}s | ${done?'OK':(info.eta||'...')}</div>
                    <div class="task-title">${info.title || '&#48516;&#49437; &#51473;...'}</div>
                    <div class="status-msg"><b style="color:${color}">${info.status.toUpperCase()}</b> | ${info.message}</div>
                    <div class="progress-track"><div class="progress-fill" style="width:${info.percent}%; ${done?'background:#10b981':''}"></div></div>
                    <div style="display:flex; justify-content:space-between;">
                        <span style="font-weight:700; color:${color}; font-size:0.9rem;">${info.percent}%</span>
                        <span class="filesize">${info.downloaded_mb}MB / ${info.total_mb}MB</span>
                    </div>
                    ${dlBtnHtml}
                    ${recHTML}
                `;
            });
        }
    </script>
</body>
</html>
"""

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer): daemon_threads = True

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_GET(self):
        if self.path.startswith("/progress"):
            cid = parse_qs(self.path.split("?",1)[1] if "?" in self.path else "").get("client_id",[""])[0]
            filtered = {k: v for k, v in progress_info.items() if v.get("client_id") == cid} if cid else progress_info
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(json.dumps(filtered).encode("utf-8")); return
        if self.path.startswith("/recommend"):
            kw = parse_qs(self.path.split("?",1)[1] if "?" in self.path else "").get("keyword",[""])[0]
            results = search_products(kw, limit=2)
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(json.dumps(results).encode("utf-8")); return
        if self.path.startswith("/download_file"):
            tid = parse_qs(self.path.split("?",1)[1] if "?" in self.path else "").get("task_id",[""])[0]
            info = progress_info.get(tid, {})
            title = info.get("title", "")
            if title:
                fp = os.path.join(OUTPUT_DIR, title)
                if os.path.exists(fp):
                    sz = os.path.getsize(fp)
                    self.send_response(200)
                    self.send_header("Content-Type", "video/mp4")
                    self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(title)}")
                    self.send_header("Content-Length", str(sz))
                    self.end_headers()
                    with open(fp, "rb") as f: self.wfile.write(f.read())
                    return
            self.send_response(404); self.end_headers(); return
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
        self.wfile.write(HTML_PAGE.encode("utf-8"))

    def do_POST(self):
        if self.path == "/download":
            body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8")
            params = parse_qs(body)
            url, name, tid, cid = params.get("url",[""])[0], params.get("filename",[""])[0], params.get("task_id",[""])[0], params.get("client_id",[""])[0]
            init_prog(tid); set_prog(tid, "client_id", cid); self.send_response(200); self.end_headers()
            def run():
                try: download_video_and_info(url, task_id=tid, out_dir=OUTPUT_DIR, custom_name=name)
                except Exception as e: set_prog(tid, "status", "error"); set_prog(tid, "message", str(e))
            threading.Thread(target=run, daemon=True).start()

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True); server = ThreadedHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"PASTEL-FLOW: http://localhost:{PORT}")
    try:
        if not os.environ.get("RENDER"): webbrowser.open(f"http://localhost:{PORT}")
    except: pass
    server.serve_forever()

if __name__ == "__main__": main()
