# Telegram Userbot (Akun Asli)

Userbot Telegram berbasis **akun pribadi**, bukan bot dari @BotFather.
Berbasis **Python 3.10+** dan **Telethon** (async/await). Struktur modular,
lengkap dengan logging console + file dan database SQLite.

Kode OTP hanya diminta **satu kali**: hasilnya disimpan di
`data/userbot.session`, lalu dipakai otomatis pada setiap start berikutnya.

## Fitur Utama: Deteksi Role & Hak Akses

Bot bisa membedakan siapa yang sedang mengirim perintah, lengkap dengan
rinciannya:

| Role              | Artinya                                                   | Perintah admin |
| ----------------- | --------------------------------------------------------- | -------------- |
| **Pemilik bot**   | Akun yang menjalankan userbot ini (otomatis akses penuh)   | ya             |
| **Pemilik grup**  | Pembuat grup/supergroup tempat perintah dikirim             | ya             |
| **Admin grup**    | Admin Telegram di grup tersebut                            | ya             |
| **Admin daftar**  | ID-nya ada di `ADMIN_IDS` pada `.env`                       | ya             |
| **Member**        | Anggota biasa                                               | tidak          |
| **Bot**           | Akun bot, bukan manusia                                    | tidak          |
| **Dilarang**      | Sudah dibanned dari grup                                   | tidak          |
| **Luar**          | Bukan anggota grup (atau di luar grup)                     | tidak          |

Setiap user juga bisa dicek status online, nomor telepon, status premium,
riwayat pesan, dan **hak admin lengkapnya** (hapus pesan, ban user, pin,
tambah admin, dan seterusnya) lewat satu perintah.

Fitur lain:

- Semua perintah diawali garis miring (`/`). **Tidak ada auto-reply pesan
  teks biasa** — akun tidak pernah mengirim pesan tanpa diminta.
- Login QR (`--qr`) sebagai cara tercepat, tanpa menunggu kode OTP
- Logging ke `logs/bot.log` (rotasi) + console
- Error handler global — tidak ada crash diam-diam
- Database SQLite `data/bot.db` — user, role terakhir, dan counter pesan
- Keamanan grup: whitelist `ALLOWED_GROUP_IDS`

## Daftar Perintah

Semua perintah diawali garis miring (`/`). Teks balasan **tanpa emoji**:
judul memakai huruf kapital bergaris `=`, isi memakai label rata kiri
dengan `:`. Tombol inline juga memakai label kapital polos.

Publik (boleh dipakai semua orang):

| Perintah           | Deskripsi                                                    |
| ------------------ | ------------------------------------------------------------ |
| `/start`           | Perkenalan + tombol pintasan                                  |
| `/menu`            | Menu lengkap: foto profil + tombol semua perintah            |
| `/menu sederhana`  | Menu versi teks singkat, tanpa foto                          |
| `/halo`            | Sapaan personal beserta role kamu                             |
| `/id`              | Detail akun: ID, status, telepon, role, riwayat pesan         |
| `/id @username`    | Detail user lain                                             |
| `/ping`            | Cek apakah bot masih responsif                                |
| `/echo <teks>`     | Mengulang teks yang kamu kirim                                |
| `/help`            | Daftar lengkap semua perintah                                 |
| `/groups [cari]`   | Daftar grup yang diikuti, untuk mencari `ALLOWED_GROUP_IDS`   |

Khusus pemilik bot & admin grup:

| Perintah           | Deskripsi                                                      |
| ------------------ | -------------------------------------------------------------- |
| `/perms [user]`    | Hak akses lengkap seorang user di grup ini                     |
| `/admins`          | Daftar admin dan pemilik grup                                   |
| `/members [cari]`  | Semua anggota grup beserta role-nya                             |
| `/salam [teks]`    | Lihat atau atur template ucapan selamat datang                 |
| `/pamit [teks]`    | Lihat atau atur template ucapan perpisahan                     |
| `/on` `/off`       | Nyalakan atau matikan ucapan otomatis di grup ini              |
| `/admin`           | Panel admin: konfigurasi + ringkasan akses                      |
| `/stat`            | Statistik database dan uptime userbot                           |

Perintah admin dijaga dekorator `admin_only`: hanya pemilik bot, admin
grup, dan ID yang terdaftar di `ADMIN_IDS` yang bisa membukanya.

## Perintah `/menu` dan Foto Profil

`/menu` mengirim foto beserta daftar tombol. Sumber gambar dipilih
berurutan:

