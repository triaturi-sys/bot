"""
Temporary Email Web Application
Domain: @sanz.com

Fitur:
- Generate email address random @sanz.com
- Terima email masuk (simulasi via SMTP server built-in)
- Inbox real-time dengan auto-refresh
- Hapus email otomatis setelah expired (30 menit)
- Copy email address ke clipboard
- API endpoint untuk integrasi
"""

from __future__ import annotations

import asyncio
import email
import random
import string
import threading
import time
import uuid
from datetime import datetime, timedelta
from email.policy import default as default_policy
from typing import Any

from aiosmtpd.controller import Controller
from aiosmtpd.smtp import Envelope, Session, SMTP
from flask import Flask, jsonify, render_template, request, session
from flask_cors import CORS

app = Flask(__name__)
app.secret_key = "tempmail-secret-key-change-in-production"
CORS(app)

# Domain untuk temp mail
DOMAIN = "sanz.com"

# Penyimpanan email di memory (production: gunakan Redis/DB)
# Format: {email_address: [{"id": ..., "from": ..., "subject": ..., "body": ..., "date": ..., "read": bool}]}
mailbox: dict[str, list[dict[str, Any]]] = {}

# Mapping session ke email address
active_addresses: dict[str, dict[str, Any]] = {}

# Lock untuk thread safety
mail_lock = threading.Lock()

# Waktu expired email (30 menit)
EMAIL_EXPIRE_MINUTES = 30


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

def generate_username(length: int = 10) -> str:
    """Generate random username untuk email."""
    chars = string.ascii_lowercase + string.digits
    return "".join(random.choice(chars) for _ in range(length))


def generate_email() -> str:
    """Generate alamat email temporary."""
    username = generate_username()
    return f"{username}@{DOMAIN}"


def cleanup_expired():
    """Hapus email dan address yang sudah expired."""
    while True:
        time.sleep(60)  # Check setiap menit
        now = datetime.now()
        with mail_lock:
            expired_keys = []
            for addr, info in active_addresses.items():
                if now > info["expires_at"]:
                    expired_keys.append(addr)
            for addr in expired_keys:
                del active_addresses[addr]
                if addr in mailbox:
                    del mailbox[addr]


# ---------------------------------------------------------------------------
# SMTP Handler - Menerima email masuk
# ---------------------------------------------------------------------------

class TempMailHandler:
    """Handler untuk menerima email via SMTP."""

    async def handle_RCPT(self, server, session: Session, envelope: Envelope, address: str, rcpt_options: list):
        """Validasi recipient - hanya terima untuk domain kita."""
        if not address.endswith(f"@{DOMAIN}"):
            return f"550 No such user at {DOMAIN}"
        envelope.rcpt_tos.append(address)
        return "250 OK"

    async def handle_DATA(self, server, session: Session, envelope: Envelope):
        """Proses email masuk dan simpan ke mailbox."""
        try:
            msg = email.message_from_bytes(envelope.content, policy=default_policy)

            # Extract body
            body = ""
            html_body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    if content_type == "text/plain":
                        body = part.get_content()
                    elif content_type == "text/html":
                        html_body = part.get_content()
            else:
                content_type = msg.get_content_type()
                if content_type == "text/html":
                    html_body = msg.get_content()
                else:
                    body = msg.get_content()

            mail_data = {
                "id": str(uuid.uuid4()),
                "from": str(envelope.mail_from),
                "to": envelope.rcpt_tos,
                "subject": msg.get("subject", "(No Subject)"),
                "body": body,
                "html_body": html_body,
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "read": False,
            }

            with mail_lock:
                for recipient in envelope.rcpt_tos:
                    recipient_lower = recipient.lower()
                    if recipient_lower not in mailbox:
                        mailbox[recipient_lower] = []
                    mailbox[recipient_lower].append(mail_data)

            return "250 Message accepted for delivery"
        except Exception as e:
            print(f"[SMTP] Error processing email: {e}")
            return "500 Error processing message"


# ---------------------------------------------------------------------------
# Flask Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Halaman utama - tampilkan inbox temp mail."""
    return render_template("index.html", domain=DOMAIN)


@app.route("/api/generate", methods=["POST"])
def api_generate():
    """Generate email address baru."""
    data = request.get_json() or {}
    custom_name = data.get("username", "").strip().lower()

    if custom_name:
        # Validasi custom username
        if not all(c in string.ascii_lowercase + string.digits + "._-" for c in custom_name):
            return jsonify({"error": "Username hanya boleh huruf kecil, angka, titik, underscore, dan dash"}), 400
        if len(custom_name) < 3 or len(custom_name) > 30:
            return jsonify({"error": "Username harus 3-30 karakter"}), 400
        email_addr = f"{custom_name}@{DOMAIN}"
    else:
        email_addr = generate_email()

    expires_at = datetime.now() + timedelta(minutes=EMAIL_EXPIRE_MINUTES)

    with mail_lock:
        if email_addr not in mailbox:
            mailbox[email_addr] = []
        active_addresses[email_addr] = {
            "created_at": datetime.now(),
            "expires_at": expires_at,
        }

    session["email"] = email_addr

    return jsonify({
        "email": email_addr,
        "expires_at": expires_at.strftime("%Y-%m-%d %H:%M:%S"),
        "expires_in_minutes": EMAIL_EXPIRE_MINUTES,
    })


@app.route("/api/inbox")
def api_inbox():
    """Ambil daftar email di inbox."""
    email_addr = request.args.get("email", "").lower()
    if not email_addr:
        email_addr = session.get("email", "")

    if not email_addr or not email_addr.endswith(f"@{DOMAIN}"):
        return jsonify({"error": "Email address tidak valid"}), 400

    with mail_lock:
        emails = mailbox.get(email_addr, [])
        # Sort by date descending
        emails_sorted = sorted(emails, key=lambda x: x["date"], reverse=True)

    return jsonify({
        "email": email_addr,
        "count": len(emails_sorted),
        "messages": emails_sorted,
    })


@app.route("/api/email/<email_id>")
def api_read_email(email_id: str):
    """Baca satu email berdasarkan ID."""
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
    """Hapus satu email."""
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


@app.route("/api/stats")
def api_stats():
    """Statistik server."""
    with mail_lock:
        total_addresses = len(active_addresses)
        total_emails = sum(len(v) for v in mailbox.values())

    return jsonify({
        "domain": DOMAIN,
        "active_addresses": total_addresses,
        "total_emails": total_emails,
        "expire_minutes": EMAIL_EXPIRE_MINUTES,
    })


# ---------------------------------------------------------------------------
# SMTP Server startup
# ---------------------------------------------------------------------------

def start_smtp_server():
    """Jalankan SMTP server di background thread."""
    handler = TempMailHandler()
    controller = Controller(handler, hostname="0.0.0.0", port=2525)
    controller.start()
    print(f"[SMTP] Server berjalan di port 2525 untuk domain @{DOMAIN}")
    return controller


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os

    # Start cleanup thread
    cleanup_thread = threading.Thread(target=cleanup_expired, daemon=True)
    cleanup_thread.start()

    # Start SMTP server
    smtp_controller = start_smtp_server()

    # Start Flask web server
    port = int(os.environ.get("PORT", 5000))
    print(f"[WEB] Temp Mail berjalan di http://localhost:{port}")
    print(f"[WEB] Domain: @{DOMAIN}")
    print(f"[SMTP] Kirim email ke port 2525 untuk testing")

    try:
        app.run(host="0.0.0.0", port=port, debug=False)
    finally:
        smtp_controller.stop()
