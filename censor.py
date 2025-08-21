# censor.py（NudeNet 3.4.2対応・完全コピペ版）
import os
import cv2
import numpy as np
from PIL import Image

# NudeNet は初回にモデルをDLします（GitHub Actionsでも可）
try:
    from nudenet import NudeDetector  # v3系
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
LABELS = {
    s.strip().upper()
    for s in os.getenv("SENSITIVE_LABELS", ",".join(_DEFAULT_LABELS)).split(",")
    if s.strip()
}

_detector = None

def _get_detector():
    """NudeNet Detectorを遅延初期化。失敗時は None を返す。"""
    global _detector
    if _detector is not None:
        return _detector
    if not _NUDE_AVAILABLE:
        return None
    try:
        _detector = NudeDetector()  # モデルを自動DL
        return _detector
    except Exception:
        return None

def _pixelate_region(img, x1, y1, x2, y2, block=MOSAIC_BLOCK):
    h, w = img.shape[:2]
    x1 = max(0, min(w - 1, int(x1)))
    y1 = max(0, min(h - 1, int(y1)))
    x2 = max(0, min(w, int(x2)))
    y2 = max(0, min(h, int(y2)))
    if x2 <= x1 or y2 <= y1:
        return img
    roi = img[y1:y2, x1:x2]
    h2 = max(1, (y2 - y1) // block)
    w2 = max(1, (x2 - x1) // block)
    small = cv2.resize(roi, (w2, h2), interpolation=cv2.INTER_LINEAR)
    pixel = cv2.resize(small, (x2 - x1, y2 - y1), interpolation=cv2.INTER_NEAREST)
    img[y1:y2, x1:x2] = pixel
    return img

def censor_image(in_path: str, out_path: str) -> bool:
    """
    画像 in_path の“秘部のみ”モザイクして out_path に保存。
    True: モザイク適用あり / False: 検出無し or 機能無効
    """
    if not MOSAIC_ENABLED:
        return False

    det = _get_detector()
    if det is None:
        # モデルが使えない場合は素通し（投稿自体は継続）
        return False

    # PILで開いて numpy(BGR) へ
    pil = Image.open(in_path).convert("RGB")
    img = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)

    # 検出（NudeNetはファイルパスを渡すのが速い）
    try:
        results = det.detect(in_path)
    except Exception:
        return False

    hit = False
    for r in results:
        label = str(r.get("label", "")).upper()
        score = float(r.get("score", 0.0))
        box = r.get("box", [0, 0, 0, 0])
        if not (isinstance(box, (list, tuple)) and len(box) == 4):
            continue
        x1, y1, x2, y2 = box
        if label in LABELS and score >= SCORE_TH:
            img = _pixelate_region(img, x1, y1, x2, y2, MOSAIC_BLOCK)
            hit = True

    if hit:
        ok = cv2.imwrite(out_path, img, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        return bool(ok)
    return False
