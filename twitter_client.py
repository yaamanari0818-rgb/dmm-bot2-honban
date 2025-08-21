import os, time, mimetypes
import requests
from requests_oauthlib import OAuth1

BASE = "https://api.twitter.com/1.1"

class TwitterClient:
    def __init__(self):
        self.auth = OAuth1(
            os.environ["X_API_KEY"],
            os.environ["X_API_SECRET"],
            os.environ["X_ACCESS_TOKEN"],
            os.environ["X_ACCESS_SECRET"],
        )
        self.sensitive = os.getenv("SENSITIVE_MEDIA", "true").lower() == "true"

    # ---- media/upload (chunked) ----
    def upload_media_chunked(self, filepath: str, media_type: str | None = None) -> str:
        size = os.path.getsize(filepath)
        media_type = media_type or (mimetypes.guess_type(filepath)[0] or "video/mp4")
        # INIT
        r = requests.post(
            f"{BASE}/media/upload.json",
            auth=self.auth,
            data={
                "command": "INIT",
                "media_type": media_type,
                "total_bytes": size,
            },
        )
        r.raise_for_status()
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
                    f"{BASE}/media/upload.json",
                    auth=self.auth,
                    data={"command": "APPEND", "media_id": media_id, "segment_index": seg},
                    files=files,
                )
                r.raise_for_status()
                seg += 1

        # FINALIZE
        r = requests.post(
            f"{BASE}/media/upload.json",
            auth=self.auth,
            data={"command": "FINALIZE", "media_id": media_id},
        )
        r.raise_for_status()
        info = r.json()
        proc = info.get("processing_info", {})
        while proc.get("state") in {"pending", "in_progress"}:
            time.sleep(proc.get("check_after_secs", 3))
            q = requests.get(f"{BASE}/media/upload.json", auth=self.auth, params={"command":"STATUS","media_id": media_id})
            q.raise_for_status()
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
        r = requests.post(f"{BASE}/statuses/update.json", auth=self.auth, data=payload)
        r.raise_for_status()
        return r.json()
