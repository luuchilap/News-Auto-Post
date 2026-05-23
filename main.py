"""
main.py — Entry point: crawl → upload S3 → đăng TikTok
Chạy: python3 main.py
"""

import json
import os
from dotenv import load_dotenv
from crawler import crawl
from s3_uploader import upload_images
from tiktok_poster import post_to_tiktok

load_dotenv()


def main():
    print("=" * 55)
    print("  TIKTOK AUTO POST — VNExpress Daily News")
    print("=" * 55)

    # Bước 1: Crawl bài từ VNExpress
    print("\n[BƯỚC 1] Crawl bài từ VNExpress...")
    articles = crawl(hours=24, max_articles=5)

    if not articles:
        print("[!] Không có bài nào, dừng lại.")
        return

    # Bước 2: Ghép card + upload S3 (USE_IMAGE_CARD=false để tắt)
    print("[BƯỚC 2] Ghép card & upload ảnh lên S3...")
    articles = upload_images(articles)

    # Lưu log để debug
    with open("articles_log.json", "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    print("  [✓] Đã lưu log vào articles_log.json")

    # Bước 3: Đăng lên TikTok
    print("\n[BƯỚC 3] Đăng lên TikTok...")
    success = post_to_tiktok(articles)

    print("\n" + "=" * 55)
    print(f"  KẾT QUẢ: {'✓ Thành công' if success else '✗ Thất bại'}")
    print("=" * 55)


if __name__ == "__main__":
    main()