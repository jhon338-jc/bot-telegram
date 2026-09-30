"""Login akun Telegram yang cepat: dipakai ulang bila session sudah ada.

Modul ini memisahkan urusan koneksi dari ``main.py``:

- :func:`build_client` membuat :class:`~telethon.TelegramClient` dengan
  parameter koneksi yang geared untuk start secepat mungkin.
- :func:`ensure_login` mencoba jalur tercepat lebih dulu: memakai session
  tersimpan (tanpa OTP sama sekali), lalu login OTP, dan QR bila diminta.
- :func:`check_setup` memvalidasi ``.env`` tanpa menyentuh jaringan,
  sehingga ``python main.py --cek`` bisa dipakai sebagai panduan.

Kode OTP maupun password 2FA boleh diisi di ``.env`` (``OTP_CODE`` dan
``TWOFA_PASSWORD``) agar program tidak perlu menunggu input keyboard -
berguna saat dijalankan dari IDE, Task Scheduler, atau service.
"""

from __future__ import annotations

import asyncio
import datetime
import getpass
import platform
import sqlite3
import sys
import time

from telethon import TelegramClient, errors
from telethon.tl.types import User

import config
from utils.logger import setup_logging

logger = setup_logging()

# Batas percobaan kode OTP sebelum menyerah, dan jeda sebelum meminta
# kode baru (mencegah terkena flood-wait dari permintaan OTP berulang).
MAX_CODE_ATTEMPTS: int = 3
RESEND_COOLDOWN: float = 5.0
# Link QR Telegram hanya hidup sekitar 30 detik, jadi link baru dibuat
# otomatis bila lewat, alih-alih menyuruh user mengulang program.
QR_ATTEMPTS: int = 50

SETUP_GUIDE: str = """
======================================================================
  LANGKAH 1 - Ambil API_ID dan API_HASH (sekali saja, gratis)
======================================================================
  1. Buka  https://my.telegram.org  di browser
  2. Masukkan nomor Telegram kamu (format internasional, misal 62812...)
     lalu tekan Next
  3. Telegram mengirim kode ke aplikasi Telegram kamu. Masukkan kodenya.
  4. Setelah masuk, buka menu  Tools  >  API development credentials
  5. Isi form bebas, contoh:
        App title    : Userbot Bot Telegram
        Short name   : userbot
        Platform     : Desktop
  6. Klik  Create application
  7. Salin  App api_id  dan  App api_hash  yang muncul

======================================================================
  LANGKAH 2 - Tulis ke file .env  (folder project ini)
======================================================================
        API_ID=12345678
        API_HASH=0123456789abcdef0123456789abcdef
        PHONE=6281234567890

  API_ID   = angka saja, tanpa spasi dan tanpa tanda +
  API_HASH = string 32 huruf/angka, tempel apa adanya
  PHONE    = nomor kamu, boleh dikosongkan (nanti ditanya di console)

======================================================================
  LANGKAH 3 - Login pertama kali (pilih salah satu)
======================================================================
  Cara TERCEPAT - login QR, tanpa kode OTP:
      python main.py --qr
    Akan muncul URL tg://login. Buka URL itu di Telegram Desktop atau
    HP yang SUDAH login, lalu setujui. Tidak perlu menunggu OTP.

  Cara biasa - kode OTP dikirim ke aplikasi Telegram kamu:
      python main.py
    Ikuti prompt di console. Kode hanya diminta SATU KALI karena
    hasilnya disimpan di  data\\userbot.session  dan dipakai otomatis
    pada start berikutnya.

======================================================================
  LANGKAH 4 - Jalankan
======================================================================
      python main.py         (akun yang sudah terhubung)
      .\\jalankan.bat        (Windows)
  Cek konfigurasi tanpa konek:  python main.py --cek
======================================================================
"""