1. Nilai `MENU_IMAGE` di `.env` (path relatif dari folder project).
2. Berkas gambar pertama di `data/foto/` (`.jpg`, `.jpeg`, `.png`, `.webp`).
3. Foto profil Telegram akun ini, diunduh ke `data/foto/profil.jpg`.

Jadi saat gambar profil belum dibuat, letakkan saja di `data/foto/`.
Kalau folder itu kosong, bot otomatis memakai foto profil Telegram
sendiri tanpa perlu konfigurasi apa pun. Menu admin (`/admin`, `/perms`,
`/members`, `/salam`, `/pamit`) hanya muncul untuk admin.

## Ucapan Otomatis di Grup

Saat ada anggota yang bergabung atau keluar, bot mengirim ucapan otomatis
di **semua grup yang diikuti akun ini** - bukan hanya grup yang ada di
`ALLOWED_GROUP_IDS`. Whitelist itu hanya berlaku untuk perintah.

Ucapan bisa diatur per grup:

```
/salam                      lihat template yang aktif
/salam Selamat datang {nama} di {grup}
/salam default              kembali ke template bawaan
/pamit <teks>               sama untuk ucapan perpisahan
/off                        matikan ucapan di grup ini
/on                         nyalakan lagi
```

Penanda yang bisa dipakai: `{nama}`, `{grup}`, `{jumlah}`, `{baris}`,
`{ctx}` (mention bot), dan `{judul}` (dipakai untuk judul dengan garis
pisah). Teks per grup disimpan di `data/ucapan.json`.

Matikan semuanya dari `.env` dengan `WELCOME_ENABLED=0` dan/atau
`GOODBYE_ENABLED=0`.

## Struktur Project

```
telegram-bot/
├── .env                     # kredensial (jangan di-share)
├── .env.example
├── jalankan.bat             # menu jalan cepat di Windows
├── layanan.bat              # menu service background (install/stop/status)
├── service.ps1              # daftarkan autostart ke Task Scheduler
├── server.py                # supervisor: jaga main.py tetap hidup
├── requirements.txt
├── README.md
├── config.py                # baca .env, validasi, daftar admin & whitelist
├── main.py                  # entry point + argumen --qr / --cek / --reset
├── uji.py                   # smoke test koneksi
├── uji_handler.py           # uji seluruh handler & deteksi role
├── uji_database.py          # uji skema, migrasi, dan counter database
├── cek_teks.py              # deteksi karakter asing yang bocor ke source
├── handlers/
│   ├── __init__.py          # registrasi handler + error handler global
│   ├── start.py             # /start, /halo
│   ├── menu.py              # /menu, /menu sederhana (foto + tombol)
│   ├── help.py              # /help
│   ├── id.py                # /id, /perms
│   ├── echo.py              # /echo
│   ├── groups.py            # /groups
│   ├── stat.py              # /ping, /stat
│   ├── members.py           # /admins, /members
│   ├── ucapan.py            # listener join/leave + /salam /pamit /on /off
│   └── admin.py             # /admin
├── utils/
│   ├── login.py             # pembuatan klien + alur login (OTP/QR)
│   ├── permissions.py       # deteksi role, status, dan hak akses
│   ├── tampilan.py          # helper teks polos tanpa emoji
│   ├── ucapan.py            # template & penyimpanan ucapan per grup
│   ├── ratelimit.py         # pembatas laju kirim (anti flood-wait)
│   ├── commands.py          # pola regex perintah + filter whitelist
│   ├── context.py           # konteks bersama antar handler
│   ├── database.py          # SQLite: users, messages, migrasi role
│   └── logger.py            # konfigurasi logging
├── data/
│   ├── userbot.session      # otorisasi akun (dibuat otomatis, jangan di-share)
│   ├── server.lock          # pengunci: hanya 1 supervisor boleh jalan
│   ├── stop.flag            # ephemeral: perintah berhenti
│   ├── ucapan.json          # template ucapan per grup (dari /salam /pamit)
│   ├── foto/                # gambar untuk /menu (opsional)
│   └── bot.db
└── logs/                    # bot.log + server.log
```

## Cara Kerja Bot (WAJIB BACA)

Telegram membedakan **bot** dan **user**; kode untuk keduanya sama sekali
berbeda. Project ini memakai **akun Telegram asli** dengan protokol MTProto,
bukan bot token. Konsekuensinya:

- Akun yang dipakai akan terlihat online di daftar "Active Sessions" di aplikasi
  Telegram kamu.
