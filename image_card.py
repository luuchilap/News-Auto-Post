"""
image_card.py — Ghép ảnh tin: phần trên = ảnh nguồn, phần dưới = tóm tắt nền cam vàng
"""

import os
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

CANVAS_W = 1080
CANVAS_H = 1920
TOP_RATIO = 0.45
# Cam đậm
ORANGE_YELLOW_TOP = "#F08C10"
ORANGE_YELLOW_BOTTOM = "#FFAB2E"
TEXT_BLACK = "#1A1A1A"
TEXT_MUTED = "#3D2808"
PADDING = 52

CATEGORY_LABELS = {
    "tin-moi-nhat": "Tin mới",
    "the-thao": "Thể thao",
    "kinh-doanh": "Kinh doanh",
    "giai-tri": "Giải trí",
}

_FONT_CANDIDATES = {
    "title": [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
    "body": [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ],
}


def _load_font(role: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_CANDIDATES.get(role, _FONT_CANDIDATES["body"]):
        if os.path.isfile(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _fit_cover(img: Image.Image, w: int, h: int) -> Image.Image:
    """Crop + resize để lấp đầy khung, giữ tâm ảnh."""
    src = img.convert("RGB")
    scale = max(w / src.width, h / src.height)
    nw, nh = int(src.width * scale), int(src.height * scale)
    resized = src.resize((nw, nh), Image.Resampling.LANCZOS)
    left = (nw - w) // 2
    top = (nh - h) // 2
    return resized.crop((left, top, left + w, top + h))


def _wrap_lines(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return []

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _make_orange_panel(width: int, height: int) -> Image.Image:
    """Nền cam vàng gradient nhẹ cho phần chữ."""
    panel = Image.new("RGB", (width, height), ORANGE_YELLOW_TOP)
    draw = ImageDraw.Draw(panel)
    r1, g1, b1 = (240, 140, 16)
    r2, g2, b2 = (255, 171, 46)
    for y in range(height):
        t = y / max(height - 1, 1)
        color = (
            int(r1 + (r2 - r1) * t),
            int(g1 + (g2 - g1) * t),
            int(b1 + (b2 - b1) * t),
        )
        draw.line([(0, y), (width, y)], fill=color)
    return panel


def _draw_brand_bar(draw: ImageDraw.ImageDraw, brand: str, w: int) -> None:
    """Thanh mờ góc trên phải."""
    if not brand:
        return
    font = _load_font("title", 38)
    pad_x, pad_y = 20, 12
    tw = draw.textlength(brand, font=font)
    th = 44
    x1 = w - PADDING - tw - pad_x * 2
    y1 = PADDING
    x2 = w - PADDING
    y2 = y1 + th
    draw.rounded_rectangle((x1, y1, x2, y2), radius=8, fill=(0, 0, 0, 160))
    draw.text((x1 + pad_x, y1 + pad_y - 4), brand, font=font, fill="white")


def build_card(
    image_bytes: bytes,
    title: str,
    summary: str,
    category: str = "",
) -> bytes:
    """
    Tạo JPEG 1080x1920 từ ảnh nguồn + title/summary.
    Trả về bytes JPEG (TikTok hỗ trợ JPEG).
    """
    top_h = int(CANVAS_H * TOP_RATIO)
    bottom_h = CANVAS_H - top_h

    source = Image.open(BytesIO(image_bytes))
    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H))
    top = _fit_cover(source, CANVAS_W, top_h)
    canvas.paste(top, (0, 0))
    bottom_panel = _make_orange_panel(CANVAS_W, bottom_h)
    canvas.paste(bottom_panel, (0, top_h))

    draw = ImageDraw.Draw(canvas, "RGBA")
    brand = os.getenv("NEWS_BRAND", "Tin nhanh")
    _draw_brand_bar(draw, brand, CANVAS_W)

    title_font = _load_font("title", 62)
    body_font = _load_font("body", 44)
    footer_font = _load_font("body", 30)

    max_text_w = CANVAS_W - PADDING * 2
    y = top_h + PADDING

    title_lines = _wrap_lines(draw, title.strip(), title_font, max_text_w)
    for line in title_lines[:4]:
        draw.text((PADDING, y), line, font=title_font, fill=TEXT_BLACK)
        y += 72

    y += 20
    summary = summary.strip()
    if len(summary) > 420:
        summary = summary[:417].rstrip() + "…"

    body_lines = _wrap_lines(draw, summary, body_font, max_text_w)
    line_h = 54
    max_body_lines = max(1, (top_h + bottom_h - (y - top_h) - 80) // line_h)
    for line in body_lines[:max_body_lines]:
        draw.text((PADDING, y), line, font=body_font, fill=TEXT_BLACK)
        y += line_h

    cat_label = CATEGORY_LABELS.get(category, category.replace("-", " ").title())
    footer = f"vnexpress.net — {cat_label}" if cat_label else "vnexpress.net"
    fw = draw.textlength(footer, font=footer_font)
    draw.text(
        (CANVAS_W - PADDING - fw, CANVAS_H - PADDING - 30),
        footer,
        font=footer_font,
        fill=TEXT_MUTED,
    )

    out = BytesIO()
    canvas.save(out, format="JPEG", quality=92, optimize=True)
    return out.getvalue()


def preview_card(article: dict, output_path: str = "preview_card.jpg") -> str:
    """Tiện test: tải ảnh từ article['image_url'] và lưu file."""
    import requests

    from s3_uploader import HEADERS, _download_image

    data, _ = _download_image(article["image_url"])
    if not data:
        raise RuntimeError("Không tải được ảnh")

    jpeg = build_card(
        data,
        article.get("title", ""),
        article.get("summary", ""),
        article.get("category", ""),
    )
    with open(output_path, "wb") as f:
        f.write(jpeg)
    return output_path