def explain_error(exc: BaseException) -> str:
    """Terjemahkan error Telethon menjadi pesan yang bisa ditindaklanjuti.

    Args:
        exc: Exception yang ditangkap.

    Returns:
        Penjelasan singkat dalam bahasa Indonesia.
    """
    if isinstance(exc, sqlite3.OperationalError) and "lock" in str(exc).lower():
        return (
            "File session sedang dipakai proses lain. Userbot kemungkinan "
            "sudah jalan di jendela lain - tutup dulu, atau hentikan "
            "proses python yang masih berjalan."
        )
    if isinstance(exc, errors.ApiIdInvalidError):
        return (
            "API_ID atau API_HASH salah. Salin ulang dari my.telegram.org "
            "> Tools > API development credentials."
        )
    if isinstance(exc, (errors.AuthKeyError, errors.AuthKeyUnregisteredError)):
        return (
            "Session lama tidak valid lagi. Jalankan: python main.py --reset"
        )
    if isinstance(exc, errors.FloodWaitError):
        return f"Telegram meminta tunggu {exc.seconds} detik sebelum mengulang."
    if isinstance(exc, (ConnectionError, OSError, TimeoutError)):
        return (
            "Tidak bisa menghubungi server Telegram. Cek internet, VPN, "
            "firewall, atau coba ganti jaringan (Wi-Fi / hotspot)."
        )
    if isinstance(exc, config.ConfigError):
        return str(exc)
    return f"{type(exc).__name__}: {exc}"


def build_client() -> TelegramClient:
    """Buat klien Telethon dengan parameter koneksi untuk start cepat.

    Tiga nilai di sini menentukan kecepatan start: ``catch_up=False``
    supaya tidak menyusul riwayat chat yang tertinggal (penyebab start
    lama setelah app lama mati), ``sequential_updates=False`` supaya
    beberapa pesan diproses paralel, dan ``flood_sleep_threshold=30``
    supaya jeda singkat dari Telegram ditunggu otomatis, bukan
    menjadi error.

    Returns:
        Klien yang belum terhubung dan belum terautentikasi.
    """
    return TelegramClient(
        str(config.SESSION_PATH),
        config.API_ID,
        config.API_HASH,
        # Batas waktu koneksi physical ke server Telegram.
        timeout=10,
        # Retry request: sedikit dan cepat supaya tidak kelihatan macet.
        request_retries=3,
        connection_retries=5,
        retry_delay=1,
        auto_reconnect=True,
        # Tangani event boleh paralel: satu pesan_GROUP tidak menahan
        # pemrosesan pesan berikutnya.
        sequential_updates=False,
        # Flood-wait <= 30 detik ditunggu otomatis, bukan error.
        flood_sleep_threshold=30,
        raise_last_call_error=True,
        # Cache entity lebih besar = lebih sedikit request ke Telegram
        # saat banyak grup di whitelist.
        entity_cache_limit=10000,
        # Tidak mengejar update yang tertinggal saat offline. Ini membuat
        # start instan; pesan yang terlewat saat app mati memang tidak
        # akan diproses ulang.
        catch_up=False,
        device_model=platform.system() or "PC",
        system_version=platform.release() or "1.0",
        lang_code="id",
        system_lang_code="id",
    )


def _ask(prompt: str, *, secret: bool = False) -> str:
    """Minta input user dengan pesan error yang jelas bila console non-interaktif.

    Args:
        prompt: Teks pertanyaan yang ditampilkan.
        secret: Bila ``True``, ketikan disembunyikan (dipakai untuk 2FA).

    Returns:
        Isi jawaban user tanpa spasi di tepi.

    Raises:
        RuntimeError: Bila tidak ada console yang bisa menerima input.
    """
    try:
        if secret:
            return getpass.getpass(prompt).strip()
        return input(prompt).strip()
    except (EOFError, OSError):
        print()
        raise RuntimeError(
            "Program ini butuh input dari keyboard, tapi console tidak "
            "membaca input (jalan dari IDE/service?). Isi OTP_CODE atau "
            "TWOFA_PASSWORD di file .env, atau jalankan di cmd/PowerShell."
        ) from None
    except KeyboardInterrupt:
        print()
        raise RuntimeError("Dibatalkan user.") from None


def _resolve_phone() -> str:
    """Tentukan nomor telepon: dari ``.env`` atau ditanya ke user.

    Returns:
        Nomor dalam format internasional apa adanya.

    Raises:
        RuntimeError: Bila nomor dikosongkan.
    """
    phone = config.PHONE
    if not phone:
        phone = _ask("Masukkan nomor Telegram kamu (format internasional): ")
    if not phone:
        raise RuntimeError("Nomor telepon wajib diisi untuk login OTP.")
    return phone


