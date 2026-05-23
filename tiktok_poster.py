"""
tiktok_poster.py — Đăng ảnh lên TikTok qua Content Posting API
"""

import requests
import os
import time

TIKTOK_API_BASE = "https://open.tiktokapis.com/v2"


def _get_headers() -> dict:
    token = os.getenv("TIKTOK_ACCESS_TOKEN")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=UTF-8",
    }


def _query_creator_info() -> dict | None:
    """Lấy thông tin creator — bắt buộc trước khi đăng bài."""
    resp = requests.post(
        f"{TIKTOK_API_BASE}/post/publish/creator_info/query/",
        headers=_get_headers(),
        timeout=10,
    )
    data = resp.json()
    if data.get("error", {}).get("code") != "ok":
        print(f"[!] Query creator info thất bại: {data}")
        return None
    return data["data"]


def _utf16_len(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def _truncate_utf16(text: str, max_runes: int) -> str:
    while text and _utf16_len(text) > max_runes:
        text = text[:-1]
    return text


def _build_caption(articles: list[dict]) -> tuple[str, str]:
    """
    TikTok photo: title tối đa 90 UTF-16 runes, description tối đa 4000.
  """
    from datetime import datetime

    date_str = datetime.now().strftime("%d/%m")
    title = _truncate_utf16(f"Điểm tin ngày {date_str}", 90)

    lines = [f"{i}. {a['title']}" for i, a in enumerate(articles, 1)]
    hashtags = "#TinTuc #VNExpress #DiemTinSang #ThoiSu"
    line_sep = "\u2028"  # Use Unicode line separator to force line breaks in TikTok caption.
    description = _truncate_utf16(line_sep.join(lines) + f"{line_sep}{line_sep}{hashtags}", 4000)
    return title, description


def _pick_privacy(privacy_options: list[str]) -> str:
    """
    App chưa audit chỉ chấp nhận SELF_ONLY dù API trả thêm PUBLIC.
    Sau audit, đặt TIKTOK_PRIVACY_LEVEL=PUBLIC_TO_EVERYONE trong .env.
    """
    forced = os.getenv("TIKTOK_PRIVACY_LEVEL", "").strip()
    if forced and forced in privacy_options:
        return forced

    # Sandbox / chưa audit: ưu tiên private để đăng được
    if "SELF_ONLY" in privacy_options:
        return "SELF_ONLY"
    if "PUBLIC_TO_EVERYONE" in privacy_options:
        return "PUBLIC_TO_EVERYONE"
    return privacy_options[0]


def post_to_tiktok(articles: list[dict]) -> bool:
    """
    Đăng carousel ảnh lên TikTok.
    Chỉ đăng những bài có s3_url hợp lệ.
    """
    # Lọc bài có ảnh trên S3
    valid = [a for a in articles if a.get("s3_url")]
    if not valid:
        print("[!] Không có ảnh nào để đăng lên TikTok")
        return False

    # Giới hạn tối đa 20 ảnh theo TikTok API
    valid = valid[:20]

    print(f"[+] Chuẩn bị đăng {len(valid)} ảnh lên TikTok...")

    # Bắt buộc query creator info trước
    creator = _query_creator_info()
    if not creator:
        return False
    print(f"  [✓] Creator: @{creator.get('creator_username')}")

    privacy_options = creator.get("privacy_level_options", [])
    privacy = _pick_privacy(privacy_options)
    print(f"  [~] privacy_level: {privacy}")
    if privacy == "SELF_ONLY":
        print("  [~] Chế độ riêng tư (chỉ bạn thấy) — hợp lệ khi app chưa audit")

    title, description = _build_caption(valid)
    payload = {
        "post_info": {
            "title":                title,
            "description":          description,
            "privacy_level":        privacy,
            "disable_comment":      False,
            "auto_add_music":       True,
            "brand_content_toggle": False,
            "brand_organic_toggle": False,
        },
        "source_info": {
            "source":            "PULL_FROM_URL",
            "photo_cover_index": 0,
            "photo_images":      [a["s3_url"] for a in valid],
        },
        "post_mode":  "DIRECT_POST",
        "media_type": "PHOTO",
    }

    print(f"  [+] Gọi TikTok API...")
    resp = requests.post(
        f"{TIKTOK_API_BASE}/post/publish/content/init/",
        headers=_get_headers(),
        json=payload,
        timeout=30,
    )
    data = resp.json()

    if data.get("error", {}).get("code") != "ok":
        err = data.get("error", {})
        print(f"  [!] Đăng thất bại: {data}")
        code = err.get("code", "")
        if code == "url_ownership_unverified":
            cf = os.getenv("CLOUDFRONT_BASE_URL", "https://your-cloudfront.net")
            print(
                "  [i] Xác minh domain CloudFront trên TikTok Developer Portal:\n"
                f"      URL Properties → thêm prefix: {cf.rstrip('/')}/"
            )
        elif code == "unaudited_client_can_only_post_to_private_accounts":
            print("  [i] App chưa audit — chỉ đăng được với privacy_level=SELF_ONLY")
        return False

    publish_id = data["data"]["publish_id"]
    print(f"  [✓] Đã gửi bài, publish_id: {publish_id}")

    # Poll trạng thái bài đăng
    _poll_status(publish_id)
    return True


def _poll_status(publish_id: str, max_tries: int = 10, interval: int = 5):
    """Kiểm tra trạng thái xử lý bài đăng."""
    print(f"  [+] Đang chờ TikTok xử lý...")
    for attempt in range(max_tries):
        time.sleep(interval)
        resp = requests.post(
            f"{TIKTOK_API_BASE}/post/publish/status/fetch/",
            headers=_get_headers(),
            json={"publish_id": publish_id},
            timeout=10,
        )
        data = resp.json()
        status = data.get("data", {}).get("status", "UNKNOWN")
        print(f"    [{attempt+1}/{max_tries}] Status: {status}")

        if status in ("PUBLISH_COMPLETE", "PUBLISH_FAILED"):
            if status == "PUBLISH_COMPLETE":
                print("  [✓] Đăng bài thành công!")
            else:
                print(f"  [!] Đăng bài thất bại: {data}")
            return

    print("  [~] Hết thời gian poll — kiểm tra TikTok thủ công")