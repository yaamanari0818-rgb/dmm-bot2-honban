# app.py（完全置き換え版）
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
    """
    FANZAの sampleMovieURL は文字列/辞書/配列のいずれか。
    - 文字列: そのまま返す
    - 辞書: size_720_480 > size_644_414 > size_560_360 > size_476_306 の順で選ぶ
    - 配列: 先頭から順に再帰的に判定して最初に見つかったものを返す
    """
    if not sample:
        return None
    if isinstance(sample, str):
        return sample
    if isinstance(sample, dict):
        for key in ("size_720_480", "size_644_414", "size_560_360", "size_476_306"):
            url = sample.get(key)
            if isinstance(url, str) and url:
                return url
        # 念のため他の値が文字列なら拾う
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
    return " ".join(tags + ["\n" + FIXED_TEXT])

def build_reply(title: str, fanza_url: str, amazon_url: str | None) -> str:
    parts = [title, fanza_url]
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
    title, link, sample_raw, poster = f["title"], f["link"], f["sample_movie"], f["poster"]

    tw = TwitterClient()

    media_path = None
    media_id = None

    # まずはサンプル動画を優先
    sample_url = choose_sample_url(sample_raw)
    try_urls = []
    if sample_url:
        try_urls.append(("video", sample_url, ".mp4"))
    if poster:
        # posterはURL文字列の想定だが、もし辞書なら適当に大きめを選ぶ
        if isinstance(poster, dict):
            poster_url = poster.get("large") or poster.get("list") or poster.get("small")
        else:
            poster_url = poster
        if poster_url:
            try_urls.append(("image", poster_url, ".jpg"))

    # ダウンロード試行（動画→ダメなら画像）
    for kind, url, suffix in try_urls:
        try:
            media_path = download(url, suffix)
            media_id = tw.upload_media_chunked(media_path)
            log(f"media upload ok: {kind} {url}")
            break
        except Exception as e:
            log(f"media download/upload failed ({kind}): {e}")

    main_text = build_main_tweet(is_new)
    res = tw.post_tweet(main_text, media_ids=[media_id] if media_id else None)
    tweet_id = res.get("id_str")

    # Amazonリンク（PA-APIなし運用：AMAZON_R18_URLS からランダム）
    from amazon_client import pick_amazon_r18_url
    amazon = pick_amazon_r18_url()

    reply_text = build_reply(title, link, amazon)
    tw.post_tweet(reply_text, reply_to_status_id=tweet_id)

    add_posted_id(f["content_id"])
    log("posted:", f["content_id"], title)

if __name__ == "__main__":
    main()