async def _sign_in_with_2fa(client: TelegramClient) -> User:
    """Selesaikan login yang dilindungi two-step verification.

    Args:
        client: Klien yang sudah memegang ``phone_code_hash`` valid.

    Returns:
        Profil user yang berhasil diautentikasi.

    Raises:
        RuntimeError: Bila password salah terus-menerus.
    """
    password = config.TWOFA_PASSWORD
    for attempt in range(1, MAX_CODE_ATTEMPTS + 1):
        if not password:
            password = _ask("Masukkan password 2FA (tidak terlihat): ", secret=True)
        if not password:
            raise RuntimeError("Password 2FA wajib diisi.")
        try:
            me = await client.sign_in(password=password)
        except errors.PasswordHashInvalidError:
            password = ""
            logger.warning(
                "Password 2FA salah (percobaan %d/%d).", attempt, MAX_CODE_ATTEMPTS
            )
            continue
        return me
    raise RuntimeError("Password 2FA salah 3 kali, login dibatalkan.")


async def _login_with_otp(client: TelegramClient) -> User:
    """Login dengan kode OTP yang dikirim ke aplikasi Telegram.

    Kode salah akan ditanyakan ulang, dan kode kedaluwarsa otomatis
    diminta ulang. Bila ``OTP_CODE`` terisi di ``.env``, tidak ada
    input keyboard sama sekali.

    Args:
        client: Klien yang sudah terhubung.

    Returns:
        Profil user yang berhasil diautentikasi.

    Raises:
        RuntimeError: Bila semua percobaan kode gagal.
    """
    phone = _resolve_phone()
    logger.info("Mengirim kode OTP ke %s...", phone[-4:].rjust(len(phone), "*"))

    for attempt in range(1, MAX_CODE_ATTEMPTS + 1):
        await client.send_code_request(phone)
        code = config.OTP_CODE or _ask("Masukkan kode OTP dari Telegram: ")

        if not code:
            raise RuntimeError(
                "Kode OTP kosong. Isi OTP_CODE di .env bila console tidak "
                "membaca input."
            )

        try:
            return await client.sign_in(phone=phone, code=code.strip())
        except errors.SessionPasswordNeededError:
            return await _sign_in_with_2fa(client)
        except errors.PhoneCodeExpiredError:
            logger.warning("Kode OTP kedaluwarsa, mengirim ulang...")
            await asyncio.sleep(RESEND_COOLDOWN)
            continue
        except errors.PhoneCodeInvalidError:
            logger.warning("Kode OTP salah (percobaan %d/%d).", attempt, MAX_CODE_ATTEMPTS)
            if attempt >= MAX_CODE_ATTEMPTS:
                break
            await asyncio.sleep(RESEND_COOLDOWN)

    raise RuntimeError("Kode OTP salah/kedaluwarsa 3 kali, login dibatalkan.")


async def _login_with_qr(client: TelegramClient) -> User:
    """Login lewat QR: cara tercepat, tanpa OTP dan tanpa 2FA yang diketik.

    Args:
        client: Klien yang sudah terhubung.

    Returns:
        Profil user yang berhasil diautentikasi.
    """
    for attempt in range(1, QR_ATTEMPTS + 1):
        qr = await client.qr_login()
        expires = qr.expires.astimezone()
        remaining = (expires - datetime.datetime.now(expires.tzinfo)).total_seconds()
        print()
        print(f"  LOGIN CEPAT (QR) - percobaan {attempt}/{QR_ATTEMPTS}")
        print("  --------------------------------------------------")
        print(f"  {qr.url}")
        print()
        print("  Buka URL di atas di Telegram Desktop / HP yang sudah login,")
        print("  lalu setujui. Tidak perlu mengetik kode OTP.")
        print(f"  Berlaku {max(0, int(remaining))} detik lagi (sampai {expires:%H:%M:%S}).")
        print("  --------------------------------------------------")
        print()

        try:
            # Tunggu hanya sampai link kedaluwarsa, lalu link baru
            # dibuat otomatis pada percobaan berikutnya.
            return await qr.wait(timeout=max(5.0, remaining))
        except errors.SessionPasswordNeededError:
            return await _sign_in_with_2fa(client)
        except asyncio.TimeoutError:
            if attempt >= QR_ATTEMPTS:
                raise RuntimeError(
                    "QR tidak disetujui setelah beberapa percobaan. "
                    "Ulangi: python main.py --qr"
                ) from None
            logger.warning("QR belum disetujui, membuat link baru...")

    raise RuntimeError("Login QR gagal. Ulangi: python main.py --qr")