- Satu akun hanya boleh menjalankan **satu** instance userbot. Menjalankan dua
  kali sekaligus membuat file session terkunci dan program gagal start.
- Jangan dipakai untuk spam atau raid grup: akun bisa dibekukan Telegram.
  Jeda antar pesan otomatis (SEND_DELAY) sengaja dijaga.

## Setup (Windows)

### 1. Persiapkan virtual environment

```bat
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Ambil API_ID dan API_HASH (gratis, sekali saja)

1. Buka **https://my.telegram.org** di browser
2. Masukkan nomor Telegram kamu (format internasional, misal `62812...`),
   lalu tekan **Next**
3. Telegram mengirim kode ke aplikasi Telegram kamu — masukkan kodenya
4. Setelah masuk, buka menu **Tools → API development credentials**
5. Isi form bebas, contoh:
   - App title: `Userbot Bot Telegram`
   - Short name: `userbot`
   - Platform: `Desktop`
6. Klik **Create application**
7. Salin **App api_id** dan **App api_hash** yang muncul

### 3. Tulis kredensial ke `.env`

```bat
copy .env.example .env
notepad .env
```

Isi minimal:

```env
API_ID=12345678
API_HASH=0123456789abcdef0123456789abcdef
PHONE=6281234567890
```

| Key              | Wajib | Keterangan                                                       |
| ---------------- | ----- | ---------------------------------------------------------------- |
| `API_ID`         | ya    | Angka dari my.telegram.org, tanpa spasi/tanda `+`                 |
| `API_HASH`       | ya    | String 32 karakter, tempel apa adanya                            |
| `PHONE`          | tidak | Nomor akun; boleh kosong lalu ditanya di console                  |
| `OTP_CODE`       | tidak | Untuk login tanpa input keyboard (IDE/service). Hapus setelah dipakai |
| `TWOFA_PASSWORD` | tidak | Sama seperti di atas, untuk akun ber-2FA                          |
| `ADMIN_IDS`      | tidak | Pisahkan dengan koma; kosong = akun ini otomatis jadi admin       |
| `ALLOWED_GROUP_IDS` | tidak | ID grup (negatif), pisahkan koma; kosong = tanpa grup            |
| `SEND_DELAY`     | tidak | Jeda minimum antar pesan otomatis, default `0.3` detik            |
| `LOG_LEVEL`      | tidak | `DEBUG` / `INFO` / `WARNING` / `ERROR`                            |

Cek dulu kredensialnya tanpa menyentuh jaringan:

```bat
python main.py --cek
```

### 4. Login pertama kali (pilih salah satu)

**Cara tercepat — QR, tanpa kode OTP:**

```bat
python main.py --qr
```

Akan muncul URL `tg://login`. Buka URL itu di Telegram Desktop atau HP yang
sudah login, lalu setujui. Tidak ada kode yang perlu diketik.

**Cara biasa — kode OTP:**

```bat
python main.py
```

Program mengirim kode ke aplikasi Telegram kamu dan menanyakannya di console.
Kode hanya diminta satu kali; setelah itu session tersimpan.

### 5. Jalankan

```bat
python main.py        # atau klik ganda jalankan.bat
```

Saat start, log akan menyebutkan berapa detik proses login/aktivasi —
start setelah session terbentuk biasanya di bawah 2 detik.

## Menjalankan sebagai Service (tanpa cmd window)

Kalau mau userbot tetap hidup di background, jangan pakai `python main.py`
langsung. Dua file baru mengurus itu:

| File          | Fungsi                                                             |
| ------------- | ------------------------------------------------------------------ |
| `server.py`   | Supervisor: menjalankan `main.py` dan me-restart bila mati         |
| `service.ps1` | Mendaftarkan supervisor ke Task Scheduler (autostart saat login)  |
| `layanan.bat` | Menu klik-ganda untuk install / start / stop / restart / status    |

Cara pakai (klik ganda `layanan.bat`, lalu pilih **1. Install**):

```bat
layanan.bat                 :: menu
powershell -File service.ps1 install     ::-autostart + jalan sekarang
powershell -File service.ps1 status      :: cek status + log
powershell -File service.ps1 stop        :: hentikan
powershell -File service.ps1 uninstall   :: hapus autostart
```

Yang происходит setelah install:

- Userbot jalan pakai `pythonw.exe`, jadi **tidak ada jendela cmd sama sekali**.
- Otomatis hidup 20 detik setelah kamu login Windows.
- Kalau `main.py` crash atau koneksi putus, supervisor restarting-nya
  (jeda 2 detik, naik sampai 60 detik).
