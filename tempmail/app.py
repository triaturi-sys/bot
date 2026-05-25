"""
Temporary Email Web Application - IMAP Mode
Domain: bookinglapanganfutsal.my.id

Cara kerja:
1. User generate email custom (misal: otp@bookinglapanganfutsal.my.id)
2. Cloudflare Email Routing forward email ke Gmail kamu
3. Aplikasi ini baca Gmail via IMAP setiap 15 detik
4. Email yang tujuannya ke domain kita ditampilkan di web

Environment Variables (.env):
- GMAIL_EMAIL=your@gmail.com
- GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
- DOMAIN=bookinglapanganfutsal.my.id (default)
- POLL_INTERVAL=15 (detik, default)
"""

from __future__ import annotations

import email
import imaplib
import os
import random
import re
import string
import threading
import time
import uuid
from datetime import datetime
from email.policy import default as default_policy
from typing import Any

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, session
from flask_cors import CORS

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GMAIL_EMAIL = os.environ.get("GMAIL_EMAIL", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "")
DOMAIN = os.environ.get("DOMAIN", "bookinglapanganfutsal.my.id")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "15"))
SECRET_KEY = os.environ.get("SECRET_KEY", "tempmail-change-this-in-production")

app = Flask(__name__)
app.secret_key = SECRET_KEY
CORS(app)

# Penyimpanan email di memory (per session restart akan refresh dari Gmail)
# Format: {email_address: [{"id": ..., "from": ..., "subject": ...}]}
mailbox: dict[str, list[dict[str, Any]]] = {}

# Track Gmail message IDs yang sudah di-fetch (biar tidak duplicate)
fetched_uids: set[str] = set()

# Lock untuk thread safety
mail_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

def generate_username(length: int = 10) -> str:
    """Generate random username untuk email."""
    chars = string.ascii_lowercase + string.digits
    return "".join(random.choice(chars) for _ in range(length))


def generate_email() -> str:
    """Generate alamat email temporary."""
    return f"{generate_username()}@{DOMAIN}"


def extract_recipient(msg) -> str | None:
    """Cari alamat tujuan original yang berakhiran @DOMAIN dari header email."""
    headers_to_check = [
        msg.get("To", ""),
        msg.get("Delivered-To", ""),
        msg.get("X-Forwarded-To", ""),
        msg.get("X-Original-To", ""),
        msg.get("Cc", ""),
    ]

    pattern = re.compile(r"[\w\.\-+]+@[\w\.\-]+", re.IGNORECASE)
    for header in headers_to_check:
        if not header:
            continue
        for match in pattern.findall(header):
            addr = match.lower()
            if addr.endswith(f"@{DOMAIN.lower()}"):
                return addr
    return None


def parse_email_body(msg) -> tuple[str, str]:
    """Extract plain text dan HTML body dari email."""
    body = ""
    html_body = ""

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", ""))
            if "attachment" in disposition:
                continue
            try:
                if content_type == "text/plain" and not body:
                    body = part.get_content()
                elif content_type == "text/html" and not html_body:
                    html_body = part.get_content()
            except Exception:
                payload = part.get_payload(decode=True)
                if payload:
                    try:
                        decoded = payload.decode("utf-8", errors="replace")
                        if content_type == "text/plain" and not body:
                            body = decoded
                        elif content_type == "text/html" and not html_body:
                            html_body = decoded
                    except Exception:
                        pass
    else:
        try:
            content = msg.get_content()
            if msg.get_content_type() == "text/html":
                html_body = content
            else:
                body = content
        except Exception:
            pass

    return body, html_body


# ---------------------------------------------------------------------------
# IMAP Poller - Baca Gmail dan filter untuk domain kita
# ---------------------------------------------------------------------------

