"""
쿠팡 파트너스 API 모듈 (HMAC-SHA256 인증 + 상품 검색 + 딥링크 생성)
"""
import hmac, hashlib, os, json, re
from time import gmtime, strftime
from urllib.parse import quote
from dotenv import load_dotenv

load_dotenv()

ACCESS_KEY = os.getenv("COUPANG_ACCESS_KEY", "")
SECRET_KEY = os.getenv("COUPANG_SECRET_KEY", "")
DOMAIN = "https://api-gateway.coupang.com"

def _generate_auth(method, url_path):
    """HMAC-SHA256 인증 헤더 생성"""
    path, *qs = url_path.split("?")
    query = qs[0] if qs else ""
    dt = strftime('%y%m%d', gmtime()) + 'T' + strftime('%H%M%S', gmtime()) + 'Z'
    msg = dt + method + path + query
    sig = hmac.new(SECRET_KEY.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"CEA algorithm=HmacSHA256, access-key={ACCESS_KEY}, signed-date={dt}, signature={sig}"

def search_products(keyword, limit=2):
    """키워드로 쿠팡 상품 검색 (추천용 1~2개)"""
    if not ACCESS_KEY or not SECRET_KEY or not keyword:
        return []
    try:
        import requests
        url_path = f"/v2/providers/affiliate_open_api/apis/openapi/v1/products/search?keyword={quote(keyword)}&limit={limit}"
        auth = _generate_auth("GET", url_path)
        r = requests.get(DOMAIN + url_path, headers={"Authorization": auth, "Content-Type": "application/json"}, timeout=5)
        if r.status_code != 200:
            return []
        data = r.json().get("data", {}).get("productData", [])
        results = []
        for item in data[:limit]:
            results.append({
                "name": item.get("productName", ""),
                "price": item.get("productPrice", 0),
                "image": item.get("productImage", ""),
                "url": item.get("productUrl", ""),  # 이미 딥링크 포함
                "rating": item.get("productRating", ""),
            })
        return results
    except Exception:
        return []

def extract_keywords(title):
    """영상 제목에서 추천 검색용 핵심 키워드 2~3개 추출"""
    if not title:
        return ""
    # 불용어 제거
    stopwords = {"the","a","an","is","are","was","were","be","been","being","have","has","had",
                 "do","does","did","will","would","shall","should","may","might","must","can","could",
                 "이","그","저","것","수","들","등","및","또","또는","의","를","에","에서","으로","로",
                 "과","와","한","할","하는","하고","하면","합니다","입니다","있는","없는","않은",
                 "I","my","me","you","your","we","our","they","their","he","she","it",
                 "ep","EP","vol","VOL","ft","FT","MV","mv","official","Official","video","Video",
                 "TikTok","tiktok","shorts","Shorts","youtube","YouTube","reels","Reels"}
    # 특수문자/괄호 내용 제거
    clean = re.sub(r'[\[\(【《].*?[\]\)】》]', '', title)
    clean = re.sub(r'[^\w\s가-힣]', ' ', clean)
    words = [w for w in clean.split() if len(w) > 1 and w.lower() not in stopwords]
    # 한글 키워드 우선, 최대 3개
    kr = [w for w in words if re.search(r'[가-힣]', w)]
    picked = kr[:3] if kr else words[:3]
    return " ".join(picked)
