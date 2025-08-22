# app.py（1枚目画像を優先・モザイク・v2投稿・ハッシュタグは本文の一番下）
from __future__ import annotations
import os, tempfile, requests
from util import is_allowed_hour, load_posted_ids, add_posted_id, log
from twitter_client import TwitterClient
from fanza_client import pick_item, extract_fields

FIXED_TEXT = "作品詳細はコメ欄から↓"
BASE_HASHTAGS = ["#素人", "#AV"]
HASHTAGS_EXTRA = [t.strip() for t in os.getenv("HASHTAGS_EXTRA", "").split(',') if t.strip()]

def download(url: str, suffix: str) -> str:
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, 'wb') as f:
        f.write(r.content)
    return path

def choose_sample_url(sample) -> str | None:
    if not sample:
        return None
    if isinstance(sample, str):
        return sample
    if isinstance(sample, dict):
        for key in ("size_720_480", "size_644_414", "size_560_360", "size_476_306"):
            url = sample.get(key)
            if isinstance(url, str) and url:
                return url
        for v in sample.values():
            if isinstance(v, str) and v:
                return v
        return None
    if isinstance(sample, (list, tuple)):
        for s in sample:
            u = choose_sample_url(s)
            if u:
                return u
    return None

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
    title, link, sample_raw, poster, sample_images = (
        f["title"], f["link"], f["sample_movie"], f["poster"], f.get("sample_images") or []
    )

    tw = TwitterClient()

    media_path = None
    media_id = None

    # --- メディア選択方針 ---
    # 1) 動画があれば挑戦（WAFで弾かれやすいので後に回したい場合は順序を入替可）
    # 2) 画像は「サンプル画像配列の**1枚目**」を最優先
    # 3) 無ければポスター系にフォールバック
    try_urls = []

    # 画像（1枚目）
    first_image_url = None
    if sample_images:
        first_image_url = sample_images[0]
    elif poster:
        if isinstance(poster, dict):
            first_image_url = poster.get("large") or poster.get("list") or poster.get("small")
        else:
            first_image_url = poster

    if first_image_url:
        try_urls.append(("image", first_image_url, ".jpg"))

    # 動画（任意：必要なら画像の後ろに）
    sample_url = choose_sample_url(sample_raw)
    if sample_url:
        try_urls.append(("video", sample_url, ".mp4"))

    # ダウンロード＆（画像なら）モザイク → アップロード
    for kind, url, suffix in try_urls:
        try:
            media_path = download(url, suffix)

            if kind == "image":
                from censor import censor_image
                censored_path = media_path.replace(suffix, "_censored.jpg")
                if censor_image(media_path, censored_path):
                    media_path = censored_path  # 秘部モザイク適用時のみ差し替え

            media_id = tw.upload_media_chunked(media_path)  # v1.1 upload
            log(f"media upload ok: {kind} {url}")
            break
        except Exception as e:
            log(f"media download/upload failed ({kind}): {e}")

    main_text = build_main_tweet(is_new)

    # v2 で投稿
    res = tw.post_tweet_v2(main_text, media_ids=[media_id] if media_id else None)
    tweet_id = (res.get("data") or {}).get("id")
    if not tweet_id:
        log("tweet failed: no tweet_id")
        return

    # Amazonリンク（PA-APIなし運用：AMAZON_R18_URLS からランダム）
    from amazon_client import pick_amazon_r18_url
    amazon = pick_amazon_r18_url()

    reply_text = build_reply(title, link, amazon)
    tw.post_tweet_v2(reply_text, reply_to_tweet_id=tweet_id)

    add_posted_id(f["content_id"])
    log("posted:", f["content_id"], title)

if __name__ == "__main__":
    main()
