"""
s3_uploader.py — Download ảnh từ VNExpress, ghép card, upload lên S3
"""

import boto3
import requests
import os
from datetime import datetime
from urllib.parse import urlparse

from image_card import build_card

# Đổi version khi đổi style card → URL S3 mới, tránh CloudFront/TikTok cache ảnh cũ
CARD_S3_VERSION = os.getenv("CARD_S3_VERSION", "v2-orange")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://vnexpress.net/",
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}

# TikTok photo API chỉ chấp nhận JPEG / WebP
SUPPORTED_FORMATS = {
    "image/jpeg": ".jpg",
    "image/jpg":  ".jpg",
    "image/webp": ".webp",
}


def _download_image(url: str) -> tuple[bytes, str] | tuple[None, None]:
    """Trả về (binary_data, content_type) hoặc (None, None) nếu lỗi."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "").split(";")[0].strip()
        if content_type not in SUPPORTED_FORMATS:
            ext = urlparse(url).path.split(".")[-1].lower()
            if ext in ("jpg", "jpeg"):
                content_type = "image/jpeg"
            elif ext == "webp":
                content_type = "image/webp"
            else:
                print(f"  [!] Định dạng không hỗ trợ ({content_type}), bỏ qua")
                return None, None
        return resp.content, content_type
    except Exception as e:
        print(f"  [!] Download ảnh thất bại ({url}): {e}")
        return None, None


def upload_images(articles: list[dict]) -> list[dict]:
    """
    Download ảnh từ mỗi bài và upload lên S3.
    Gán thêm 's3_url' (CloudFront URL) vào mỗi article.
    """
    s3 = boto3.client(
        "s3",
        region_name=os.getenv("AWS_REGION", "ap-southeast-1"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )

    bucket      = os.getenv("S3_BUCKET_NAME")
    cf_base_url = os.getenv("CLOUDFRONT_BASE_URL", "").rstrip("/")
    if cf_base_url and not cf_base_url.startswith("https://"):
        cf_base_url = "https://" + cf_base_url
    date_prefix = datetime.now().strftime("%Y/%m/%d")
    use_card = os.getenv("USE_IMAGE_CARD", "true").lower() in ("1", "true", "yes")

    for i, article in enumerate(articles):
        article["s3_url"] = None

        if not article.get("image_url"):
            print(f"  [~] Bài {i+1}: không có ảnh, bỏ qua upload")
            continue

        print(f"  [+] Bài {i+1}: download ảnh...")
        data, content_type = _download_image(article["image_url"])
        if not data:
            continue

        if use_card:
            print(f"  [+] Bài {i+1}: ghép card (ảnh + nền cam vàng)...")
            try:
                data = build_card(
                    data,
                    article.get("title", ""),
                    article.get("summary", ""),
                    article.get("category", ""),
                )
                content_type = "image/jpeg"
            except Exception as e:
                print(f"  [!] Ghép card thất bại: {e}")
                continue

        if use_card:
            # Luôn JPEG card; path riêng + version để không dính cache .webp cũ
            ext = ".jpg"
            filename = f"news-{i+1}.jpg"
            s3_key = f"vnexpress/{date_prefix}/cards/{CARD_S3_VERSION}/{filename}"
        else:
            ext = SUPPORTED_FORMATS.get(content_type, ".jpg")
            filename = f"news-{i+1}{ext}"
            s3_key = f"vnexpress/{date_prefix}/{filename}"

        try:
            s3.put_object(
                Bucket=bucket,
                Key=s3_key,
                Body=data,
                ContentType=content_type,
                CacheControl="max-age=0, no-cache, no-store, must-revalidate",
            )
            article["s3_url"] = f"{cf_base_url}/{s3_key}"
            print(f"  [✓] Upload xong: {article['s3_url']}")
        except Exception as e:
            print(f"  [!] Upload S3 thất bại: {e}")

    return articles