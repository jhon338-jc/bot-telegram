"""Konfigurasi logging: console + file dengan rotasi.

Lokasi file log ditentukan oleh ``config.LOG_DIR`` dan dibuat otomatis
jika belum ada. Satu logger bernama ``bot`` dipakai di seluruh aplikasi.

Saat userbot dijalankan sebagai server (``pythonw.exe`` lewat Task
Scheduler) tidak ada console sama sekali, sehingga ``sys.stderr`` bernilai
``None``. Handler console lalu dilewati supaya tidak melempar error dari
dalam ``logging``; log tetap lengkap di ``logs/bot.log``.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from config import LOG_DIR, LOG_LEVEL

LOG_FORMAT: str = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def setup_logging() -> logging.Logger:
    """Siapkan logging console dan file (bot.log) dengan rotasi.

    Handler dipasang pada logger *root*, bukan hanya pada logger ``bot``.
    Setiap modul handler memakai ``logging.getLogger(__name__)``, jadi
    kalau hanya logger ``bot`` yang dikonfigurasi, log dari
    ``handlers.stat`` atau ``handlers.menu`` tidak akan pernah muncul di
    ``bot.log``.

    Returns:
        Instance ``logging.Logger`` bernama ``bot`` siap dipakai.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    if not root.handlers:
        root.setLevel(LOG_LEVEL)

        formatter = logging.Formatter(LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)

        file_handler = RotatingFileHandler(
            LOG_DIR / "bot.log",
            maxBytes=1_000_000,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)

        root.addHandler(file_handler)
        # Tanpa console (pythonw/service) sys.stderr bernilai None, sehingga
        # StreamHandler akan gagal setiap kali menulis. Lewati saja di mode itu.
        if sys.stderr is not None:
            root.addHandler(console_handler)

    return logging.getLogger("bot")


setup_logging()