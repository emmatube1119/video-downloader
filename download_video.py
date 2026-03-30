"""
영상 다운로드 도구
==================
샤오홍슈(레드노트), 테무 등 다양한 플랫폼의 영상을 다운로드합니다.
Playwright로 브라우저를 열어 영상 URL을 추출한 뒤 다운로드합니다.

사용법:
    python download_video.py <영상_URL> [저장_폴더] [--name 파일명]

예시:
    python download_video.py https://www.rednote.com/explore/... outcome
    python download_video.py https://www.rednote.com/explore/... outcome --name 내영상
"""

import sys
import os
import re
import json
import requests
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright


def normalize_url(url: str) -> str:
    """rednote.com 등 모바일/단축 URL을 xiaohongshu.com 데스크탑 원본 URL로 변환합니다."""
    url = url.replace("www.rednote.com", "www.xiaohongshu.com").replace("rednote.com", "www.xiaohongshu.com")
    
    # xhslink, v.xiaohongshu.com 등 모바일 공유 링크인 경우
    if "xhslink.com" in url or "v.xiaohongshu.com" in url or "/discovery/item/" in url:
        try:
            # 리다이렉트를 추적하여 최종 URL 확보
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            r = requests.get(url, headers=headers, allow_redirects=True, timeout=15)
            final_url = r.url
            
            # /item/ 또는 /explore/ 뒤의 노트 ID 추출
            m = re.search(r'(?:item|explore)/([a-zA-Z0-9]+)', final_url)
            if m:
                note_id = m.group(1)
                # 데스크탑 전용 깔끔한 주소로 강제 조립
                return f"https://www.xiaohongshu.com/explore/{note_id}"
            else:
                return final_url
        except Exception as e:
            print(f"⚠️ 모바일 링크 원본 추적 실패: {e}")
            pass
            
    return url


