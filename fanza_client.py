# fanza_client.py
import os, random, requests

# --- FANZA API設定 ---
API = "https://api.dmm.com/affiliate/v3/ItemList"

API_ID = os.getenv("FANZA_API_ID", "").strip()
AFF_ID = os.getenv("FANZA_AFFILIATE_ID", "").strip()

if not API_ID or not AFF_ID:
    raise RuntimeError(
        "FANZA_API_ID / FANZA_AFFILIATE_ID が未設定です。\n"
        "GitHub → Settings → Secrets and variables → Actions → Secrets に登録してください。"
    )

# --- 素人フロア固定 ---
COMMON = {
    "api_id": API_ID,
    "affiliate_id": AFF_ID,
    "site": "FANZA",
    "service": "digital",
    "floor": "videoc",   # ← 素人専用フロア
    "output": "json",
}

# 検索キーワード（保険として残す）
KEYWORD = "素人"

# 任意ジャンルフィルタ（例: "ギャル,人妻"）
ALLOWED_GENRES = {g.strip() for g in os.getenv("GENRE_NAMES", "").split(",") if g.strip()}

# --- API呼び出し ---
def _call(params: dict) -> list[dict]:
    q = COMMON | params
    try:
        r = requests.get(API, params=q, timeout=30)
        if r.status_code >= 400:
            raise RuntimeError(f"DMM APIエラー {r.status_code}: {r.text[:300]}")
        js = r.json()
    except Exception as e:
        raise RuntimeError(f"DMM API呼び出し失敗: {e}")
    items = js.get("result", {}).get("items", [])

    # ジャンルフィルタ適用（環境変数 GENRE_NAMES 指定時のみ）
    if ALLOWED_GENRES:
        def ok(it):
            genres = (((it or {}).get("iteminfo") or {}).get("genre") or [])
            names = { (g or {}).get("name") for g in genres if isinstance(g, dict) }
            return bool(ALLOWED_GENRES & names)
        items = [x for x in items if ok(x)]
    return items

# --- アフィリエイトリンク加工 ---
def _aff_link(url: str) -> str:
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}utm_source=twitter&utm_medium=social&utm_campaign=bot"

# --- 新着 & 人気取得 ---
def fetch_newest(limit=50) -> list[dict]:
    return _call({"keyword": KEYWORD, "sort": "date", "hits": limit})

def fetch_popular(limit=50) -> list[dict]:
    return _call({"keyword": KEYWORD, "sort": "rank", "hits": limit})

# --- 投稿候補を選ぶ ---
def pick_item(posted_ids: set[str]) -> tuple[dict | None, bool]:
    newest = [x for x in fetch_newest() if x.get("content_id") not in posted_ids]
    if newest:
        return newest[0], True
    pop = [x for x in fetch_popular() if x.get("content_id") not in posted_ids]
    if pop:
        return random.choice(pop), False
    return None, False

# --- 必要な情報を抽出 ---
def extract_fields(item: dict) -> dict:
    title = item.get("title")
    cid = item.get("content_id") or item.get("product_id") or title
    url = item.get("URL") or item.get("affiliateURL") or item.get("url")
    url = _aff_link(url)
    sample = (
        item.get("sampleMovieURL")
        or item.get("sampleMovieUrl")
        or item.get("sampleMovie")
        or None
    )
    images = item.get("imageURL") or item.get("image") or {}
    poster = images.get("large") or images.get("list") or images.get("small")
    return {
        "content_id": cid,
        "title": title,
        "link": url,
        "sample_movie": sample,
        "poster": poster,
    }
