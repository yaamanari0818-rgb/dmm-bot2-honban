import os, random, requests

API = "https://api.dmm.com/affiliate/v3/ItemList"

API_ID = os.environ["FANZA_API_ID"]
AFF_ID = os.environ["FANZA_AFFILIATE_ID"]

# ★ ここがポイント：floor を 'videoc'（素人）に固定します
# 参考：フロアコード 'videoc' = 素人。'videoa' は一般的なアダルト動画。 
# （公式フロアAPIのレスポンス例・技術記事に 'videoc' が素人として掲載） 
# https://affiliate.dmm.com/api/v3/floorlist.html ほか
COMMON = {
    "api_id": API_ID,
    "affiliate_id": AFF_ID,
    "site": "FANZA",
    "service": "digital",
    "floor": "videoc",   # ← 素人フロア固定
    "output": "json",
}

# キーワードは保険として残します（なくてもOK）
KEYWORD = "素人"

# 追加：サブジャンル名でさらに絞り込みたい場合は環境変数 GENRE_NAMES に
# 「ギャル,人妻」のようにカンマ区切りで設定してください（空なら全件許可）
ALLOWED_GENRES = {g.strip() for g in os.getenv("GENRE_NAMES", "").split(",") if g.strip()}

def _call(params: dict) -> list[dict]:
    q = COMMON | params
    r = requests.get(API, params=q, timeout=30)
    r.raise_for_status()
    js = r.json()
    items = js.get("result", {}).get("items", [])
    # サブジャンル名フィルタ（任意）
    if ALLOWED_GENRES:
        def ok(it):
            genres = (((it or {}).get("iteminfo") or {}).get("genre") or [])
            names = { (g or {}).get("name") for g in genres if isinstance(g, dict) }
            return bool(ALLOWED_GENRES & names)
        items = [x for x in items if ok(x)]
    return items

def _aff_link(url: str) -> str:
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}utm_source=twitter&utm_medium=social&utm_campaign=bot"

def fetch_newest(limit=50) -> list[dict]:
    return _call({"keyword": KEYWORD, "sort": "date", "hits": limit})

def fetch_popular(limit=50) -> list[dict]:
    return _call({"keyword": KEYWORD, "sort": "rank", "hits": limit})

def pick_item(posted_ids: set[str]) -> tuple[dict | None, bool]:
    # 1) 新作優先（未出のみ）
    newest = [x for x in fetch_newest() if x.get("content_id") not in posted_ids]
    if newest:
        return newest[0], True
    # 2) 人気順から未出をランダム
    pop = [x for x in fetch_popular() if x.get("content_id") not in posted_ids]
    if pop:
        return random.choice(pop), False
    return None, False

def extract_fields(item: dict) -> dict:
    title = item.get("title")
    cid = item.get("content_id") or item.get("product_id") or title
    url = item.get("URL") or item.get("affiliateURL") or item.get("url")
    url = _aff_link(url)
    # sampleムービー（あれば優先）
    sample = (item.get("sampleMovieURL") or item.get("sampleMovieUrl") or item.get("sampleMovie") or None)
    # サムネ（動画が無いとき画像で代替）
    images = item.get("imageURL") or item.get("image") or {}
    poster = images.get("large") or images.get("list") or images.get("small")
    return {"content_id": cid, "title": title, "link": url, "sample_movie": sample, "poster": poster}
