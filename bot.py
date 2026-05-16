"""
Bot booking TNBTS (Taman Nasional Bromo Tengger Semeru)
URL: https://bromotenggersemeru.id/booking/site/<site>?date_depart=YYYY-MM-DD

Bot ini mengisi form booking secara otomatis, termasuk:
- Memilih pintu masuk, jenis & jumlah kendaraan
- Mengisi tanggal berangkat & pulang
- Mengisi data ketua kelompok
- Membuka modal "Form Anggota" dan menambah satu / banyak grup anggota
  (dengan jumlah laki-laki, perempuan, dan kebangsaan yg berbeda)
- Memilih metode pembayaran & menyetujui S&K
- (Opsional) menekan tombol CONFIRM BOOKING

Cara menjalankan:
    pip install -r requirements.txt
    python -m playwright install chromium
    cp .env.example .env       # isi kredensial
    cp config.example.json config.json   # isi data booking
    python bot.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from playwright.sync_api import (
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def log(msg: str) -> None:
    print(f"[bot] {msg}", flush=True)


def load_config() -> dict[str, Any]:
    cfg_path = ROOT / "config.json"
    if not cfg_path.exists():
        log("config.json tidak ditemukan, fallback ke config.example.json")
        cfg_path = ROOT / "config.example.json"
    with cfg_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def select_by_label(page: Page, locator_selector: str, label: str) -> None:
    """Pilih <option> berdasarkan label (case-insensitive, partial match)."""
    if label is None or label == "":
        return
    el = page.locator(locator_selector).first
    el.wait_for(state="visible", timeout=15_000)

    # Coba exact label dulu, fallback ke value/text yang mengandung label
    try:
        el.select_option(label=label)
        return
    except Exception:
        pass

    options = el.locator("option").all_text_contents()
    target = None
    label_lower = label.strip().lower()
    for opt in options:
        if opt.strip().lower() == label_lower:
            target = opt
            break
    if target is None:
        for opt in options:
            if label_lower in opt.strip().lower():
                target = opt
                break
    if target is None:
        raise ValueError(
            f"Tidak menemukan opsi '{label}' pada selector {locator_selector}. "
            f"Opsi tersedia: {options}"
        )
    el.select_option(label=target)


def fill_if_visible(page: Page, selector: str, value: str) -> None:
    if value is None or value == "":
        return
    loc = page.locator(selector).first
    if loc.count() == 0:
        return
    loc.wait_for(state="visible", timeout=10_000)
    loc.fill("")
    loc.fill(str(value))


# ---------------------------------------------------------------------------
# Bot steps
# ---------------------------------------------------------------------------
def login_if_needed(page: Page) -> None:
    """Login otomatis jika halaman redirect ke login.
    Asumsi: form login memiliki input email/username & password.
    """
    username = os.getenv("TNBTS_USERNAME")
    password = os.getenv("TNBTS_PASSWORD")
    if not username or not password:
        log("Kredensial login tidak diset, skip auto-login.")
        return

    if "login" not in page.url.lower():
        return

    log("Halaman login terdeteksi, mencoba login otomatis...")
    # Mencoba beberapa kemungkinan selector
    for sel in ['input[name="email"]', 'input[type="email"]', 'input[name="username"]']:
        if page.locator(sel).count():
            page.locator(sel).first.fill(username)
            break
    for sel in ['input[name="password"]', 'input[type="password"]']:
        if page.locator(sel).count():
            page.locator(sel).first.fill(password)
            break
    # Submit
    for sel in [
        'button[type="submit"]',
        'button:has-text("Login")',
        'button:has-text("Masuk")',
        'input[type="submit"]',
    ]:
        if page.locator(sel).count():
            page.locator(sel).first.click()
            break
    page.wait_for_load_state("networkidle", timeout=30_000)


def fill_main_form(page: Page, cfg: dict[str, Any]) -> None:
    booking = cfg.get("booking", {})

    # Pintu Masuk
    select_by_label(
        page,
        'select[name="pintu_masuk"], select[name="entry_gate"], '
        'label:has-text("Pintu Masuk") + select, '
        'div:has(> label:has-text("Pintu Masuk")) select',
        booking.get("pintu_masuk", ""),
    )

    # Jenis Kendaraan
    select_by_label(
        page,
        'select[name="jenis_kendaraan"], select[name="vehicle_type"], '
        'div:has(> label:has-text("Jenis Kendaraan")) select',
        booking.get("jenis_kendaraan", ""),
    )

    # Jumlah Kendaraan
    select_by_label(
        page,
        'select[name="jumlah_kendaraan"], select[name="vehicle_count"], '
        'div:has(> label:has-text("Jumlah Kendaraan")) select',
        str(booking.get("jumlah_kendaraan", "")),
    )

    # Tanggal Berangkat (biasanya sudah terisi dari URL ?date_depart=)
    if booking.get("tanggal_berangkat"):
        fill_if_visible(
            page,
            'input[name="tanggal_berangkat"], input[name="date_depart"], '
            'input[placeholder*="Berangkat" i]',
            booking["tanggal_berangkat"],
        )

    # Tanggal Pulang
    fill_if_visible(
        page,
        'input[name="tanggal_pulang"], input[name="date_return"], '
        'input[placeholder*="Pulang" i]',
        booking.get("tanggal_pulang", ""),
    )
    # Tutup datepicker (klik di luar)
    page.keyboard.press("Escape")


def fill_ketua(page: Page, cfg: dict[str, Any]) -> None:
    ketua = cfg.get("ketua", {})

    fill_if_visible(
        page,
        'input[name="nama_ketua"], input[name="leader_name"], '
        'input[placeholder*="nama sesuai" i]',
        ketua.get("nama", ""),
    )
    select_by_label(
        page,
        'div:has(> label:has-text("Kebangsaan")) select:visible',
        ketua.get("kebangsaan", ""),
    )
    select_by_label(
        page,
        'select[name="jenis_kelamin"], '
        'div:has(> label:has-text("Jenis Kelamin")) select',
        ketua.get("jenis_kelamin", ""),
    )
    select_by_label(
        page,
        'select[name="jenis_identitas"], '
        'div:has(> label:has-text("Jenis Identitas")) select',
        ketua.get("jenis_identitas", ""),
    )
    fill_if_visible(
        page,
        'input[name="nomor_identitas"], input[name="id_number"], '
        'input[placeholder*="Nomor Kartu" i]',
        ketua.get("nomor_identitas", ""),
    )
    fill_if_visible(
        page,
        'input[name="no_telp"], input[name="phone"], '
        'input[placeholder*="No Telp" i]',
        ketua.get("no_telp", ""),
    )


def add_anggota(page: Page, anggota_list: list[dict[str, Any]]) -> None:
    """Buka modal 'Form Anggota' dan tambahkan tiap grup anggota.

    anggota_list: list of {anggota_laki_laki, anggota_perempuan, kebangsaan}
    """
    if not anggota_list:
        log("Tidak ada data anggota di config, skip.")
        return

    for idx, group in enumerate(anggota_list, start=1):
        log(f"Menambah grup anggota #{idx}: {group}")

        # Klik tombol "Tambah" di section Data Anggota
        tambah_btn = page.locator(
            'button:has-text("Tambah"), a:has-text("Tambah")'
        ).filter(has_not_text="Anggota").first
        # fallback: tombol Tambah pertama yg ada di area Data Anggota
        if tambah_btn.count() == 0:
            tambah_btn = page.locator(
                'div:has(> *:has-text("Data Anggota")) >> button:has-text("Tambah")'
            ).first
        tambah_btn.scroll_into_view_if_needed()
        tambah_btn.click()

        # Tunggu modal "Form Anggota" muncul
        modal = page.locator('div.modal:visible, [role="dialog"]:visible').first
        modal.wait_for(state="visible", timeout=10_000)

        # Isi field di modal
        select_by_label(
            page,
            'div:has(> label:has-text("Anggota Laki Laki")) select, '
            '[role="dialog"] select >> nth=0',
            str(group.get("anggota_laki_laki", 0)),
        )
        select_by_label(
            page,
            'div:has(> label:has-text("Anggota Perempuan")) select, '
            '[role="dialog"] select >> nth=1',
            str(group.get("anggota_perempuan", 0)),
        )
        select_by_label(
            page,
            'div:has(> label:has-text("Kebangsaan")) select:visible >> nth=-1, '
            '[role="dialog"] select >> nth=2',
            group.get("kebangsaan", ""),
        )

        # Klik tombol submit di modal
        modal.locator('button:has-text("Tambah Anggota")').first.click()

        # Tunggu modal tertutup
        try:
            modal.wait_for(state="hidden", timeout=10_000)
        except PlaywrightTimeoutError:
            log("Modal tidak tertutup otomatis, coba tutup paksa...")
            page.keyboard.press("Escape")

        # Beri jeda kecil agar tabel ter-update
        page.wait_for_timeout(500)


def fill_payment_and_submit(page: Page, cfg: dict[str, Any]) -> None:
    select_by_label(
        page,
        'select[name="metode_pembayaran"], select[name="payment_method"], '
        'div:has(> label:has-text("Metode Pembayaran")) select',
        cfg.get("metode_pembayaran", ""),
    )

    if cfg.get("setujui_syarat", True):
        cb = page.locator(
            'input[type="checkbox"]:near(:text("Persyaratan"))'
        ).first
        if cb.count() == 0:
            cb = page.locator('form input[type="checkbox"]').last
        try:
            cb.check()
        except Exception:
            cb.click()

    if cfg.get("submit", False):
        log("Menekan tombol CONFIRM BOOKING...")
        page.locator('button:has-text("CONFIRM BOOKING"), '
                     'button:has-text("Confirm Booking")').first.click()
        page.wait_for_load_state("networkidle", timeout=60_000)
    else:
        log("submit=false → form sudah terisi, biarkan user yang menekan tombol.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run(playwright: Playwright) -> None:
    cfg = load_config()
    booking_url = os.getenv("BOOKING_URL") or cfg.get("booking_url")
    if not booking_url:
        raise SystemExit("BOOKING_URL belum diset di .env atau config.json")

    headless = os.getenv("HEADLESS", "false").lower() == "true"
    slow_mo = int(os.getenv("SLOW_MO", "150"))

    browser = playwright.chromium.launch(headless=headless, slow_mo=slow_mo)
    context = browser.new_context()
    page = context.new_page()

    try:
        log(f"Membuka {booking_url}")
        page.goto(booking_url, wait_until="domcontentloaded")

        login_if_needed(page)
        # Setelah login, kalau redirect, navigate ulang
        if "booking/site" not in page.url:
            page.goto(booking_url, wait_until="domcontentloaded")

        page.wait_for_load_state("networkidle", timeout=30_000)

        log("Mengisi form utama (pintu masuk, kendaraan, tanggal)...")
        fill_main_form(page, cfg)

        log("Mengisi data ketua kelompok...")
        fill_ketua(page, cfg)

        log("Menambahkan data anggota...")
        add_anggota(page, cfg.get("anggota", []))

        log("Mengisi metode pembayaran & konfirmasi...")
        fill_payment_and_submit(page, cfg)

        # Screenshot untuk dokumentasi
        screenshots_dir = ROOT / "screenshots"
        screenshots_dir.mkdir(exist_ok=True)
        ss_path = screenshots_dir / f"result_{int(time.time())}.png"
        page.screenshot(path=str(ss_path), full_page=True)
        log(f"Screenshot disimpan: {ss_path}")

        if not cfg.get("submit", False):
            log("Menahan browser tetap terbuka 60 detik untuk review manual...")
            page.wait_for_timeout(60_000)

    except Exception as e:
        log(f"ERROR: {e}")
        try:
            page.screenshot(path=str(ROOT / "screenshots" / "error.png"), full_page=True)
        except Exception:
            pass
        raise
    finally:
        context.close()
        browser.close()


def main() -> int:
    with sync_playwright() as p:
        run(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
