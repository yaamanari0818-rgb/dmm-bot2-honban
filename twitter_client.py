# twitter_client.py（v1.1: upload / v2: create tweet）
import os, time, mimetypes, json
import requests
from requests_oauthlib import OAuth1

API_V1 = "https://api.twitter.com/1.1"
API_V2 = "https://api.twitter.com/2"
UPLOAD_BASE = "https://upload.twitter.com/1.1"  # メディアはこっち

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
        # CloudflareやWAF対策：チャンク間に待機、サイズ調整できるように
        self.chunk_mb = max(1, int(os.getenv("UPLOAD_CHUNK_MB", "4")))  # 1〜4MB推奨
        self.append_pause = float(os.getenv("UPLOAD_APPEND_PAUSE_SEC", "0.4"))  # 連投間隔

    # ---- media/upload (chunked, v1.1) ----
    def upload_media_chunked(self, filepath: str, media_type: str | None = None) -> str:
        size = os.path.getsize(filepath)
        media_type = media_type or (mimetypes.guess_type(filepath)[0] or "application/octet-stream")
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

        r = requests.post(f"{UPLOAD_BASE}/media/upload.json", auth=self.auth, data=init_data)
        if r.status_code >= 400:
            raise RuntimeError(f"[INIT] media/upload 失敗 {r.status_code}: {r.text}")
        media_id = r.json()["media_id_string"]

        # APPEND
        seg = 0
        chunk_size = self.chunk_mb * 1024 * 1024
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
                # 連投しすぎ回避
                time.sleep(self.append_pause)

        # FINALIZE
        r = requests.post(f"{UPLOAD_BASE}/media/upload.json", auth=self.auth, data={"command": "FINALIZE", "media_id": media_id})
        if r.status_code >= 400:
            raise RuntimeError(f"[FINALIZE] media/upload 失敗 {r.status_code}: {r.text}")
        proc = r.json().get("processing_info", {})
        while proc.get("state") in {"pending", "in_progress"}:
            time.sleep(proc.get("check_after_secs", 3))
            q = requests.get(f"{UPLOAD_BASE}/media/upload.json", auth=self.auth, params={"command": "STATUS", "media_id": media_id})
            if q.status_code >= 400:
                raise RuntimeError(f"[STATUS] media/upload 失敗 {q.status_code}: {q.text}")
            proc = q.json().get("processing_info", {})
            if proc.get("state") == "failed":
                raise RuntimeError(f"media processing failed: {proc}")
        return media_id

    # ---- create Tweet (v2) ----
    def post_tweet_v2(self, text: str, media_ids: list[str] | None = None, reply_to_tweet_id: str | None = None) -> dict:
        payload = {"text": text}
        if media_ids:
            payload["media"] = {"media_ids": media_ids}
        # v2: possibly_sensitive はトップレベルで可
        payload["possibly_sensitive"] = self.sensitive
        if reply_to_tweet_id:
            payload["reply"] = {"in_reply_to_tweet_id": reply_to_tweet_id}

        headers = {"Content-Type": "application/json"}
        r = requests.post(f"{API_V2}/tweets", auth=self.auth, headers=headers, data=json.dumps(payload))
        if r.status_code >= 400:
            raise RuntimeError(f"[V2 POST] /2/tweets 失敗 {r.status_code}: {r.text}")
        return r.json()
