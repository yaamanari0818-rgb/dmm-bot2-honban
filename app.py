from __future__ import annotations
import os, tempfile, requests
from util import is_allowed_hour, load_posted_ids, add_posted_id, log
from twitter_client import TwitterClient
from fanza_client import pick_item, extract_fields
from amazon_client import pick_amazon_r18_url

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
    title, link, sample, poster = f["title"], f["link"], f["sample_movie"], f["poster"]

    tw = TwitterClient()

    media_path = None
    media_id = None
    if sample:
        media_path = download(sample, ".mp4")
    elif poster:
        media_path = download(poster, ".jpg")
    if media_path:
        media_id = tw.upload_media_chunked(media_path)

    main_text = build_main_tweet(is_new)
    res = tw.post_tweet(main_text, media_ids=[media_id] if media_id else None)
    tweet_id = res.get("id_str")

    amazon = pick_amazon_r18_url()
    reply_text = build_reply(title, link, amazon)
    tw.post_tweet(reply_text, reply_to_status_id=tweet_id)

    add_posted_id(f["content_id"])
    log("posted:", f["content_id"], title)

if __name__ == "__main__":
    main()
