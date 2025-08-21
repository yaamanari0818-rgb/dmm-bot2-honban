# twitter_client.py（完全置き換え）
import os, time, mimetypes
import requests
from requests_oauthlib import OAuth1

API_BASE = "https://api.twitter.com/1.1"
UPLOAD_BASE = "https://upload.twitter.com/1.1"  # ← 重要：メディアはこっち

def _must_env(name: str) -> str:
    v = os.getenv(name, "").strip()
    if not v:
        raise RuntimeError(f"環境変数 {name} が未設定です（GitHub > Settings > Secrets で設定）。")
    return v

class TwitterClient:
    def __init__(self):
        self.auth = OAuth1(
            _must_env("X_API_KEY"),
            _must_env("X_API_SECRET"),
            _must_env("X_ACCESS_TOKEN"),
            _must_env("X_ACCESS_SECRET"),
        )
        self.sensitive = os.getenv("SENSITIVE_MEDIA", "true").lower() == "true"

    # ---- media/upload (chunked) ----
    def upload_media_chunked(self, filepath: str, media_type: str | None = None) -> str:
        size = os.path.getsize(filepath)
        media_type = media_type or (mimetypes.guess_type(filepath)[0] or "application/octet-stream")
        # 画像/動画でメディアカテゴリを付ける（推奨）
        if media_type.startswith("video/"):
            media_category = "tweet_video"
        elif media_type.startswith("image/"):
            media_category = "tweet_image"
        else:
            media_category = None

        init_data = {
            "command": "INIT",
            "media_type": media_type,
            "total_bytes": size,
        }
        if media_category:
            init_data["media_category"] = media_category

        r = requests.post(
            f"{UPLOAD_BASE}/media/upload.json",
            auth=self.auth,
            data=init_data,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"[INIT] media/upload 失敗 {r.status_code}: {r.text}")
        media_id = r.json()["media_id_string"]

        # APPEND
        seg = 0
        chunk_size = 4 * 1024 * 1024
        with open(filepath, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                files = {"media": chunk}
                r = requests.post(
                    f"{UPLOAD_BASE}/media/upload.json",
                    auth=self.auth,
                    data={"command": "APPEND", "media_id": media_id, "segment_index": seg},
                    files=files,
                )
                if r.status_code >= 400:
                    raise RuntimeError(f"[APPEND] media/upload 失敗 {r.status_code}: {r.text}")
                seg += 1

        # FINALIZE
        r = requests.post(
            f"{UPLOAD_BASE}/media/upload.json",
            auth=self.auth,
            data={"command": "FINALIZE", "media_id": media_id},
        )
        if r.status_code >= 400:
            raise RuntimeError(f"[FINALIZE] media/upload 失敗 {r.status_code}: {r.text}")
        info = r.json()
        proc = info.get("processing_info", {})
        while proc.get("state") in {"pending", "in_progress"}:
            time.sleep(proc.get("check_after_secs", 3))
            q = requests.get(
                f"{UPLOAD_BASE}/media/upload.json",
                auth=self.auth,
                params={"command": "STATUS", "media_id": media_id},
            )
            if q.status_code >= 400:
                raise RuntimeError(f"[STATUS] media/upload 失敗 {q.status_code}: {q.text}")
            proc = q.json().get("processing_info", {})
            if proc.get("state") == "failed":
                raise RuntimeError(f"media processing failed: {proc}")
        return media_id

    def post_tweet(self, text: str, media_ids: list[str] | None = None, reply_to_status_id: str | None = None) -> dict:
        payload = {
            "status": text,
            "trim_user": True,
            "possibly_sensitive": self.sensitive,
        }
        if media_ids:
            payload["media_ids"] = ",".join(media_ids)
        if reply_to_status_id:
            payload["in_reply_to_status_id"] = reply_to_status_id
            payload["auto_populate_reply_metadata"] = True

        r = requests.post(f"{API_BASE}/statuses/update.json", auth=self.auth, data=payload)
        if r.status_code >= 400:
            # エラー理由を見やすく
            raise RuntimeError(f"[POST] statuses/update 失敗 {r.status_code}: {r.text}")
        return r.json()