async def ensure_login(client: TelegramClient, *, use_qr: bool = False) -> User:
    """Hubungkan klien dan pastikan akun sudah terautentikasi.

    Jalur tercepat dipakai lebih dulu: bila ``data/userbot.session``
    sudah menyimpan otorisasi, proses selesai tanpa OTP dan tanpa satu
    pun permintaan login tambahan.

    Args:
        client: Klien hasil :func:`build_client`.
        use_qr: Bila ``True``, pakai login QR alih-alih kode OTP.

    Returns:
        Profil user yang sedang dijalankan.
    """
    started = time.perf_counter()
    await client.connect()

    me = await client.get_me()
    if me is not None:
        logger.info(
            "Sesi tersimpan dipakai (tanpa OTP) dalam %.2f dtk.",
            time.perf_counter() - started,
        )
        return me

    logger.info("Belum pernah login — mulai proses login satu kali.")
    if use_qr:
        me = await _login_with_qr(client)
    else:
        me = await _login_with_otp(client)

    session_file = config.SESSION_PATH.with_suffix(".session")
    logger.info(
        "Login berhasil sebagai %s (ID %s) dalam %.2f dtk.",
        me.first_name,
        me.id,
        time.perf_counter() - started,
    )
    if session_file.exists():
        logger.info(
            "Otorisasi tersimpan di %s - start berikutnya instan.", session_file
        )
    return me


def check_setup() -> bool:
    """Periksa ``.env`` tanpa membuka koneksi ke Telegram.

    Returns:
        ``True`` bila konfigurasi sah, ``False`` bila ada yang kurang.
    """
    print("Cek konfigurasi userbot")
    print("=" * 70)

    found = config.problems()
    checks = [
        ("API_ID", "terisi" if config.API_ID > 0 else "KOSONG"),
        ("API_HASH", "terisi" if config.API_HASH else "KOSONG"),
        ("PHONE", config.PHONE if config.PHONE else "kosong (ditanya saat login)"),
        ("ADMIN_IDS", ", ".join(map(str, config.ADMIN_IDS)) or "kosong (otomatis akun ini)"),
        (
            "ALLOWED_GROUP_IDS",
            ", ".join(map(str, config.ALLOWED_GROUP_IDS)) or "kosong (tanpa grup)",
        ),
        ("SEND_DELAY", f"{config.SEND_DELAY} detik"),
        ("SESSION_PATH", str(config.SESSION_PATH.with_suffix(".session"))),
    ]
    for name, value in checks:
        print(f"  {name:<18} : {value}")

    session_exists = config.SESSION_PATH.with_suffix(".session").exists()
    print(f"  {'SESSION ADA':<18} : {'ya' if session_exists else 'belum (login dulu)'}")
    print("=" * 70)

    if found:
        print("MASALAH:")
        for item in found:
            print(f"  - {item}")
        print()
        print(SETUP_GUIDE)
        return False

    if session_exists:
        print("Semua siap. Jalankan: python main.py")
    else:
        print("Kredensial siap, tinggal login sekali:")
        print("  python main.py --qr   (tercepat, tanpa OTP)")
        print("  python main.py        (kirim kode OTP ke Telegram)")
    return True


def reset_session() -> bool:
    """Hapus file session agar akun bisa diloginkan ulang dari nol.

    Returns:
        ``True`` bila ada file yang dihapus.
    """
    removed = False
    for path in config.DATA_DIR.glob("userbot.session*"):
        try:
            path.unlink()
            print(f"Dihapus: {path}")
            removed = True
        except OSError as exc:
            print(f"Gagal menghapus {path}: {exc}", file=sys.stderr)
    if not removed:
        print("Tidak ada file session untuk dihapus.")
    return removed
