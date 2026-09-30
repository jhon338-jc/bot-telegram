"""Kumpulan handler userbot dan error handler global.

Setiap modul di folder ``handlers`` mengekspos fungsi ``register(ctx)``
yang memasang callback Telethon ke klien. Modul baru cukup ditambahkan ke
tuple ``_HANDLER_MODULES`` tanpa menyentuh file lain.

Telethon memanggil setiap callback dengan satu argumen saja dan menangkap
exception-nya sendiri, jadi tidak ada mekanisme ``(event, error)`` bawaan.
:function:`_install_error_guard` membungkus tiap callback yang didaftarkan
supaya semua kegagalan masuk ke log aplikasi (``logs/bot.log``) lengkap
dengan traceback, alih-alih hanya muncul di logger internal Telethon.
"""

from __future__ import annotations

import functools
import logging
import traceback

from telethon.events import NewMessage

from utils.context import Context

from . import (
    admin,
    echo,
    groups,
    help,
    id,
    members,
    menu,
    start,
    stat,
    ucapan,
)

logger = logging.getLogger(__name__)

__all__ = ["register_handlers", "on_error"]

# Urutan modul: perintah umum dulu, baru modul khusus admin, lalu modul
# listener otomatis. Modul ucapan dipasang terakhir karena ia bukan
# perintah, melainkan bereaksi ke aksi grup.
_HANDLER_MODULES = (
    start,
    menu,
    help,
    id,
    echo,
    groups,
    stat,
    members,
    admin,
    ucapan,
)


def on_error(event: NewMessage, exc: Exception) -> None:
    """Catat kegagalan sebuah handler beserta konteks chat-nya.

    Args:
        event: Event yang memicu error.
        exc: Exception yang ditangkap.
    """
    logger.error("Kesalahan di handler: %s: %s", type(exc).__name__, exc)
    chat = getattr(event, "chat_id", None)
    if chat is not None:
        logger.error("  terjadi di chat %s", chat)
    logger.debug("Traceback:\n%s", traceback.format_exc())


def _guard(callback):
    """Bungkus callback handler agar error-nya masuk ke :func:`on_error`.

    Args:
        callback: Fungsi async handler dengan satu parameter ``event``.

    Returns:
        Fungsi async pengganti yang tidak pernah melempar exception, sehingga
        satu handler yang rusak tidak menghentikan userbot.
    """

    @functools.wraps(callback)
    async def wrapper(event):
        try:
            return await callback(event)
        except Exception as exc:  # noqa: BLE001 - sengaja ditangkap di sini
            on_error(event, exc)
            return None

    return wrapper


def _install_error_guard(client) -> None:
    """Bungkus semua handler yang didaftarkan pada klien ini.

    ``TelegramClient.on`` hanya mendelegasikan ke ``add_event_handler``,
    jadi satu titik ini sudah mencakup seluruh modul handler.

    Args:
        client: Klien Telethon yang akan diberi wrapper.
    """
    original = client.add_event_handler

    def add_event_handler(callback, event=None):
        return original(_guard(callback), event)

    client.add_event_handler = add_event_handler  # type: ignore[method-assign]


def register_handlers(ctx: Context) -> None:
    """Pasang seluruh handler dari setiap modul ke klien.

    Args:
        ctx: Konteks bersama berisi klien, database, dan profil akun.
    """
    _install_error_guard(ctx.client)

    for module in _HANDLER_MODULES:
        module.register(ctx)

    logger.info("Terdaftar %d modul handler.", len(_HANDLER_MODULES))
