# TempMail @sanz.com

Aplikasi web email sementara (temporary/disposable email) dengan domain custom `@sanz.com`.

## Fitur

- **Generate Email** - Buat alamat email random atau custom username
- **Inbox Real-time** - Auto-refresh setiap 5 detik
- **Baca Email** - Tampilkan email plain text dan HTML
- **Copy to Clipboard** - Salin alamat email dengan satu klik
- **Auto Expire** - Email otomatis dihapus setelah 30 menit
- **SMTP Server Built-in** - Terima email langsung di port 2525
- **REST API** - Endpoint API untuk integrasi
- **Responsive** - Tampilan optimal di desktop dan mobile

## Screenshot

Tampilan dark mode modern dengan gradient biru-ungu.

## Setup & Instalasi

```bash
cd tempmail

# Install dependencies
pip install -r requirements.txt

# Jalankan aplikasi
python app.py
```

Aplikasi akan berjalan di:
- **Web Interface**: http://localhost:5000
- **SMTP Server**: port 2525

## Cara Penggunaan

1. Buka http://localhost:5000
2. Klik **"Generate Email"** atau ketik username custom
3. Alamat email `xxx@sanz.com` akan dibuat
4. Kirim email ke alamat tersebut (via SMTP port 2525)
5. Email masuk akan otomatis muncul di inbox

## Testing Kirim Email

Gunakan Python untuk mengirim test email:

```python
import smtplib
from email.mime.text import MIMEText

msg = MIMEText("Halo ini email testing!")
msg["Subject"] = "Test Email"
msg["From"] = "sender@example.com"
msg["To"] = "username@sanz.com"

with smtplib.SMTP("localhost", 2525) as server:
    server.send_message(msg)

print("Email terkirim!")
```

Atau via command line:

```bash
python -c "
import smtplib
from email.mime.text import MIMEText
msg = MIMEText('Hello from TempMail!')
msg['Subject'] = 'Test'
msg['From'] = 'test@example.com'
msg['To'] = 'user@sanz.com'
with smtplib.SMTP('localhost', 2525) as s:
    s.send_message(msg)
"
```

## API Endpoints

| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| POST | `/api/generate` | Generate email baru |
| GET | `/api/inbox?email=xxx@sanz.com` | Ambil daftar email |
| GET | `/api/email/<id>?email=xxx@sanz.com` | Baca satu email |
| DELETE | `/api/delete/<id>?email=xxx@sanz.com` | Hapus satu email |
| DELETE | `/api/delete-all?email=xxx@sanz.com` | Hapus semua email |
| GET | `/api/stats` | Statistik server |

### Contoh API

**Generate email:**
```bash
curl -X POST http://localhost:5000/api/generate \
  -H "Content-Type: application/json" \
  -d '{"username": "myname"}'
```

Response:
```json
{
  "email": "myname@sanz.com",
  "expires_at": "2026-05-25 14:30:00",
  "expires_in_minutes": 30
}
```

## Konfigurasi

Environment variables (opsional):

| Variable | Default | Deskripsi |
|----------|---------|-----------|
| `PORT` | 5000 | Port web server |

## Catatan Produksi

Untuk deployment production:

1. **Ganti `app.secret_key`** dengan secret yang aman
2. **Gunakan Redis/Database** untuk menyimpan email (saat ini in-memory)
3. **Setup DNS MX Record** agar domain `sanz.com` mengarah ke server
4. **Gunakan port 25** untuk SMTP (butuh root/privilege)
5. **Tambahkan rate limiting** untuk mencegah abuse
6. **Gunakan Gunicorn/uWSGI** sebagai WSGI server

### DNS Setup (Produksi)

Tambahkan MX record di DNS domain `sanz.com`:

```
sanz.com.  IN  MX  10  mail.sanz.com.
mail.sanz.com.  IN  A   <IP_SERVER>
```

## Tech Stack

- **Backend**: Python, Flask, aiosmtpd
- **Frontend**: HTML5, CSS3, Vanilla JavaScript
- **Storage**: In-memory (dictionary)

## License

MIT