def fetch_emails_from_gmail() -> int:
    """Connect ke Gmail IMAP dan ambil email baru untuk domain kita.

    Returns:
        Jumlah email baru yang di-fetch.
    """
    if not GMAIL_EMAIL or not GMAIL_APP_PASSWORD:
        return 0

    new_count = 0
    imap = None
    try:
        imap = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        imap.login(GMAIL_EMAIL, GMAIL_APP_PASSWORD)
        imap.select("INBOX")

        # Cari email yang TO/CC mengandung domain kita
        # ALL = ambil semua, lalu filter manual via header
        status, data = imap.uid("search", None, "ALL")
        if status != "OK":
            return 0

        uids = data[0].split()
        # Ambil 50 terbaru aja biar cepat
        uids = uids[-50:] if len(uids) > 50 else uids

        for uid in uids:
            uid_str = uid.decode() if isinstance(uid, bytes) else str(uid)

            # Skip kalau sudah pernah di-fetch
            if uid_str in fetched_uids:
                continue

            status, msg_data = imap.uid("fetch", uid, "(RFC822)")
            if status != "OK" or not msg_data or not msg_data[0]:
                continue

            raw_email = msg_data[0][1]
            if not isinstance(raw_email, (bytes, bytearray)):
                continue

            msg = email.message_from_bytes(raw_email, policy=default_policy)

            recipient = extract_recipient(msg)
            if not recipient:
                fetched_uids.add(uid_str)
                continue

            subject = str(msg.get("subject", "(No Subject)"))
            from_addr = str(msg.get("from", "Unknown"))
            date_str = str(msg.get("date", ""))

            body, html_body = parse_email_body(msg)

            mail_data = {
                "id": str(uuid.uuid4()),
                "uid": uid_str,
                "from": from_addr,
                "to": recipient,
                "subject": subject,
                "body": body,
                "html_body": html_body,
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "raw_date": date_str,
                "read": False,
            }

            with mail_lock:
                if recipient not in mailbox:
                    mailbox[recipient] = []
                mailbox[recipient].append(mail_data)
                fetched_uids.add(uid_str)
                new_count += 1

        imap.close()

    except imaplib.IMAP4.error as e:
        print(f"[IMAP] Login/Auth error: {e}")
    except Exception as e:
        print(f"[IMAP] Error: {e}")
    finally:
        if imap is not None:
            try:
                imap.logout()
            except Exception:
                pass

    if new_count > 0:
        print(f"[IMAP] Fetched {new_count} new email(s)")

    return new_count


def imap_poll_loop():
    """Background thread - polling Gmail terus menerus."""
    print(f"[IMAP] Poller started (interval: {POLL_INTERVAL}s)")
    while True:
        try:
            fetch_emails_from_gmail()
        except Exception as e:
            print(f"[IMAP] Poll error: {e}")
        time.sleep(POLL_INTERVAL)


# ---------------------------------------------------------------------------
# Flask Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Halaman utama."""
    return render_template("index.html", domain=DOMAIN)


@app.route("/api/generate", methods=["POST"])
def api_generate():
    """Generate email address baru."""
    data = request.get_json() or {}
    custom_name = data.get("username", "").strip().lower()

    if custom_name:
        if not all(c in string.ascii_lowercase + string.digits + "._-" for c in custom_name):
            return jsonify({"error": "Username hanya boleh huruf kecil, angka, titik, underscore, dan dash"}), 400
        if len(custom_name) < 3 or len(custom_name) > 30:
            return jsonify({"error": "Username harus 3-30 karakter"}), 400
        email_addr = f"{custom_name}@{DOMAIN}"
    else:
        email_addr = generate_email()

    with mail_lock:
        if email_addr not in mailbox:
            mailbox[email_addr] = []

    session["email"] = email_addr

    return jsonify({
        "email": email_addr,
        "expires_at": "never",
        "expires_in_minutes": 0,
        "permanent": True,
    })


