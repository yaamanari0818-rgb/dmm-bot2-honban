import os, random, requests

API = "https://api.dmm.com/affiliate/v3/ItemList"

API_ID = os.environ["FANZA_API_ID"]
AFF_ID = os.environ["FANZA_AFFILIATE_ID"]

COMMON = {
    "api_id": API_ID,
    "affiliate_id": AFF_ID,
    "site": "FANZA",
    "service": "digital",
    "floor": "videoa",
    "output": "json",
}

KEYWORD = "素人"

def _call(params: dict) -> list[dict]:
    q = COMMON | params
    r = requests.get(API, params=q, timeout=30)
    r.raise_for_status()
    js = r.json()
    return js.get("result", {}).get("items", [])

def _aff_link(url: str) -> str:
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}utm_source=twitter&utm_medium=social&utm_campaign=bot"

def fetch_newest(limit=50) -> list[dict]:
    return _call({"keyword": KEYWORD, "sort": "date", "hits": limit})

def fetch_popular(limit=50) -> list[dict]:
    return _call({"keyword": KEYWORD, "sort": "rank", "hits": limit})

def pick_item(posted_ids: set[str]) -> tuple[dict | None, bool]:
    newest = [x for x in fetch_newest() if x.get("content_id") not in posted_ids]
    if newest:
        return newest[0], True
    pop = [x for x in fetch_popular() if x.get("content_id") not in posted_ids]
    if pop:
        return random.choice(pop), False
    return None, False

def extract_fields(item: dict) -> dict:
    title = item.get("title")
    cid = item.get("content_id") or item.get("product_id") or title
    url = item.get("URL") or item.get("affiliateURL") or item.get("url")
    url = _aff_link(url)
    sample = (item.get("sampleMovieURL") or item.get("sampleMovieUrl") or item.get("sampleMovie") or None)
    images = item.get("imageURL") or item.get("image") or {}
    poster = images.get("large") or images.get("list") or images.get("small")
    return {"content_id": cid, "title": title, "link": url, "sample_movie": sample, "poster": poster}
