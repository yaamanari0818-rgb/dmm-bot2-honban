import os, random

# 使い方：
# GitHub → Settings → Secrets and variables → Actions → Secrets に
# Name: AMAZON_R18_URLS
# Secret: アフィ付き商品URLを「カンマ区切り」で登録
# 例）https://www.amazon.co.jp/dp/AAAAAA?tag=yourtag-22,https://www.amazon.co.jp/dp/BBBBBB?tag=yourtag-22

FALLBACK = [u.strip() for u in os.getenv("AMAZON_R18_URLS", "").split(",") if u.strip()]

def pick_amazon_r18_url() -> str | None:
    return random.choice(FALLBACK) if FALLBACK else None
