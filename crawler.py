"""
crawler.py — Fetch bài từ VNExpress RSS trong 24h qua
"""

import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
import time

RSS_FEEDS = {
    "thoi-su":      "https://vnexpress.net/rss/thoi-su.rss",
    "the-gioi":     "https://vnexpress.net/rss/the-gioi.rss",
    "khoa-hoc":     "https://vnexpress.net/rss/khoa-hoc.rss",
    "giai-tri":     "https://vnexpress.net/rss/giai-tri.rss",
    "the-thao":     "https://vnexpress.net/rss/the-thao.rss",
    "bat-dong-san": "https://vnexpress.net/rss/bat-dong-san.rss",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://vnexpress.net/",
}


def _get_og_image(url: str) -> str | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        og = soup.find("meta", property="og:image")
        if og and og.get("content"):
            return og["content"]
        img = soup.select_one("article img[src]")
        if img:
            return img["src"]
    except Exception as e:
        print(f"  [!] Không lấy được ảnh từ {url}: {e}")
    return None


def crawl(hours: int = 24, max_articles: int = 5) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    all_articles = []

    for name, url in RSS_FEEDS.items():
        print(f"[+] Fetch feed: {name}")
        feed = feedparser.parse(url)

        for entry in feed.entries:
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            if published and published < cutoff:
                continue

            image_url = None
            if hasattr(entry, "media_content") and entry.media_content:
                image_url = entry.media_content[0].get("url")
            elif hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
                image_url = entry.media_thumbnail[0].get("url")

            all_articles.append({
                "title":     entry.get("title", "").strip(),
                "url":       entry.get("link", ""),
                "summary":   BeautifulSoup(
                                 entry.get("summary", ""), "html.parser"
                             ).get_text(strip=True),
                "published": published.isoformat() if published else "",
                "category":  name,
                "image_url": image_url,
            })

        time.sleep(0.5)

    all_articles.sort(key=lambda x: x["published"], reverse=True)

    seen_urls: set[str] = set()
    unique: list[dict] = []
    for article in all_articles:
        if article["url"] in seen_urls:
            continue
        seen_urls.add(article["url"])
        unique.append(article)

    top = unique[:max_articles]

    # Enrich ảnh cho bài chưa có
    for i, article in enumerate(top):
        if not article["image_url"]:
            print(f"  [~] Scrape og:image bài {i+1}...")
            article["image_url"] = _get_og_image(article["url"])
            time.sleep(1)

    print(f"[✓] Crawl xong: {len(top)} bài\n")
    return top