@app.route("/api/inbox")
def api_inbox():
    """Ambil daftar email di inbox + trigger fetch on-demand."""
    email_addr = request.args.get("email", "").lower()
    if not email_addr:
        email_addr = session.get("email", "")

    if not email_addr or not email_addr.endswith(f"@{DOMAIN.lower()}"):
        return jsonify({"error": "Email address tidak valid"}), 400

    # On-demand fetch (best effort, jangan blocking lama)
    threading.Thread(target=fetch_emails_from_gmail, daemon=True).start()

    with mail_lock:
        emails = mailbox.get(email_addr, [])
        emails_sorted = sorted(emails, key=lambda x: x["date"], reverse=True)

    return jsonify({
        "email": email_addr,
        "count": len(emails_sorted),
        "messages": emails_sorted,
    })


@app.route("/api/email/<email_id>")
def api_read_email(email_id: str):
    """Baca satu email."""
    email_addr = request.args.get("email", "").lower()
    if not email_addr:
        email_addr = session.get("email", "")
    if not email_addr:
        return jsonify({"error": "Email address tidak ditemukan"}), 400

    with mail_lock:
        emails = mailbox.get(email_addr, [])
        for mail in emails:
            if mail["id"] == email_id:
                mail["read"] = True
                return jsonify(mail)

    return jsonify({"error": "Email tidak ditemukan"}), 404


@app.route("/api/delete/<email_id>", methods=["DELETE"])
def api_delete_email(email_id: str):
    """Hapus satu email dari tampilan."""
    email_addr = request.args.get("email", "").lower()
    if not email_addr:
        email_addr = session.get("email", "")
    if not email_addr:
        return jsonify({"error": "Email address tidak ditemukan"}), 400

    with mail_lock:
        emails = mailbox.get(email_addr, [])
        mailbox[email_addr] = [m for m in emails if m["id"] != email_id]

    return jsonify({"success": True})


@app.route("/api/delete-all", methods=["DELETE"])
def api_delete_all():
    """Hapus semua email di inbox."""
    email_addr = request.args.get("email", "").lower()
    if not email_addr:
        email_addr = session.get("email", "")
    if not email_addr:
        return jsonify({"error": "Email address tidak ditemukan"}), 400

    with mail_lock:
        mailbox[email_addr] = []

    return jsonify({"success": True})


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    """Force refresh inbox dari Gmail."""
    new_count = fetch_emails_from_gmail()
    return jsonify({"new_emails": new_count})


@app.route("/api/stats")
def api_stats():
    """Statistik server."""
    with mail_lock:
        total_addresses = len(mailbox)
        total_emails = sum(len(v) for v in mailbox.values())

    return jsonify({
        "domain": DOMAIN,
        "active_addresses": total_addresses,
        "total_emails": total_emails,
        "imap_configured": bool(GMAIL_EMAIL and GMAIL_APP_PASSWORD),
        "poll_interval": POLL_INTERVAL,
    })


@app.route("/health")
def health():
    """Health check endpoint untuk Render."""
    return jsonify({"status": "ok", "domain": DOMAIN})


# ---------------------------------------------------------------------------
# Start IMAP poller saat app dimuat (untuk gunicorn dan flask)
# ---------------------------------------------------------------------------

_poller_started = False
_poller_lock = threading.Lock()


def ensure_poller_started():
    global _poller_started
    with _poller_lock:
        if _poller_started:
            return
        if not (GMAIL_EMAIL and GMAIL_APP_PASSWORD):
            print("[WARN] GMAIL_EMAIL atau GMAIL_APP_PASSWORD belum diset. IMAP poller tidak jalan.")
            print("[WARN] Set environment variables di .env atau di Render dashboard.")
            _poller_started = True
            return
        thread = threading.Thread(target=imap_poll_loop, daemon=True)
        thread.start()
        _poller_started = True


# Jalankan saat module dimuat (works for gunicorn juga)
ensure_poller_started()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"[WEB] TempMail running at http://localhost:{port}")
    print(f"[WEB] Domain: @{DOMAIN}")
    print(f"[IMAP] Source Gmail: {GMAIL_EMAIL or '(not configured)'}")
    app.run(host="0.0.0.0", port=port, debug=False)
