# app.py（ジャケットのみタイプ）
from __future__ import annotations
import os, tempfile, requests
from util import is_allowed_hour, load_posted_ids, add_posted_id, log
from twitter_client import TwitterClient
from fanza_client import pick_item, extract_fields

# ===== 文面設定 =====
FIXED_TEXT = "作品詳細はコメ欄から↓"
BASE_HASHTAGS = ["#素人", "#AV"]
HASHTAGS_EXTRA = [t.strip() for t in os.getenv("HASHTAGS_EXTRA", "").split(',') if t.strip()]

# モザイクを使う/使わない（任意）：変数で切替可（既定 true）
MOSAIC_ENABLED = os.getenv("MOSAIC_ENABLED", "true").lower() == "true"

# ===== ユーティリティ =====
def download(url: str, suffix: str) -> str:
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, 'wb') as f:
        f.write(r.content)
    return path

def build_main_tweet(is_new: bool) -> str:
    tags = BASE_HASHTAGS + (HASHTAGS_EXTRA or [])
    if is_new:
        tags = ["#新着"] + tags
    # 本文の一番下（メディアの下）にハッシュタグ
    return FIXED_TEXT + "\n\n" + " ".join(tags)

def build_reply(title: str, fanza_url: str, amazon_url: str | None) -> str:
    parts = [
        f"👀{title}👇",
        fanza_url,
        "🔥おすすめのR18グッズはこちら🔥",
    ]
    if amazon_url:
        parts.append(amazon_url)
    return "\n".join(parts)

# ===== メイン =====
def main():
    if not is_allowed_hour():
        log("skip: not allowed hour (JST)")
        return

    posted = load_posted_ids()
    item, is_new = pick_item(posted)
    if not item:
        log("no candidate found")
        return

    f = extract_fields(item)
    title, link, poster = f["title"], f["link"], f["poster"]

    # --- ジャケットURLだけを使う ---
    poster_url = None
    if isinstance(poster, dict):
        poster_url = poster.get("large") or poster.get("list") or poster.get("small")
    elif isinstance(poster, str):
        poster_url = poster

    if not poster_url:
        log("no poster image found; skip this item")
        return

    tw = TwitterClient()

    # ダウンロード →（任意）モザイク → アップロード
    media_id = None
    try:
        media_path = download(poster_url, ".jpg")

        # 画像モザイク（有効時のみ）
        if MOSAIC_ENABLED:
            try:
                from censor import censor_image
                censored_path = media_path.replace(".jpg", "_censored.jpg")
                if censor_image(media_path, censored_path):
                    media_path = censored_path
            except Exception as e:
                log(f"censor skipped: {e}")

        media_id = tw.upload_media_chunked(media_path)  # v1.1 upload
        log(f"media upload ok: image {poster_url}")
    except Exception as e:
        log(f"media download/upload failed (image): {e}")

    # 本文（ハッシュタグは一番下）
    main_text = build_main_tweet(is_new)

    # v2 で投稿
    res = tw.post_tweet_v2(main_text, media_ids=[media_id] if media_id else None)
    tweet_id = (res.get("data") or {}).get("id")
    if not tweet_id:
        log("tweet failed: no tweet_id")
        return

    # リプ（タイトル + FANZA + グッズ）
    from amazon_client import pick_amazon_r18_url  # PA-API未使用のランダムURL運用
    amazon = pick_amazon_r18_url()
    reply_text = build_reply(title, link, amazon)
    tw.post_tweet_v2(reply_text, reply_to_tweet_id=tweet_id)

    add_posted_id(f["content_id"])
    log("posted:", f["content_id"], title)

if __name__ == "__main__":
    main()
