"""Konfigurasi global userbot Telegram.

Berbeda dengan bot resmi, userbot ini memakai **akun Telegram asli** yang
dicatat melalui session MTProto. Kredensial dibaca dari environment (``.env``)
lewat python-dotenv: ``API_ID`` dan ``API_HASH`` dari my.telegram.org, lalu
``PHONE`` untuk proses login OTP.

Nilai yang tidak ada **tidak** menggagalkan import modul ini. Semua pembacaan
sifatnya toleran, dan pemeriksaan seriousness dilakukan lewat :func:`validate`
supaya program bisa menampilkan panduan lengkap (``python main.py --cek``)
alih-alih melempar traceback yang membingungkan.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR: Path = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")


class ConfigError(RuntimeError):
    """Konfigurasi tidak lengkap; bisa diperbaiki sendiri oleh user."""


def _parse_int_list(value: str | None) -> list[int]:
    """Ubah string CSV menjadi list of int, abaikan nilai kosong/tidak valid.

    Args:
        value: Nilai mentah dari environment, misal ``"-100123, -100456, "``.

    Returns:
        List berisi integer yang berhasil diparsing.
    """
    if not value:
        return []
    parsed: list[int] = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            parsed.append(int(item))
        except ValueError:
            continue
    return parsed


def _parse_bool(value: str | None, default: bool) -> bool:
    """Ubah string environment menjadi boolean.

    Args:
        value: Nilai mentah, misal ``"1"``, ``"true"``, ``"off"``.
        default: Nilai kembalian bila ``value`` kosong.

    Returns:
        ``True`` bila nilai menyatakan aktif.
    """
    if value is None:
        return default
    normalized = value.strip().casefold()
    if not normalized:
        return default
    return normalized in {"1", "true", "yes", "on", "y"}


def _parse_int(value: str | None, default: int = 0) -> int:
    """Ubah string menjadi int, kembali ke ``default`` bila tidak valid.

    Args:
        value: Nilai mentah dari environment.
        default: Nilai kembalian bila ``value`` kosong atau bukan angka.

    Returns:
        Integer hasil parsing atau ``default``.
    """
    if value is None:
        return default
    value = value.strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _parse_float(value: str | None, default: float) -> float:
    """Ubah string menjadi float, kembali ke ``default`` bila tidak valid.

    Args:
        value: Nilai mentah dari environment.
        default: Nilai kembalian bila ``value`` kosong atau bukan angka.

    Returns:
        Float hasil parsing atau ``default``.
    """
    if value is None:
        return default
    value = value.strip()
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


# API_ID berupa angka dari my.telegram.org. Nilai 0 = belum diisi, dan
# akan dilaporkan oleh validate() dengan panduan lengkap.
API_ID: int = _parse_int(os.getenv("API_ID"))
API_HASH: str = os.getenv("API_HASH", "").strip()

# Nomor akun yang dipakai login. Boleh dikosongkan, lalu program
# menanyakannya sendiri di console.
PHONE: str = os.getenv("PHONE", "").strip()

# Kode OTP dan password 2FA. Opsional: bila diisi, program tidak perlu
# menunggu input keyboard sama sekali (berguna untuk login dari IDE,
# Task Scheduler, atau service). Kosongkan setelah login berhasil.
OTP_CODE: str = os.getenv("OTP_CODE", "").strip()
TWOFA_PASSWORD: str = os.getenv("TWOFA_PASSWORD", "")

ADMIN_IDS: list[int] = _parse_int_list(os.getenv("ADMIN_IDS"))
ALLOWED_GROUP_IDS: list[int] = _parse_int_list(os.getenv("ALLOWED_GROUP_IDS"))

# Jeda minimum antar pesan yang dikirim otomatis (detik). Pesan pertama
# dikirim langsung tanpa menunggu; jeda hanya berlaku antar pesan
# beruntun, sehingga bot tetap terasa responsif.
SEND_DELAY: float = max(0.0, _parse_float(os.getenv("SEND_DELAY"), 0.3))

# Ucapan otomatis di grup. Aktif secara bawaan dan berlaku di SEMUA grup
# yang diikuti akun ini, bukan hanya grup yang ada di ALLOWED_GROUP_IDS.
# Isi WELCOME_TEXT / GOODBYE_TEXT sebagai template bawaan; teks per grup
# bisa ditimpa lewat perintah /salam dan /pamit (disimpan di
# data/ucapan.json) sehingga nilai di sini tidak ikut berubah.
WELCOME_ENABLED: bool = _parse_bool(os.getenv("WELCOME_ENABLED"), True)
GOODBYE_ENABLED: bool = _parse_bool(os.getenv("GOODBYE_ENABLED"), True)
WELCOME_TEXT: str = os.getenv("WELCOME_TEXT", "").strip()
GOODBYE_TEXT: str = os.getenv("GOODBYE_TEXT", "").strip()

# ID grup yang sementara mematikan ucapan, diisi oleh perintah /off. Status
# ini hanya berlaku selama proses berjalan; mengaktifkan kembali cukup /on.
UCAPAN_MATI: set[str] = set()

# Gambar yang dikirim bersama perintah /menu. Letakkan file .jpg atau .png
# di folder ini; bila kosong, bot memakai foto profil Telegram-nya.
MENU_IMAGE: str = os.getenv("MENU_IMAGE", "").strip()

LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").strip().upper()

DATA_DIR: Path = BASE_DIR / "data"
LOG_DIR: Path = BASE_DIR / "logs"
IMAGE_DIR: Path = DATA_DIR / "foto"
DATABASE_PATH: Path = DATA_DIR / "bot.db"
SESSION_PATH: Path = DATA_DIR / "userbot"

# Session wajib ada di folder yang bisa ditulis, kalau tidak Telethon
# gagal menyimpan otorisasi dan OTP akan ditanyakan ulang tiap restart.
DATA_DIR.mkdir(parents=True, exist_ok=True)


def problems() -> list[str]:
    """Kumpulkan seluruh masalah konfigurasi yang aktif saat ini.

    Returns:
        Daftar pesan singkat. Daftar kosong berarti konfigurasi sah.
    """
    found: list[str] = []
    if API_ID <= 0:
        found.append("API_ID belum diisi atau bukan angka positif")
    if not API_HASH:
        found.append("API_HASH belum diisi")
    return found


def validate() -> None:
    """Pastikan konfigurasi cukup untuk menghubungi Telegram.

    Raises:
        ConfigError: Bila ``API_ID`` atau ``API_HASH`` belum terisi.
    """
    found = problems()
    if not found:
        return
    raise ConfigError(
        "Konfigurasi belum lengkap: " + "; ".join(found) + "."
    )


def is_admin(user_id: int) -> bool:
    """Periksa apakah sebuah user terdaftar sebagai admin.

    Args:
        user_id: ID Telegram dari user.

    Returns:
        ``True`` jika ID ada di daftar ``ADMIN_IDS``.
    """
    return user_id in ADMIN_IDS


def is_group_allowed(chat_id: int) -> bool:
    """Periksa apakah sebuah grup terdaftar di whitelist.

    Args:
        chat_id: ID chat (negatif untuk grup/supergroup/channel).

    Returns:
        ``True`` jika ID ada di daftar ``ALLOWED_GROUP_IDS``.
    """
    return chat_id in ALLOWED_GROUP_IDS