- Tidak butuh NSSM, tidak butuh hak admin, tidak butuh password tersimpan.

Log:

| Log                  | Isi                                              |
| -------------------- | ------------------------------------------------ |
| `logs\bot.log`       | Log userbot Telethon                              |
| `logs\server.log`    | Log supervisor: start, crash, dan restart         |

Cek jalan/tidaknya:

```bat
powershell -File service.ps1 status
venv\Scripts\python.exe server.py status
```

> Service ini berjalan selama kamu login. Kalau Windows restart, userbot
> hidup kembali setelah login. Untuk berhenti total, buka Task Scheduler
> lalu hapus task `TelegramUserbot`, atau jalankan `service.ps1 uninstall`.

## Perintah CLI

| Perintah              | Fungsi                                                      |
| --------------------- | ----------------------------------------------------------- |
| `python main.py`      | Jalankan userbot (login OTP bila session belum ada)        |
| `python main.py --qr` | Login lewat QR                                              |
| `python main.py --cek`| Tampilkan status konfigurasi + panduan, tanpa konek         |
| `python main.py --reset` | Hapus `data/userbot.session` untuk login ulang dari nol   |
| `python server.py start` | Jalankan supervisor (mode background, tanpa console)    |
| `python server.py stop`  | Minta supervisor + child berhenti                     |
| `python server.py status` | Status singkat + 10 baris log terakhir              |
| `python uji.py`       | Smoke test: login lalu kirim pesan uji ke chat sendiri      |

## Cara Menguji

Jalankan uji otomatis dulu (tidak menyentuh Telegram):

```bat
venv\Scripts\python.exe uji_handler.py
venv\Scripts\python.exe uji_database.py
```

Untuk uji langsung, pakai **akun Telegram lain** — pesan yang kamu kirim
dari akun sendiri diabaikan Telethon (`incoming=True`):

1. Dari akun lain, kirim `/start`, `/halo`, `/help`, `/id`, `/ping`,
   `/echo halo` — semuanya harus dibalas
2. Kirim `/perms`, `/admins`, `/members`, `/admin`, `/stat` dari akun lain —
   harus ditolak dengan pesan "Akses ditolak" kalau pengirim bukan admin
3. Untuk tes grup: masukkan akun ini ke grup, kirim `/groups` di chat pribadi
   untuk melihat ID grup, tulis ID itu ke `ALLOWED_GROUP_IDS`, restart

## Pengembangan

1. Buat file baru di `handlers/` (contoh: `handlers/ping.py`)
2. Definisikan fungsi `register(ctx)` yang memasang callback Telethon
3. Tambahkan modul ke tuple `_HANDLER_MODULES` di `handlers/__init__.py`
4. Tulis uji di `uji_handler.py`, lalu jalankan

## Troubleshooting

| Masalah                                              | Solusi                                                                    |
| ---------------------------------------------------- | ------------------------------------------------------------------------- |
| `API_ID belum diisi`                                 | Ikuti langkah 2, lalu `python main.py --cek` untuk memastikan terbaca     |
| `API_ID atau API_HASH salah`                         | Salin ulang dari my.telegram.org; jangan ada spasi atau tanda `+`          |
| `The api_id/api_hash combination is invalid`        | Sama seperti di atas — biasanya `API_HASH` terpotong atau tidak lengkap |
| Program berhenti saat meminta kode OTP              | Jalankan dari cmd/PowerShell, atau isi `OTP_CODE` di `.env`               |
| `File session sedang dipakai proses lain`            | Userbot sudah jalan di jendela lain; tutup jendela tersebut                |
| `Session lama tidak valid lagi`                      | `python main.py --reset`, lalu login ulang                                  |
| `MASALAH: FloodWait` / sering kena throttle          | Naikkan `SEND_DELAY` di `.env` (misal `1.5`)                               |
| `/admins` bilang tidak bisa baca grup                | Grup basic tidak mendukung daftar admin; pakai supergroup                 |
| Akses ditolak padahal kamu admin                     | Cek dengan `/id`; daftarkan ID kamu di `ADMIN_IDS` lalu restart            |
| Gagal konek / timeout                                | Cek internet, VPN, firewall, atau ganti jaringan (Wi-Fi / hotspot)         |
| `ActivationRequiredError`                              | Akun kamu harus lebih dulu aktif di aplikasi Telegram sebelum dipakai     |