def extract_video_url_from_page(url: str) -> dict:
    """Playwright로 페이지를 열어 영상/이미지 정보를 추출합니다.

    Returns:
        dict: {
            'title': str,
            'type': 'video' | 'image',
            'video_url': str (영상인 경우),
            'image_urls': list[str] (이미지인 경우),
        }
    """
    url = normalize_url(url)
    result = {"title": "", "type": "", "video_url": "", "image_urls": []}
    video_urls_found = []

    # --- 1단계: yt-dlp를 활용한 글로벌 표준 파싱 (특정 도메인은 제외하고 브라우저 파싱으로 직행) ---
    exclude_domains = ["xiaohongshu.com", "xhslink.com", "taobao.com", "1688.com", "temu.com"]
    if not any(domain in url for domain in exclude_domains):
        try:
            import yt_dlp
            print(f"🔍 범용 라이브러리(yt-dlp)로 분석 시도 중...")
            ydl_opts = {
                "quiet": True,
                "noplaylist": True,
                "format": "best[ext=mp4]/best", # 단일 파일 형태(비디오+오디오 통합) 최우선
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info and info.get("url"):
                    print("✅ 범용 라이브러리 분석 성공!")
                    result["title"] = info.get("title", "untitled")
                    result["type"] = "video"
                    result["video_url"] = info.get("url")
                    result["extractor"] = "ytdlp"
                    return result
        except Exception as e:
            print(f"⚠️ yt-dlp 파싱 실패, 브라우저 스니핑으로 전환합니다: {e}")
            pass

    # --- 2단계: 브라우저 자동화(Playwright) 및 네트워크 스니핑 (샤오홍슈, 타오바오 등) ---
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            locale="ko-KR",
        )
        page = context.new_page()

        # 네트워크 요청에서 영상 URL 수집 (강력한 스니핑)
        def on_response(response):
            try:
                content_type = response.headers.get("content-type", "").lower()
                req_url = response.url.lower()
                
                # 비디오 형식이나 확장자를 가진 모든 트래픽 감청
                if "video" in content_type or ".mp4" in req_url or "sns-video" in req_url or ".m3u8" in req_url:
                    # 너무 짧거나 쓸모없는 리소스 제외
                    if "video_urls_found" not in locals(): pass
                    video_urls_found.append(response.url)
            except Exception:
                pass

        page.on("response", on_response)

        print(f"🌐 브라우저 분석 중: {url}")
        try:
            # 샤오홍슈 모바일 단축링크(xhslink) 등은 리다이렉트를 기다려야 하므로 domcontentloaded 유지 
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            
            # 페이지가 완전히 로딩되고 XHR 요청이 끝날 때까지 조금 더 대기 (쇼핑몰 동영상 로딩용)
            page.wait_for_timeout(4000)
        except Exception:
            # 타임아웃이어도 계속 진행 (이미 스니핑된 데이터가 있을 수 있음)
            pass

        # 방법 1: __INITIAL_STATE__ 에서 추출
        try:
            state_json = page.evaluate("""() => {
                if (window.__INITIAL_STATE__) {
                    return JSON.stringify(window.__INITIAL_STATE__);
                }
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

                    # 영상 확인
                    video = note.get("video", {})
                    if video:
                        result["type"] = "video"
                        # media.stream 에서 URL 추출
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
                        # consumer.originVideoKey 백업
                        if not best_url:
                            consumer = video.get("consumer", {})
                            origin_key = consumer.get("originVideoKey", "")
                            if origin_key:
                                best_url = f"https://sns-video-bd.xhscdn.com/{origin_key}"
                        result["video_url"] = best_url
                    else:
                        # 이미지 노트
                        result["type"] = "image"
                        img_list = note.get("imageList", [])
                        for img in img_list:
                            url_default = img.get("urlDefault", "")
                            url_pre = img.get("urlPre", "")
                            info_list = img.get("infoList", [])
                            # 가장 큰 이미지 URL
                            best_img = url_default or url_pre
                            if info_list:
                                best_img = info_list[-1].get("url", best_img)
                            if best_img:
                                if best_img.startswith("//"):
                                    best_img = "https:" + best_img
                                result["image_urls"].append(best_img)
        except Exception as e:
            print(f"  __INITIAL_STATE__ 파싱 실패: {e}")

        # 방법 2: 네트워크에서 캡처된 영상 URL 사용 (방법1 실패 시)
        if result["type"] == "video" and not result["video_url"] and video_urls_found:
            result["video_url"] = video_urls_found[0]
        elif not result["type"] and video_urls_found:
            result["type"] = "video"
            result["video_url"] = video_urls_found[0]

        # 방법 3: video 태그에서 직접 추출 (쇼핑몰 대응)
        if result["type"] == "video" and not result["video_url"]:
            try:
                video_src = page.evaluate("""() => {
                    const video = document.querySelector('video');
                    if (video) {
                        return video.src || video.querySelector('source')?.src || '';
                    }
                    return '';
                }""")
                if video_src and video_src.startswith("http"):
                    result["video_url"] = video_src
            except Exception:
                pass
                
        # 만약 타입이 지정되지 않았지만 스니핑으로 찾아놓은 비디오가 있다면 강제 할당
        if not result["type"] and video_urls_found:
            result["type"] = "video"
            result["video_url"] = video_urls_found[0]

        # 타이틀 백업
        if not result["title"]:
            try:
                result["title"] = page.title() or "untitled"
            except Exception:
                result["title"] = "untitled"

        browser.close()

    return result


def sanitize_filename(name: str) -> str:
    """파일명에 사용할 수 없는 문자를 제거합니다."""
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = name.strip()
    return name[:100] if name else "untitled"


# 다운로드 진행률 전역 상태 (웹 GUI에서 참조)
progress_info = {
    "status": "idle", # idle, extracting, downloading, done
    "percent": 0,
    "downloaded_mb": 0.0,
    "total_mb": 0.0
}

def unique_filepath(filepath: str) -> str:
    """파일이 이미 존재하면 _1, _2... 을 붙여서 고유한 경로를 반환합니다."""
    if not os.path.exists(filepath):
        return filepath
    base, ext = os.path.splitext(filepath)
    counter = 1
    while os.path.exists(f"{base}_{counter}{ext}"):
        counter += 1
    return f"{base}_{counter}{ext}"


def download_file(url: str, filepath: str):
    """URL에서 파일을 다운로드합니다."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.xiaohongshu.com/",
    }
    with requests.get(url, headers=headers, stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        downloaded = 0
        
        progress_info["status"] = "downloading"
        progress_info["total_mb"] = total / 1024 / 1024 if total > 0 else 0.0

        with open(filepath, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
                downloaded += len(chunk)
                progress_info["downloaded_mb"] = downloaded / 1024 / 1024
                
                if total > 0:
                    pct = downloaded / total * 100
                    progress_info["percent"] = int(pct)
                    print(f"\r  📥 다운로드 중... {pct:.0f}% ({downloaded // 1024}KB / {total // 1024}KB)", end="", flush=True)
        print()


def download_video(url: str, output_dir: str = "outcome", custom_name: str = ""):
    """주어진 URL에서 영상/이미지를 다운로드합니다.

    Args:
        url: 영상 페이지 URL
        output_dir: 저장할 폴더 경로
        custom_name: 사용자 지정 파일명 (확장자 제외). 비어있으면 원본 제목 사용.
    """
    os.makedirs(output_dir, exist_ok=True)

    print(f"🔽 다운로드 시작: {url}")
    print(f"📂 저장 위치: {output_dir}")
    if custom_name:
        print(f"📝 파일명: {custom_name}")
    print("-" * 50)

    info = extract_video_url_from_page(url)

    if not info["type"]:
        print("❌ 영상/이미지를 찾을 수 없습니다.")
        return False

    # 파일명 결정: 사용자 지정 > 원본 제목
    base_name = sanitize_filename(custom_name) if custom_name else sanitize_filename(info["title"])

    if info["type"] == "video":
        if not info["video_url"]:
            print("❌ 영상 URL을 추출할 수 없습니다.")
            progress_info["status"] = "idle"
            return False
        filepath = unique_filepath(os.path.join(output_dir, f"{base_name}.mp4"))
        print(f"🎬 영상 발견: {info['title']}")
        print(f"  URL: {info['video_url'][:100]}...")
        download_file(info["video_url"], filepath)
        print(f"✅ 저장 완료: {filepath}")

    elif info["type"] == "image":
        print(f"🖼️ 이미지 {len(info['image_urls'])}장 발견: {info['title']}")
        for i, img_url in enumerate(info["image_urls"]):
            ext = ".jpg"
            if ".png" in img_url:
                ext = ".png"
            elif ".webp" in img_url:
                ext = ".webp"
            filepath = unique_filepath(os.path.join(output_dir, f"{base_name}_{i+1}{ext}"))
            print(f"  [{i+1}/{len(info['image_urls'])}] 다운로드 중...")
            download_file(img_url, filepath)
            print(f"  ✅ 저장: {filepath}")

    progress_info["status"] = "done"
    return True


def main():
    if len(sys.argv) < 2:
        print("=" * 50)
        print("  영상 다운로드 도구")
        print("=" * 50)
        print()
        print("사용법: python download_video.py <URL> [저장폴더] [--name 파일명]")
        print()
        print("지원 플랫폼: 샤오홍슈(레드노트), 기타")
        print()
        print("예시:")
        print("  python download_video.py https://www.rednote.com/explore/...")
        print("  python download_video.py https://www.rednote.com/explore/... outcome --name 내영상")
        sys.exit(1)

    video_url = sys.argv[1]
    out_dir = "outcome"
    custom_name = ""

    # 인자 파싱
    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == "--name" and i + 1 < len(args):
            custom_name = args[i + 1]
            i += 2
        else:
            out_dir = args[i]
            i += 1

    success = download_video(video_url, out_dir, custom_name)
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
