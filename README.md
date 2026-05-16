# TNBTS Booking Bot

Bot otomatisasi pengisian form booking di [bromotenggersemeru.id](https://bromotenggersemeru.id/) menggunakan **Python + Playwright**.

Bot ini dibuat berdasarkan tampilan halaman booking site (contoh: `lembah-watangan`) dan secara otomatis:

1. Login (jika dibutuhkan)
2. Memilih **Pintu Masuk**, **Jenis Kendaraan**, dan **Jumlah Kendaraan**
3. Mengisi **Tanggal Berangkat** & **Tanggal Pulang**
4. Mengisi **Data Ketua Kelompok** (nama, kebangsaan, jenis kelamin, identitas, no telp)
5. Membuka modal **Form Anggota** dan menambahkan **satu atau lebih grup anggota** (laki-laki + perempuan + kebangsaan) — sesuai gambar ke-3
6. Memilih **Metode Pembayaran** & menyetujui Persyaratan
7. (Opsional) menekan tombol **CONFIRM BOOKING**

> Default mode adalah **dry-run** (`submit: false`) — form akan terisi tapi tombol Confirm tidak ditekan, supaya kamu bisa review dulu.

---

## 1. Prasyarat

- Python 3.9+
- Akun terdaftar di bromotenggersemeru.id

## 2. Setup

```bash
# clone repo lalu masuk ke folder
cd bot

# install dependency
pip install -r requirements.txt

# install browser Chromium untuk Playwright
python -m playwright install chromium
```

## 3. Konfigurasi

### a. Kredensial & URL — `.env`

```bash
cp .env.example .env
```

Isi `.env`:

```
TNBTS_USERNAME=email_anda@example.com
TNBTS_PASSWORD=password_anda
BOOKING_URL=https://bromotenggersemeru.id/booking/site/lembah-watangan?date_depart=2026-05-16
HEADLESS=false
SLOW_MO=200
```

### b. Data booking — `config.json`

```bash
cp config.example.json config.json
```

Edit `config.json` sesuai kebutuhan:

```json
{
  "booking": {
    "pintu_masuk": "Cemoro Lawang",
    "jenis_kendaraan": "Roda 4",
    "jumlah_kendaraan": "1",
    "tanggal_berangkat": "16-05-2026",
    "tanggal_pulang": "17-05-2026"
  },
  "ketua": {
    "nama": "Tukul Ahmad",
    "kebangsaan": "Indonesia",
    "jenis_kelamin": "Laki-laki",
    "jenis_identitas": "KTP",
    "nomor_identitas": "3501234567890001",
    "no_telp": "081234567890"
  },
  "anggota": [
    { "anggota_laki_laki": 2, "anggota_perempuan": 4, "kebangsaan": "Indonesia" },
    { "anggota_laki_laki": 1, "anggota_perempuan": 0, "kebangsaan": "Algeria" }
  ],
  "metode_pembayaran": "BNI",
  "setujui_syarat": true,
  "submit": false
}
```

**Field penting:**

| Field | Keterangan |
|---|---|
| `anggota` | Array — tiap entri = satu kali klik tombol **Tambah** + isi modal **Form Anggota**. Bisa ada banyak grup (misal grup WNI dan grup WNA). |
| `submit` | `false` = bot hanya mengisi form, **tidak** menekan Confirm. `true` = bot menekan Confirm Booking. |
| `setujui_syarat` | Centang checkbox persyaratan. |

## 4. Menjalankan

```bash
python bot.py
```

Browser akan terbuka (kecuali `HEADLESS=true`), bot mengisi form, lalu menahan halaman 60 detik untuk review. Screenshot hasil akan disimpan ke folder `screenshots/`.

## 5. Tips Debugging

- Set `HEADLESS=false` agar bisa melihat apa yang dilakukan bot
- Set `SLOW_MO=400` (atau lebih besar) untuk memperlambat klik
- Jika selektor dropdown gagal (mis. nama opsi sedikit beda), bot akan mencetak daftar opsi yang tersedia di terminal — copy nilai persis ke `config.json`
- File `screenshots/error.png` dibuat otomatis saat terjadi error

## 6. Disclaimer

Gunakan bot ini secara bertanggung jawab dan sesuai S&K bromotenggersemeru.id. Bot tidak melewati antrian/CAPTCHA dan tidak ditujukan untuk scalping tiket.
