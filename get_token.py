"""
get_token.py — Lấy TIKTOK_ACCESS_TOKEN & TIKTOK_OPEN_ID qua OAuth + ngrok

Cách dùng:
  1. Terminal 1: ngrok http 8080
  2. Copy URL ngrok (https://xxxx.ngrok-free.app) vào TikTok Portal → Login Kit → Redirect URI:
       https://xxxx.ngrok-free.app/callback
  3. Thêm vào .env: TIKTOK_REDIRECT_URI=https://xxxx.ngrok-free.app/callback
  4. Terminal 2: python3 get_token.py
  5. Mở link authorize, đăng nhập account TikTok (vd. techholic) → Allow
  6. Script tự ghi token vào .env
"""

import os
import secrets
import threading
import webbrowser
from pathlib import Path
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv, set_key
from flask import Flask, request

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(ENV_PATH)

CLIENT_KEY = os.getenv("CLIENT_KEY", "")
CLIENT_SECRET = os.getenv("CLIENT_SECRET", "")
REDIRECT_URI = os.getenv("TIKTOK_REDIRECT_URI", "")
PORT = int(os.getenv("OAUTH_PORT", "8080"))

SCOPES = "user.info.basic,video.publish"
AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"

app = Flask(__name__)
_state = secrets.token_urlsafe(16)
_done = threading.Event()


def _build_auth_url() -> str:
    params = {
        "client_key": CLIENT_KEY,
        "scope": SCOPES,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "state": _state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def _exchange_code(code: str) -> dict:
    resp = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": CLIENT_KEY,
            "client_secret": CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _update_env(access_token: str, open_id: str, refresh_token: str = "") -> None:
    set_key(str(ENV_PATH), "TIKTOK_ACCESS_TOKEN", access_token)
    set_key(str(ENV_PATH), "TIKTOK_OPEN_ID", open_id)
    if refresh_token:
        set_key(str(ENV_PATH), "TIKTOK_REFRESH_TOKEN", refresh_token)


@app.route("/callback")
def callback():
    err = request.args.get("error")
    if err:
        return f"<h2>OAuth lỗi: {err}</h2><p>{request.args.get('error_description', '')}</p>", 400

    if request.args.get("state") != _state:
        return "<h2>State không khớp — thử lại từ đầu.</h2>", 400

    code = request.args.get("code")
    if not code:
        return "<h2>Không có code trong callback.</h2>", 400

    try:
        data = _exchange_code(code)
    except requests.HTTPError as e:
        body = e.response.text if e.response is not None else str(e)
        return f"<h2>Đổi code thất bại</h2><pre>{body}</pre>", 500

    if "error" in data and data.get("error"):
        return f"<h2>TikTok API lỗi</h2><pre>{data}</pre>", 500

    access_token = data.get("access_token", "")
    open_id = data.get("open_id", "")
    refresh_token = data.get("refresh_token", "")

    if not access_token or not open_id:
        return f"<h2>Thiếu token trong response</h2><pre>{data}</pre>", 500

    _update_env(access_token, open_id, refresh_token)
    _done.set()

    return f"""
    <h2>Thành công</h2>
    <p>Đã lưu vào <code>.env</code></p>
    <ul>
      <li><b>open_id:</b> {open_id}</li>
      <li><b>access_token:</b> {access_token[:20]}…</li>
    </ul>
    <p>Chạy <code>python3 main.py</code> để đăng bài. Có thể đóng tab này.</p>
    """


@app.route("/")
def index():
    return f'<p>Chờ OAuth… <a href="{_build_auth_url()}">Mở authorize</a></p>'


def _verify_creator(access_token: str) -> str | None:
    resp = requests.post(
        "https://open.tiktokapis.com/v2/post/publish/creator_info/query/",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        timeout=15,
    )
    data = resp.json()
    if data.get("error", {}).get("code") == "ok":
        return data.get("data", {}).get("creator_username")
    return None


def main():
    if not CLIENT_KEY or not CLIENT_SECRET:
        print("[!] Thiếu CLIENT_KEY / CLIENT_SECRET trong .env")
        return

    if not REDIRECT_URI:
        print("[!] Thiếu TIKTOK_REDIRECT_URI trong .env")
        print("    Ví dụ: TIKTOK_REDIRECT_URI=https://abcd1234.ngrok-free.app/callback")
        print("    (phải khớp Redirect URI trên TikTok Developer Portal)")
        return

    auth_url = _build_auth_url()
    print("=" * 55)
    print("  TIKTOK OAUTH — ngrok")
    print("=" * 55)
    print(f"\n[1] Đảm bảo ngrok đang chạy: ngrok http {PORT}")
    print(f"[2] Redirect URI (.env): {REDIRECT_URI}")
    print(f"\n[3] Mở link sau (đăng nhập account muốn đăng bài):\n")
    print(auth_url)
    print(f"\n[4] Server local: http://127.0.0.1:{PORT}/callback\n")

    threading.Timer(1.5, lambda: webbrowser.open(auth_url)).start()

    app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False)

    if _done.is_set():
        load_dotenv(ENV_PATH, override=True)
        token = os.getenv("TIKTOK_ACCESS_TOKEN", "")
        username = _verify_creator(token) if token else None
        print("\n[✓] Đã cập nhật .env")
        if username:
            print(f"[✓] Creator: @{username}")


if __name__ == "__main__":
    main()
