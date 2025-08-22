# fanza_client.py
import os, random, requests

API = "https://api.dmm.com/affiliate/v3/ItemList"

API_ID = os.getenv("FANZA_API_ID", "").strip()
AFF_ID = os.getenv("FANZA_AFFILIATE_ID", "").strip()

if not API_ID or not AFF_ID:
    raise RuntimeError(
        "FANZA_API_ID / FANZA_AFFILIATE_ID が未設定です。\n"
        "GitHub → Settings → Secrets and variables → Actions → Secrets に登録してください。"
    )

# 素人フロア固定
COMMON = {
    "api_id": API_ID,
    "affiliate_id": AFF_ID,
    "site": "FANZA",
    "service": "digital",
    "floor": "videoc",   # ← 素人
    "output": "json",
}

KEYWORD = "素人"
ALLOWED_GENRES = {g.strip() for g in os.getenv("GENRE_NAMES", "").split(",") if g.strip()}

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

    # 任意：ジャンル名で絞る
    if ALLOWED_GENRES:
        def ok(it):
            genres = (((it or {}).get("iteminfo") or {}).get("genre") or [])
            names = { (g or {}).get("name") for g in genres if isinstance(g, dict) }
            return bool(ALLOWED_GENRES & names)
        items = [x for x in items if ok(x)]
    return items

def _aff_link(url: str) -> str:
    if not url:
        return url
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

def _extract_first_image_from_any(sample_image_url_field) -> list[str]:
    """
    FANZAは sampleImageURL が dict/list/str いずれでも来る。
    - dict: {"sample_s": [...], "sample_l": [...]} など
    - list: ["https://...jpg", ...]
    - str : "https://...jpg"
    これらから**配列**を組み立てて返す（重複は除外）。
    """
    urls: list[str] = []
    v = sample_image_url_field
    if not v:
        return urls

    def push(u):
        if isinstance(u, str) and u and u not in urls:
            urls.append(u)

    if isinstance(v, str):
        push(v)
    elif isinstance(v, (list, tuple)):
        for u in v:
            push(u)
    elif isinstance(v, dict):
        # よくあるキー：sample_s, sample_l, image, images
        for key in ("sample_s", "sample_l", "image", "images", "list", "large", "small"):
            vv = v.get(key)
            if isinstance(vv, str):
                push(vv)
            elif isinstance(vv, (list, tuple)):
                for u in vv:
                    push(u)
            # 値がさらに辞書なら、その中も軽く探る
            elif isinstance(vv, dict):
                for w in vv.values():
                    if isinstance(w, str):
                        push(w)
                    elif isinstance(w, (list, tuple)):
                        for u in w:
                            push(u)
    return urls

def extract_fields(item: dict) -> dict:
    title = item.get("title")
    cid = item.get("content_id") or item.get("product_id") or title
    url = item.get("URL") or item.get("affiliateURL") or item.get("url")
    url = _aff_link(url)

    # サンプル動画
    sample = (
        item.get("sampleMovieURL")
        or item.get("sampleMovieUrl")
        or item.get("sampleMovie")
        or None
    )

    # 旧ポスター系（後方互換で残す）
    images = item.get("imageURL") or item.get("image") or {}
    poster = images.get("large") if isinstance(images, dict) else images
    poster = poster or (images.get("list") if isinstance(images, dict) else poster) or (images.get("small") if isinstance(images, dict) else poster)

    # サンプル画像の配列を**正規化**して取り出す
    sample_images = []
    # 代表的：sampleImageURL フィールド
    for key in ("sampleImageURL", "sampleImageUrl", "sampleImage", "sampleImages"):
        arr = _extract_first_image_from_any(item.get(key))
        if arr:
            sample_images.extend(arr)
    # 重複除去
    sample_images = list(dict.fromkeys(sample_images))

    return {
        "content_id": cid,
        "title": title,
        "link": url,
        "sample_movie": sample,
        "poster": poster,
        "sample_images": sample_images,  # ← ここを app.py が使う（先頭＝1枚目）
    }
