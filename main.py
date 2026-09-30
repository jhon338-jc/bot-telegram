"""Entry point userbot Telegram.

Userbot ini memakai **akun Telegram asli**, bukan bot dari @BotFather.
Login dilakukan lewat protokol MTProto: session tersimpan di
``data/userbot.session`` sehingga kode OTP hanya diminta satu kali.

Contoh:
    python main.py            # pakai akun yang sudah pernah login
    python main.py --qr       # login pertama kali lewat QR (tercepat)
    python main.py --cek      # cek konfigurasi tanpa konek ke Telegram
    python main.py --reset    # hapus session, lalu login ulang
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import config
from handlers import register_handlers
from handlers.stat import tandai_mulai
from utils.context import Context
from utils.database import Database
from utils.logger import setup_logging
from utils.login import (
    SETUP_GUIDE,
    build_client,
    check_setup,
    ensure_login,
    explain_error,
    reset_session,
)

logger = setup_logging()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Baca argumen baris perintah.

    Args:
        argv: Daftar argumen; ``None`` berarti ``sys.argv[1:]``.

    Returns:
        Objek argumen hasil parsing.
    """
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Userbot Telegram berbasis akun asli (Telethon).",
        epilog="Butuh API_ID dan API_HASH? Jalankan: python main.py --cek",
    )
    parser.add_argument(
        "--qr",
        action="store_true",
        help="Login lewat QR (tanpa kode OTP) - hanya perlu saat pertama kali.",
    )
    parser.add_argument(
        "--cek",
        action="store_true",
        help="Tampilkan status konfigurasi lalu keluar tanpa konek.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Hapus file session lalu keluar, untuk login ulang dari nol.",
    )
    return parser.parse_args(argv)


async def run(*, use_qr: bool = False) -> None:
    """Jalankan userbot sampai koneksi terputus (Ctrl+C).

    Args:
        use_qr: Bila ``True``, gunakan login QR saat session belum ada.

    Raises:
        config.ConfigError: Bila ``.env`` belum lengkap.
        RuntimeError: Bila login gagal.
    """
    config.validate()

    db = Database(config.DATABASE_PATH)
    db.connect()

    client = build_client()
    try:
        me = await ensure_login(client, use_qr=use_qr)
    except Exception:
        await client.disconnect()
        db.close()
        raise

    if not config.ADMIN_IDS:
        config.ADMIN_IDS = [me.id]
        logger.info("ADMIN_IDS kosong - akun ini otomatis didaftarkan sebagai admin.")

    ctx = Context(client=client, db=db, me=me)
    register_handlers(ctx)
    tandai_mulai()

    logger.info("Userbot aktif. Grup yang diizinkan: %s", config.ALLOWED_GROUP_IDS or "kosong")
    logger.info("Pemilik bot: %s (ID %s). Admin terdaftar: %s", ctx.display_name, ctx.me_id, config.ADMIN_IDS or "tidak ada")
    logger.info("Tekan Ctrl+C untuk menghentikan.")

    try:
        await client.run_until_disconnected()
    finally:
        await client.disconnect()
        db.close()
        logger.info("Userbot dihentikan.")


def main() -> None:
    """Titik masuk skrip: jalankan event loop sampai userbot berhenti."""
    args = parse_args()

    if args.cek:
        sys.exit(0 if check_setup() else 1)

    if args.reset:
        sys.exit(0 if reset_session() else 1)

    try:
        asyncio.run(run(use_qr=args.qr))
    except KeyboardInterrupt:
        logger.info("Dihentikan oleh user.")
    except config.ConfigError as exc:
        logger.error("%s", exc)
        print(SETUP_GUIDE)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001 - pesan error untuk user
        logger.error("Gagal menjalankan userbot: %s", exc)
        print()
        print("  MASALAH: " + explain_error(exc))
        print()
        sys.exit(1)


if __name__ == "__main__":
    main()
