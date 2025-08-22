# censor.py（露出部のみ■で塗りつぶし）
import os
import cv2
import numpy as np
from PIL import Image

# NudeNet（v3系）で露出部を検出
try:
    from nudenet import NudeDetector
    _NUDE_AVAILABLE = True
except Exception:
    _NUDE_AVAILABLE = False

# ===== 調整用パラメータ（Actions > Variables で上書き可） =====
ENABLED = os.getenv("MOSAIC_ENABLED", "true").lower() == "true"   # trueで有効
SCORE_TH = float(os.getenv("MOSAIC_SCORE_TH", "0.55"))             # 検出スコアしきい値（↑＝厳しめ）
MIN_BOX_AREA_RATIO = float(os.getenv("MOSAIC_MIN_BOX_AREA", "0.012"))  # 最小面積比（画像に対して1.2%など）
PAD_RATIO = float(os.getenv("MOSAIC_PAD_RATIO", "0.06"))           # ボックスを上下左右に拡張（6%）
# 塗りつぶし色（BGRで指定 or HEX）
SOLID_COLOR_ENV = os.getenv("SOLID_COLOR", "#000000")              # 既定：黒（■）
# 対象ラベル（カンマ区切りで上書き可）
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
    global _detector
    if _detector is not None:
        return _detector
    if not _NUDE_AVAILABLE:
        return None
    try:
        _detector = NudeDetector()  # 初回はモデルDL
        return _detector
    except Exception:
        return None

def _parse_color(v: str):
    """
    '#RRGGBB' or 'B,G,R' or 'R,G,B' っぽい文字列をBGRタプルに変換。
    不正なら黒。
    """
    v = (v or "").strip()
    # HEX
    if v.startswith("#") and len(v) == 7:
        try:
            r = int(v[1:3], 16)
            g = int(v[3:5], 16)
            b = int(v[5:7], 16)
            return (b, g, r)  # OpenCVはBGR
        except Exception:
            pass
    # CSV
    if "," in v:
        try:
            parts = [int(x.strip()) for x in v.split(",")]
            if len(parts) == 3:
                # 0-255 範囲をクリップ
                parts = [max(0, min(255, p)) for p in parts]
                # R,G,B か B,G,R か曖昧だが、R,G,B と見なす → BGRに並べ替え
                r, g, b = parts
                return (b, g, r)
        except Exception:
            pass
    return (0, 0, 0)  # fallback: 黒

SOLID_COLOR = _parse_color(SOLID_COLOR_ENV)

def _clip(v, lo, hi):  # クリップ
    return max(lo, min(hi, v))

def _expand_box(x1, y1, x2, y2, W, H, pad_ratio=PAD_RATIO):
    w = x2 - x1
    h = y2 - y1
    px = int(round(w * pad_ratio))
    py = int(round(h * pad_ratio))
    nx1 = _clip(x1 - px, 0, W - 1)
    ny1 = _clip(y1 - py, 0, H - 1)
    nx2 = _clip(x2 + px, 1, W)
    ny2 = _clip(y2 + py, 1, H)
    # 最低1px以上
    if nx2 <= nx1: nx2 = min(W, nx1 + 1)
    if ny2 <= ny1: ny2 = min(H, ny1 + 1)
    return nx1, ny1, nx2, ny2

def _solid_fill(img, x1, y1, x2, y2, color=SOLID_COLOR):
    # 完全塗りつぶし（■）
    cv2.rectangle(img, (x1, y1), (x2, y2), color, thickness=-1)
    return img

def censor_image(in_path: str, out_path: str) -> bool:
    """
    画像 in_path を解析し、「十分に強い＆大きい露出」だけを■で塗りつぶし。
    1つも当てなければ False → 呼び出し側は元画像のまま使う。
    """
    if not ENABLED:
        return False

    det = _get_detector()
    if det is None:
        return False

    # 画像読み込み
    pil = Image.open(in_path).convert("RGB")
    rgb = np.array(pil)
    img = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    H, W = img.shape[:2]
    img_area = float(H * W) if H and W else 0.0

    # 検出（ファイルパス指定が高速）
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
        x1, y1, x2, y2 = [int(max(0, v)) for v in box]
        x1 = _clip(x1, 0, W - 1); x2 = _clip(max(x2, x1 + 1), 1, W)
        y1 = _clip(y1, 0, H - 1); y2 = _clip(max(y2, y1 + 1), 1, H)

        # 対象ラベル & スコア閾値
        if label not in LABELS or score < SCORE_TH:
            continue

        # 面積が小さすぎる検出は無視
        if img_area <= 0:
            continue
        box_area = float((x2 - x1) * (y2 - y1))
        if (box_area / img_area) < MIN_BOX_AREA_RATIO:
            continue

        # パディングして確実に覆う
        ex1, ey1, ex2, ey2 = _expand_box(x1, y1, x2, y2, W, H, PAD_RATIO)

        # ■で塗りつぶし
        img = _solid_fill(img, ex1, ey1, ex2, ey2, SOLID_COLOR)
        hit = True

    if hit:
        cv2.imwrite(out_path, img, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        return True
    return False
