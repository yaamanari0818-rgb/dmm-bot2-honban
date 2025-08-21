# censor.py
import os
import cv2
from PIL import Image

# NudeNet は初回にモデルをDLします
try:
    from nudenet import NudeDetector  # type: ignore
    _NUDE_AVAILABLE = True
except Exception:
    _NUDE_AVAILABLE = False

# ===== 環境変数で調整可能 =====
MOSAIC_ENABLED = os.getenv("MOSAIC_ENABLED", "true").lower() == "true"
MOSAIC_BLOCK = max(8, int(os.getenv("MOSAIC_BLOCK", "24")))  # 粗さ（大きいほど荒い）
SCORE_TH = float(os.getenv("MOSAIC_SCORE_TH", "0.45"))       # 検出しきい値

_DEFAULT_LABELS = [
    "EXPOSED_ANUS",
    "EXPOSED_BREAST_F",
    "EXPOSED_BREAST_M",
    "EXPOSED_GENITALIA_F",
    "EXPOSED_GENITALIA_M",
    "EXPOSED_BUTTOCKS",
]
LABELS = {s.strip().upper() for s in os.getenv(
    "SENSITIVE_LABELS",
    ",".join(_DEFAULT_LABELS)
).split(",") if s.strip()}

_detector = None

def _get_detector():
    global _detector
    if _detector is None:
        _detector = NudeDetector()
    return _detector

def _pixelate_region(img, x1, y1, x2, y2, block=MOSAIC_BLOCK):
    h, w = img.shape[:2]
    x1 = max(0, min(w-1, int(x1)))
    y1 = max(0, min(h-1, int(y1)))
    x2 = max(0, min(w,   int(x2)))
    y2 = max(0, min(h,   int(y2)))
    if x2 <= x1 or y2 <= y1:
        return img
    roi = img[y1:y2, x1:x2]
    h2 = max(1, (y2-y1)//block)
    w2 = max(1, (x2-x1)//block)
    small = cv2.resize(roi, (w2, h2), interpolation=cv2.INTER_LINEAR)
    pixel = cv2.resize(small, (x2-x1, y2-y1), interpolation=cv2.INTER_NEAREST)
    img[y1:y2, x1:x2] = pixel
    return img

def censor_image(in_path: str, out_path: str) -> bool:
    """
    画像 in_path の“秘部のみ”モザイクして out_path に保存。
    True: モザイク適用あり / False: 検出無しで未変更
    """
    if not MOSAIC_ENABLED or not _NUDE_AVAILABLE:
        return False

    det = _get_detector()
    pil = Image.open(in_path).convert("RGB")
    img = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)

    results = det.detect(in_path)  # [{'label': 'EXPOSED_GENITALIA_F', 'score': 0.9, 'box': [x1,y1,x2,y2]}, ...]
    hit = False
    for r in results:
        label = str(r.get("label", "")).upper()
        score = float(r.get("score", 0.0))
        x1, y1, x2, y2 = r.get("box", [0,0,0,0])
        if label in LABELS and score >= SCORE_TH:
            img = _pixelate_region(img, x1, y1, x2, y2, MOSAIC_BLOCK)
            hit = True

    if hit:
        ok = cv2.imwrite(out_path, img, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        return bool(ok)
    return False

# numpy は最後に読み込み（ログ短縮のため）
import numpy as np  # noqa: E402
